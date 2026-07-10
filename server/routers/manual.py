"""
Manual entry router — 근무자 수동 송출 입력.
POST   /api/manual/entries              → 수동 송출 내역 1건 입력
GET    /api/manual/entries?date=        → 특정 방송일자의 입력 목록
DELETE /api/manual/entries/{entry_id}   → 입력 1건 삭제
GET    /api/manual/campaign-worker?date= → 날짜별 공익광고 근무자 조회
POST   /api/manual/campaign-worker       → 날짜별 공익광고 근무자 저장
GET    /api/manual/client-ip             → 접속 IP 조회 (화면 표출용)
"""

from datetime import datetime

from fastapi import APIRouter, Request, Query, HTTPException
from pydantic import BaseModel

from database import get_apst_conn
from parsers.utils import classify_grade
from services.activity_log import log_event

router = APIRouter(prefix="/api/manual", tags=["manual"])

# 수동 입력에서 선택 가능한 소재종류
_CONTENT_TYPES = {"흘림자막", "공익재난", "캠페인"}


class ManualEntry(BaseModel):
    broadcast_date: str            # YYYY-MM-DD
    content_type:   str            # 흘림자막 | 공익재난 | 캠페인
    broadcast_time: str            # HH:MM:SS 또는 HH:MM
    program_name:   str | None = None
    item_title:     str | None = None
    worker_name:    str | None = None


class CampaignWorker(BaseModel):
    broadcast_date: str
    worker_name:    str | None = None


def _client_ip(request: Request) -> str:
    """접속 클라이언트 IP. 프록시(X-Forwarded-For)가 있으면 우선 사용."""
    xff = request.headers.get("x-forwarded-for")
    if xff:
        return xff.split(",")[0].strip()
    return request.client.host if request.client else ""


def _normalize_time(t: str) -> str:
    """'HH:MM' → 'HH:MM:00'. 이미 초가 있으면 그대로."""
    parts = t.strip().split(":")
    if len(parts) == 2:
        return f"{parts[0].zfill(2)}:{parts[1].zfill(2)}:00"
    if len(parts) == 3:
        return f"{parts[0].zfill(2)}:{parts[1].zfill(2)}:{parts[2].zfill(2)}"
    return t


@router.get("/client-ip")
def get_client_ip(request: Request) -> dict:
    """접속 IP 반환 (수동 입력 화면 표출용)."""
    return {"ip": _client_ip(request)}


@router.post("/entries")
def create_entry(body: ManualEntry, request: Request) -> dict:
    """수동 송출 내역 1건 입력."""
    if body.content_type not in _CONTENT_TYPES:
        raise HTTPException(status_code=400, detail=f"소재종류는 {_CONTENT_TYPES} 중 하나여야 합니다.")

    time_str = _normalize_time(body.broadcast_time)
    try:
        hour = int(time_str[:2])
    except (ValueError, IndexError):
        raise HTTPException(status_code=400, detail="송출시간 형식이 올바르지 않습니다. (예: 08:53 또는 08:53:00)")

    ip = _client_ip(request)
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    with get_apst_conn() as conn:
        cur = conn.execute(
            """INSERT INTO manual_entries
               (broadcast_date, content_type, broadcast_time, broadcast_hour,
                program_name, item_title, grade, worker_name, client_ip, created_at)
               VALUES (?,?,?,?,?,?,?,?,?,?)""",
            (body.broadcast_date, body.content_type, time_str, hour,
             body.program_name or "", body.item_title or "",
             classify_grade(time_str), body.worker_name or "", ip, now),
        )
        entry_id = cur.lastrowid

    log_event("info", "manual_input",
              f"수동 송출 입력: {body.broadcast_date} {time_str} [{body.content_type}] "
              f"{body.item_title or ''} (근무자: {body.worker_name or '-'}, IP: {ip})")

    return {"id": entry_id, "created_at": now, "client_ip": ip, "message": "입력되었습니다."}


@router.get("/entries")
def list_entries(date: str = Query(..., description="YYYY-MM-DD")) -> dict:
    """특정 방송일자의 수동 입력 목록 (입력 순서)."""
    with get_apst_conn() as conn:
        rows = conn.execute(
            """SELECT id, broadcast_date, content_type, broadcast_time, broadcast_hour,
                      program_name, item_title, grade, worker_name, client_ip, created_at
               FROM manual_entries
               WHERE broadcast_date = ?
               ORDER BY broadcast_time, id""",
            (date,),
        ).fetchall()
    return {"date": date, "total": len(rows), "entries": [dict(r) for r in rows]}


@router.delete("/entries/{entry_id}")
def delete_entry(entry_id: int) -> dict:
    """수동 입력 1건 삭제."""
    with get_apst_conn() as conn:
        cur = conn.execute("DELETE FROM manual_entries WHERE id = ?", (entry_id,))
        if cur.rowcount == 0:
            raise HTTPException(status_code=404, detail="해당 입력을 찾을 수 없습니다.")
    return {"message": "삭제되었습니다.", "id": entry_id}


@router.get("/campaign-worker")
def get_campaign_worker(date: str = Query(..., description="YYYY-MM-DD")) -> dict:
    """날짜별 공익광고 송출 근무자 조회."""
    with get_apst_conn() as conn:
        row = conn.execute(
            "SELECT worker_name FROM campaign_worker WHERE broadcast_date = ?", (date,)
        ).fetchone()
    return {"date": date, "worker_name": row["worker_name"] if row else ""}


@router.post("/campaign-worker")
def set_campaign_worker(body: CampaignWorker) -> dict:
    """날짜별 공익광고 송출 근무자 저장."""
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with get_apst_conn() as conn:
        conn.execute(
            """INSERT INTO campaign_worker (broadcast_date, worker_name, updated_at)
               VALUES (?,?,?)
               ON CONFLICT(broadcast_date)
               DO UPDATE SET worker_name = excluded.worker_name, updated_at = excluded.updated_at""",
            (body.broadcast_date, body.worker_name or "", now),
        )
    return {"message": "공익광고 근무자가 저장되었습니다.", "date": body.broadcast_date}
