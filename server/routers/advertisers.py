"""
Advertisers router — CRUD for advertiser info used in F-04 PDF.
"""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from database import get_apst_conn

router = APIRouter(prefix="/api/advertisers", tags=["advertisers"])


class AdvertiserIn(BaseModel):
    item_name:        str
    company_name:     str        = ""
    business_reg_no:  str        = ""
    ceo_name:         str        = ""
    business_type:    str        = ""
    broadcast_medium: str        = "TV"
    note:             str        = "송출시간은 방송사 상황에 따라 변동될 수 있음"


class AdvertiserUpdate(BaseModel):
    company_name:     str | None = None
    business_reg_no:  str | None = None
    ceo_name:         str | None = None
    business_type:    str | None = None
    broadcast_medium: str | None = None
    note:             str | None = None


@router.get("")
def list_advertisers() -> list[dict]:
    """광고주 목록 전체 조회."""
    with get_apst_conn() as conn:
        rows = conn.execute(
            "SELECT * FROM advertisers ORDER BY item_name"
        ).fetchall()
    return [dict(r) for r in rows]


@router.get("/{item_name}")
def get_advertiser(item_name: str) -> dict:
    """특정 소재명의 광고주 정보 조회."""
    with get_apst_conn() as conn:
        row = conn.execute(
            "SELECT * FROM advertisers WHERE item_name = ?", (item_name,)
        ).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="광고주 정보를 찾을 수 없습니다.")
    return dict(row)


@router.post("", status_code=201)
def create_advertiser(body: AdvertiserIn) -> dict:
    """광고주 정보 등록."""
    with get_apst_conn() as conn:
        try:
            conn.execute(
                """INSERT INTO advertisers
                   (item_name, company_name, business_reg_no, ceo_name,
                    business_type, broadcast_medium, note)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (
                    body.item_name, body.company_name, body.business_reg_no,
                    body.ceo_name,  body.business_type, body.broadcast_medium,
                    body.note,
                ),
            )
        except Exception:
            raise HTTPException(
                status_code=409,
                detail=f"'{body.item_name}' 광고주 정보가 이미 존재합니다."
            )
    return {"message": "광고주 정보가 등록되었습니다.", "item_name": body.item_name}


@router.put("/{item_name}")
def update_advertiser(item_name: str, body: AdvertiserUpdate) -> dict:
    """광고주 정보 수정 (전달된 필드만 업데이트)."""
    updates = {k: v for k, v in body.model_dump().items() if v is not None}
    if not updates:
        raise HTTPException(status_code=400, detail="변경할 필드가 없습니다.")

    set_clause = ", ".join(f"{k} = ?" for k in updates)
    values = list(updates.values()) + [item_name]

    with get_apst_conn() as conn:
        cur = conn.execute(
            f"UPDATE advertisers SET {set_clause}, updated_at = datetime('now') WHERE item_name = ?",
            values,
        )
        if cur.rowcount == 0:
            raise HTTPException(status_code=404, detail="광고주 정보를 찾을 수 없습니다.")
    return {"message": "광고주 정보가 수정되었습니다.", "item_name": item_name}


@router.delete("/{item_name}")
def delete_advertiser(item_name: str) -> dict:
    """광고주 정보 삭제."""
    with get_apst_conn() as conn:
        cur = conn.execute(
            "DELETE FROM advertisers WHERE item_name = ?", (item_name,)
        )
        if cur.rowcount == 0:
            raise HTTPException(status_code=404, detail="광고주 정보를 찾을 수 없습니다.")
    return {"message": "광고주 정보가 삭제되었습니다.", "item_name": item_name}
