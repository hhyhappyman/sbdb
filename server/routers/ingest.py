"""
Ingest router — upload files and load them into the DB.
POST /api/ingest/cml             → parse CML and update clip_map in ddr1.db
POST /api/ingest/apst            → parse APST file and insert into apst.db
POST /api/ingest/ddr1            → parse DDR1 log and insert into ddr1.db
POST /api/ingest/apst/scan       → 설정된 apst_dir 폴더를 스캔하여 전체 적재
POST /api/ingest/ddr1/scan       → 설정된 ddr1_dir 폴더를 스캔하여 전체 적재
GET  /api/ingest/status          → 현재 DB 적재 현황 (날짜 범위, 건수 등)
"""

import tempfile
import os
import re
import json
from datetime import date as _date, timedelta
from pathlib import Path
from fastapi import APIRouter, UploadFile, File, Form, HTTPException

from database import get_apst_conn, get_ddr1_conn
from parsers.cml_parser import parse_cml, build_clip_rows, resolve_cml_path_for_date
from parsers.apst_parser import parse_apst, parse_apst_all, find_manual_segments
from parsers.ddr1_parser import parse_ddr1, extract_manual_segment_records
from parsers.utils import (
    extract_item_name, classify_grade, clean_prm_campaign_name,
    apst_name_matches, find_apst_files,
)
from services.aggregator import get_campaign_names, get_apst_name_map, get_apst_name_before
from services.activity_log import log_event
from config import APST_SUFFIX_DEFAULT

router = APIRouter(prefix="/api/ingest", tags=["ingest"])


def _get_setting(key: str) -> str:
    """app_settings에서 값 조회."""
    with get_apst_conn() as conn:
        row = conn.execute(
            "SELECT value FROM app_settings WHERE key = ?", (key,)
        ).fetchone()
    return row["value"] if row else ""


def _apst_suffix() -> str:
    """APST 파일명 접미사 설정값 (미설정 시 기본값)."""
    return _get_setting("apst_suffix") or APST_SUFFIX_DEFAULT


def _insert_apst_records(records: list[dict], conn) -> int:
    """
    apst.db에 레코드 삽입. 실제로 삽입된 건수를 반환한다.
    `INSERT OR IGNORE` + UNIQUE(broadcast_date, broadcast_time, clip_id) 인덱스로,
    파일명이 달라도 같은 (날짜·시간·clip_id) 행은 자동으로 건너뛴다(중복 방지).
    """
    if not records:
        return 0
    before = conn.total_changes
    conn.executemany(
        """INSERT OR IGNORE INTO broadcasts
           (broadcast_date, broadcast_time, broadcast_hour,
            clip_id, item_name_raw, item_name, duration_sec,
            program_block, content_type, content_type_label, grade,
            main_equipment, internal_id, source_file)
           VALUES
           (:broadcast_date, :broadcast_time, :broadcast_hour,
            :clip_id, :item_name_raw, :item_name, :duration_sec,
            :program_block, :content_type, :content_type_label, :grade,
            :main_equipment, :internal_id, :source_file)""",
        records,
    )
    return conn.total_changes - before


def _load_cml_map_by_date(dates: set[str], warn: bool = True) -> dict[str, dict]:
    """
    날짜별 CML 매핑을 로드한다 (imc<YYYYMMDD>.cml). 찾지 못한 날짜는 빈 dict.
    warn=True면 CML 없는 날짜에 file_missing 로그를 남긴다(보조 로드 시 warn=False).
    cml_path 미설정이면 모든 날짜가 빈 dict.
    """
    cml_setting = _get_setting("cml_path")
    cml_map_by_date: dict[str, dict] = {}
    for date in dates:
        cml_file = resolve_cml_path_for_date(cml_setting, date)
        if cml_file:
            cml_map_by_date[date] = parse_cml(cml_file)
        else:
            cml_map_by_date[date] = {}
            if warn:
                log_event(
                    "warning", "file_missing",
                    f"CML 파일을 찾을 수 없습니다 (날짜: {date}, cml_path 설정: '{cml_setting}')"
                )
    return cml_map_by_date


def _insert_manual_segments(segments: list[dict]) -> int:
    """
    주장비명이 DDR1인 수동 송출 구간(segments)에 대해 해당 날짜의 DDR1 로그 파일을
    찾아 실제 송출된 소재를 추출하고 ddr1.db에 적재한다.
    ddr1_dir 미설정, 해당 날짜 로그/CML 없음 등의 경우 조용히 0건 반환 (로그는 기록됨).
    """
    if not segments:
        return 0

    ddr1_dir = _get_setting("ddr1_dir")
    if not ddr1_dir:
        return 0

    dir_path = Path(ddr1_dir)
    if not dir_path.exists() or not dir_path.is_dir():
        return 0

    log_files_by_date: dict[str, str] = {}
    for fpath in list(dir_path.glob("*.Log")) + list(dir_path.glob("*.log")):
        d = _date_from_filename(fpath.name)
        if d and d not in log_files_by_date:
            log_files_by_date[d] = str(fpath)

    # 구간별 source_file("manual:로그파일:트리거ID")을 미리 계산.
    # 이미 적재된 구간은 추출(로그 파싱) 전에 걸러내 성능을 확보한다.
    # DDR1 로그가 아직 없으면(폴더 감시에서 APST가 DDR1보다 먼저 도착한 경우 등)
    # 조용히 건너뛴다. 파일이 도착하면 재적재(reconcile) 때 다시 시도되고,
    # 실제 누락은 달력 붉은색(3파일 존재 점검)으로 이미 표시되므로 별도 경고를 남기지 않는다.
    seg_src: list[tuple[dict, str]] = []
    for seg in segments:
        log_path = log_files_by_date.get(seg["broadcast_date"])
        if not log_path:
            continue
        seg_src.append((seg, f"manual:{Path(log_path).name}:{seg['trigger_clip_id']}"))

    if not seg_src:
        return 0

    all_srcs = list({src for _, src in seg_src})
    with get_ddr1_conn() as conn:
        placeholders = ",".join("?" * len(all_srcs))
        done = {
            row["source_file"]
            for row in conn.execute(
                f"SELECT DISTINCT source_file FROM broadcasts WHERE source_file IN ({placeholders})",
                all_srcs,
            ).fetchall()
        }

    # 아직 적재되지 않은 구간만 실제 추출 대상으로 남김
    todo_segments = [seg for seg, src in seg_src if src not in done]
    if not todo_segments:
        return 0

    todo_dates = {seg["broadcast_date"] for seg in todo_segments}
    # 어제 날짜 CML도 함께 로드 (당일 CML·자동송출 DB에 없을 때 보완용)
    prev_dates = set()
    for d in todo_dates:
        try:
            prev_dates.add((_date.fromisoformat(d) - timedelta(days=1)).isoformat())
        except ValueError:
            pass
    cml_map_by_date = _load_cml_map_by_date(todo_dates)
    # 어제 날짜 CML은 보조 로드 (경고 생략)
    cml_map_by_date.update(_load_cml_map_by_date(prev_dates - todo_dates, warn=False))
    campaign_names = get_campaign_names()
    # CML에 없는 clip_id는 같은 날짜 자동송출(apst.db) 소재명으로 보완
    apst_map_by_date = get_apst_name_map(todo_dates)

    # 날짜 무관 자동송출 조회 (기준일 이전 가장 가까운 날짜) — 결과 메모이즈
    _before_cache: dict = {}
    def _apst_before(clip_id: str, before_date: str):
        k = (clip_id, before_date)
        if k not in _before_cache:
            _before_cache[k] = get_apst_name_before(clip_id, before_date)
        return _before_cache[k]

    records = extract_manual_segment_records(
        todo_segments, log_files_by_date, cml_map_by_date, campaign_names,
        apst_map_by_date, apst_lookup=_apst_before,
    )
    if not records:
        return 0

    with get_ddr1_conn() as conn:
        conn.executemany(
            """INSERT INTO broadcasts
               (broadcast_date, broadcast_time, broadcast_hour,
                clip_id, item_name_raw, item_name,
                content_type_label, grade, duration_sec, source_file)
               VALUES
               (:broadcast_date, :broadcast_time, :broadcast_hour,
                :clip_id, :item_name_raw, :item_name,
                :content_type_label, :grade, :duration_sec, :source_file)""",
            records,
        )
    log_event("info", "db_insert", f"수동 송출 구간 {len(records)}건 적재 (ddr1.db)")
    return len(records)


def ingest_date(date: str) -> dict:
    """
    해당 방송일의 로컬 파일(CML/APST)을 적재한다. FTP로 파일을 받은 뒤 호출한다.
    - CML: 해당 날짜 imc<YYYYMMDD>.cml → clip_map 갱신(INSERT OR REPLACE)
    - APST: 해당 날짜 .apst → broadcasts 적재(이미 처리된 파일은 건너뜀)
            + 수동 송출 구간(DDR1) 적재
    반환: {"date", "cml", "apst", "manual", "apst_files"}
    """
    result = {"date": date, "cml": 0, "apst": 0, "manual": 0, "apst_files": []}

    # ── CML ──
    cml_setting = _get_setting("cml_path")
    cml_file = resolve_cml_path_for_date(cml_setting, date)
    if cml_file:
        try:
            rows = build_clip_rows(parse_cml(cml_file))
            if rows:
                with get_ddr1_conn() as conn:
                    conn.executemany(
                        """INSERT OR REPLACE INTO clip_map
                           (clip_id, item_type, full_name, advertiser, duration_sec)
                           VALUES (:clip_id, :item_type, :full_name, :advertiser, :duration_sec)""",
                        rows,
                    )
                result["cml"] = len(rows)
        except Exception as e:
            log_event("error", "db_update", f"CML 적재 오류 ({date}): {e}")

    # ── APST + 수동 송출 ──
    apst_dir = _get_setting("apst_dir")
    if apst_dir and Path(apst_dir).exists():
        for fpath in find_apst_files(apst_dir, _apst_suffix(), date):
            fname = fpath.name
            result["apst_files"].append(fname)
            try:
                with get_apst_conn() as conn:
                    exists = conn.execute(
                        "SELECT 1 FROM broadcasts WHERE source_file = ? LIMIT 1", (fname,)
                    ).fetchone()
                if not exists:
                    records = parse_apst(str(fpath), source_file=fname)
                    with get_apst_conn() as conn:
                        _insert_apst_records(records, conn)
                    result["apst"] += len(records)
                # 수동 송출 구간은 중복검사가 있어 항상 시도
                segments = find_manual_segments(str(fpath))
                result["manual"] += _insert_manual_segments(segments)
            except Exception as e:
                log_event("error", "db_insert", f"APST 적재 오류 ({fname}): {e}")

    return result


def _find_manual_windows_for_date(broadcast_date: str) -> list[tuple[str, str]]:
    """
    해당 날짜의 apst_dir 파일에서 수동 송출 구간(시작/종료 시간)을 찾는다.
    parse_ddr1()의 exclude_windows로 전달해, find_manual_segments() 기반 적재와
    겹치지 않도록 한다. apst_dir 미설정이거나 해당 날짜 파일이 없으면 빈 리스트.
    """
    apst_dir = _get_setting("apst_dir")
    if not apst_dir:
        return []

    dir_path = Path(apst_dir)
    if not dir_path.exists() or not dir_path.is_dir():
        return []

    for fpath in find_apst_files(dir_path, _apst_suffix(), broadcast_date):
        try:
            segments = find_manual_segments(str(fpath))
        except Exception:
            continue
        return [(seg["start_time"], seg["end_time"]) for seg in segments]

    return []


def _date_from_filename(filename: str) -> str | None:
    """
    파일명에서 날짜(YYYYMMDD) 추출.
    예: 20260506AAA.apst → 2026-05-06
        2026-05-06.Log   → 2026-05-06
    """
    # YYYYMMDD 패턴
    m = re.search(r'(\d{4})(\d{2})(\d{2})', filename)
    if m:
        return f"{m.group(1)}-{m.group(2)}-{m.group(3)}"
    # YYYY-MM-DD 패턴
    m = re.search(r'(\d{4}-\d{2}-\d{2})', filename)
    if m:
        return m.group(1)
    return None


# ── CML ────────────────────────────────────────────────────────────────────

@router.post("/cml/scan")
def scan_cml_dir() -> dict:
    """
    환경설정의 cml_path 폴더를 스캔하여 모든 .cml 파일을 clip_map에 적재.
    INSERT OR REPLACE로 기존 항목을 최신 정보로 갱신.
    """
    cml_setting = _get_setting("cml_path")
    if not cml_setting:
        raise HTTPException(
            status_code=400,
            detail="환경설정에서 CML 파일 경로(cml_path)를 먼저 설정해 주세요."
        )

    p = Path(cml_setting)
    if p.is_file():
        cml_files = [p]
    elif p.is_dir():
        cml_files = sorted(p.glob("*.cml")) + sorted(p.glob("*.CML"))
    else:
        raise HTTPException(status_code=400, detail=f"경로를 찾을 수 없습니다: {cml_setting}")

    if not cml_files:
        raise HTTPException(status_code=404, detail=f"폴더에 .cml 파일이 없습니다: {cml_setting}")

    all_rows: list[dict] = []
    results = []

    for fpath in cml_files:
        try:
            clip_map = parse_cml(str(fpath))
            rows = build_clip_rows(clip_map)
            all_rows.extend(rows)
            results.append({"file": fpath.name, "status": "ok", "clips": len(rows)})
        except Exception as e:
            results.append({"file": fpath.name, "status": "error", "message": str(e)})

    if all_rows:
        with get_ddr1_conn() as conn:
            conn.executemany(
                """INSERT OR REPLACE INTO clip_map
                   (clip_id, item_type, full_name, advertiser, duration_sec)
                   VALUES (:clip_id, :item_type, :full_name, :advertiser, :duration_sec)""",
                all_rows,
            )
        log_event("info", "db_update",
                  f"CML 전체 스캔 갱신: {len(cml_files)}개 파일, {len(all_rows)}건")

    return {
        "message": f"{len(cml_files)}개 파일 스캔 완료.",
        "total_clips": len(all_rows),
        "files": results,
    }


@router.post("/cml")
async def ingest_cml(file: UploadFile = File(...)) -> dict:
    """CML 매핑 파일을 업로드하여 ddr1.db의 clip_map을 갱신합니다."""
    content = await file.read()

    with tempfile.NamedTemporaryFile(delete=False, suffix=".cml") as tmp:
        tmp.write(content)
        tmp_path = tmp.name

    try:
        clip_map = parse_cml(tmp_path)
        rows = build_clip_rows(clip_map)
    finally:
        os.unlink(tmp_path)

    if not rows:
        raise HTTPException(status_code=400, detail="CML 파일에서 유효한 데이터를 찾을 수 없습니다.")

    with get_ddr1_conn() as conn:
        conn.execute("DELETE FROM clip_map")
        conn.executemany(
            """INSERT INTO clip_map (clip_id, item_type, full_name, advertiser, duration_sec)
               VALUES (:clip_id, :item_type, :full_name, :advertiser, :duration_sec)""",
            rows,
        )
    log_event("info", "db_update", f"CML 매핑 갱신: {file.filename} ({len(rows)}건)")

    return {
        "message": "CML 파일이 처리되었습니다.",
        "filename": file.filename,
        "total_clips": len(rows),
    }


# ── APST ───────────────────────────────────────────────────────────────────

@router.post("/apst")
async def ingest_apst(file: UploadFile = File(...)) -> dict:
    """APST 파일을 업로드하여 apst.db에 적재합니다. 이미 처리한 파일은 건너뜁니다."""
    source_file = file.filename
    content = await file.read()

    # Check duplicate
    with get_apst_conn() as conn:
        exists = conn.execute(
            "SELECT 1 FROM broadcasts WHERE source_file = ? LIMIT 1",
            (source_file,),
        ).fetchone()
    if exists:
        raise HTTPException(
            status_code=409,
            detail=f"'{source_file}' 파일은 이미 처리되었습니다.",
        )

    with tempfile.NamedTemporaryFile(delete=False, suffix=".apst") as tmp:
        tmp.write(content)
        tmp_path = tmp.name

    try:
        try:
            records = parse_apst(tmp_path, source_file=source_file)
            segments = find_manual_segments(tmp_path)
        except json.JSONDecodeError as e:
            raise HTTPException(
                status_code=400,
                detail=f"APST 파일이 올바른 JSON 형식이 아닙니다(파일 손상/병합 오류 가능): {e}",
            )
        except Exception as e:
            raise HTTPException(status_code=400, detail=f"APST 파일 처리 오류: {e}")
    finally:
        os.unlink(tmp_path)

    inserted = 0
    if records:
        with get_apst_conn() as conn:
            inserted = _insert_apst_records(records, conn)
        log_event(
            "info", "db_insert",
            f"APST 적재: {source_file} (신규 {inserted}건 / 중복 {len(records) - inserted}건 건너뜀)",
        )

    manual_inserted = _insert_manual_segments(segments)

    return {
        "message": "APST 파일이 처리되었습니다." if records else "저장할 캠페인·ID 소재가 없습니다.",
        "filename": source_file,
        "inserted": inserted,
        "skipped": len(records) - inserted,
        "manual_inserted": manual_inserted,
    }


# ── DDR1 ───────────────────────────────────────────────────────────────────

@router.post("/ddr1")
async def ingest_ddr1(
    file: UploadFile = File(...),
    broadcast_date: str = Form(..., description="YYYY-MM-DD"),
) -> dict:
    """
    DDR1 로그 파일을 업로드하여 ddr1.db에 적재합니다.
    broadcast_date: 해당 로그의 날짜 (YYYY-MM-DD) — 로그에 날짜가 없어 수동 입력
    """
    # Validate date format
    import re
    if not re.match(r"^\d{4}-\d{2}-\d{2}$", broadcast_date):
        raise HTTPException(
            status_code=400,
            detail="broadcast_date 형식이 올바르지 않습니다. (예: 2026-05-06)"
        )

    source_file = file.filename
    content = await file.read()

    # Check duplicate
    with get_ddr1_conn() as conn:
        exists = conn.execute(
            "SELECT 1 FROM broadcasts WHERE source_file = ? LIMIT 1",
            (source_file,),
        ).fetchone()
    if exists:
        raise HTTPException(
            status_code=409,
            detail=f"'{source_file}' 파일은 이미 처리되었습니다.",
        )

    # Load CML map from ddr1.db
    with get_ddr1_conn() as conn:
        rows = conn.execute("SELECT * FROM clip_map").fetchall()
    cml_map = {
        r["clip_id"]: {
            "full_name": r["full_name"],
            "advertiser": r["advertiser"],
            "duration_sec": r["duration_sec"],
        }
        for r in rows
    }
    if not cml_map:
        raise HTTPException(
            status_code=400,
            detail="clip_map이 비어 있습니다. CML 파일을 먼저 업로드해 주세요.",
        )

    # Load campaign names from APST DB
    campaign_names = get_campaign_names()

    with tempfile.NamedTemporaryFile(delete=False, suffix=".log") as tmp:
        tmp.write(content)
        tmp_path = tmp.name

    exclude_windows = _find_manual_windows_for_date(broadcast_date)

    try:
        records = parse_ddr1(
            tmp_path,
            broadcast_date=broadcast_date,
            cml_map=cml_map,
            campaign_names=campaign_names,
            source_file=source_file,
            exclude_windows=exclude_windows,
        )
    finally:
        os.unlink(tmp_path)

    if not records:
        return {
            "message": "저장할 캠페인·ID 소재가 없습니다.",
            "filename": source_file,
            "inserted": 0,
        }

    with get_ddr1_conn() as conn:
        conn.executemany(
            """INSERT INTO broadcasts
               (broadcast_date, broadcast_time, broadcast_hour,
                clip_id, item_name_raw, item_name,
                content_type_label, grade, duration_sec, source_file)
               VALUES
               (:broadcast_date, :broadcast_time, :broadcast_hour,
                :clip_id, :item_name_raw, :item_name,
                :content_type_label, :grade, :duration_sec, :source_file)""",
            records,
        )

    return {
        "message": "DDR1 파일이 처리되었습니다.",
        "filename": source_file,
        "broadcast_date": broadcast_date,
        "inserted": len(records),
    }


# ── PRM 공익/재난 소재 DB 마이그레이션 ────────────────────────────────────────

@router.post("/apst/migrate-prm")
def migrate_prm_to_campaign() -> dict:
    """
    기존 APST 파일을 재스캔하여 PRM 공익/재난 소재를 캠페인으로 apst.db에 추가.
    broadcast_date + broadcast_time + clip_id가 동일한 항목은 건너뜀 (중복 방지).
    """
    apst_dir = _get_setting("apst_dir")
    if not apst_dir:
        raise HTTPException(
            status_code=400,
            detail="환경설정에서 APST 디렉터리(apst_dir)를 먼저 설정해 주세요."
        )
    dir_path = Path(apst_dir)
    if not dir_path.exists() or not dir_path.is_dir():
        raise HTTPException(status_code=400, detail=f"디렉터리를 찾을 수 없습니다: {apst_dir}")

    apst_files = find_apst_files(dir_path, _apst_suffix())
    if not apst_files:
        raise HTTPException(status_code=404, detail=f"폴더에 .apst 파일이 없습니다: {apst_dir}")

    total_inserted = 0

    for fpath in apst_files:
        try:
            all_items = parse_apst_all(str(fpath), source_file=fpath.name)
        except Exception:
            continue

        prm_records = []
        for item in all_items:
            if item.get("con") != "PRM":
                continue
            raw = item.get("item_name_raw", "")
            if "공익" not in raw and "재난" not in raw:
                continue
            btime = item["broadcast_time"]
            prm_records.append({
                "broadcast_date":     item["broadcast_date"],
                "broadcast_time":     btime,
                "broadcast_hour":     int(btime[:2]),
                "clip_id":            item["src_id"],
                "item_name_raw":      raw,
                "item_name":          extract_item_name(raw),
                "duration_sec":       0,
                "program_block":      item.get("program_block", ""),
                "content_type":       "PRM",
                "content_type_label": "공익재난",
                "grade":              classify_grade(btime),
                "main_equipment":     item.get("main_equipment", ""),
                "internal_id":        None,
                "source_file":        fpath.name,
            })

        if not prm_records:
            continue

        with get_apst_conn() as conn:
            for rec in prm_records:
                exists = conn.execute(
                    "SELECT 1 FROM broadcasts WHERE broadcast_date=? AND broadcast_time=? AND clip_id=?",
                    (rec["broadcast_date"], rec["broadcast_time"], rec["clip_id"])
                ).fetchone()
                if not exists:
                    conn.execute(
                        """INSERT INTO broadcasts
                           (broadcast_date, broadcast_time, broadcast_hour,
                            clip_id, item_name_raw, item_name, duration_sec,
                            program_block, content_type, content_type_label, grade,
                            main_equipment, internal_id, source_file)
                           VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                        (rec["broadcast_date"], rec["broadcast_time"], rec["broadcast_hour"],
                         rec["clip_id"], rec["item_name_raw"], rec["item_name"], rec["duration_sec"],
                         rec["program_block"], rec["content_type"], rec["content_type_label"], rec["grade"],
                         rec["main_equipment"], rec["internal_id"], rec["source_file"])
                    )
                    total_inserted += 1

    log_event("info", "db_update", f"PRM 공익/재난 캠페인 마이그레이션: {total_inserted}건 추가")
    return {
        "message": f"PRM 공익/재난 소재 {total_inserted}건이 공익재난으로 DB에 추가되었습니다.",
        "inserted": total_inserted,
    }


@router.post("/apst/migrate-label-gongikjaenan")
def migrate_label_to_gongikjaenan() -> dict:
    """
    기존에 '캠페인'으로 저장된 PRM 공익/재난 소재의 content_type_label을
    '공익재난'으로 일괄 변경 (소급 적용).
    대상: content_type = 'PRM' AND content_type_label = '캠페인'
          AND (item_name_raw에 '공익' 또는 '재난' 포함)
    """
    with get_apst_conn() as conn:
        cur = conn.execute(
            """UPDATE broadcasts
               SET content_type_label = '공익재난'
               WHERE content_type = 'PRM'
                 AND content_type_label = '캠페인'
                 AND (item_name_raw LIKE '%공익%' OR item_name_raw LIKE '%재난%')"""
        )
        updated = cur.rowcount

    log_event("info", "db_update", f"공익재난 소재종류 전환: {updated}건 변경")
    return {
        "message": f"공익/재난 소재 {updated}건이 '공익재난' 소재종류로 변경되었습니다.",
        "updated": updated,
    }


@router.post("/apst/clean-prm-names")
def clean_prm_names() -> dict:
    """
    기존 DB의 공익/재난 캠페인 소재명을 정제된 형식으로 일괄 업데이트.
    (공익)/(재난) 키워드를 맨 앞으로 이동, 특수문자 제거.
    """
    updated = 0
    with get_apst_conn() as conn:
        rows = conn.execute(
            "SELECT DISTINCT item_name FROM broadcasts "
            "WHERE content_type_label IN ('공익재난', '캠페인') "
            "AND (item_name LIKE '%공익%' OR item_name LIKE '%재난%')"
        ).fetchall()

        for row in rows:
            old_name = row["item_name"]
            new_name = clean_prm_campaign_name(old_name)
            if new_name != old_name:
                conn.execute(
                    "UPDATE broadcasts SET item_name = ? WHERE item_name = ?",
                    (new_name, old_name)
                )
                updated += 1

    log_event("info", "db_update", f"공익/재난 소재명 정제 완료: {updated}건 변경")
    return {
        "message": f"공익/재난 소재명 {updated}건이 정제되었습니다.",
        "updated": updated,
    }


# ── APST 디렉터리 전체 스캔 적재 ───────────────────────────────────────────

@router.post("/apst/scan")
def scan_apst_dir() -> dict:
    """
    환경설정의 apst_dir 폴더를 스캔하여 미처리 .apst 파일을 모두 적재.
    이미 처리된 파일(source_file 중복)은 건너뜀.
    """
    apst_dir = _get_setting("apst_dir")
    if not apst_dir:
        raise HTTPException(
            status_code=400,
            detail="환경설정에서 APST 파일 디렉터리(apst_dir)를 먼저 설정해 주세요."
        )

    dir_path = Path(apst_dir)
    if not dir_path.exists() or not dir_path.is_dir():
        log_event("error", "file_missing", f"APST 디렉터리를 찾을 수 없습니다: {apst_dir}")
        raise HTTPException(
            status_code=400,
            detail=f"디렉터리를 찾을 수 없습니다: {apst_dir}"
        )

    # 이미 처리된 파일명 목록
    with get_apst_conn() as conn:
        done = {
            r["source_file"]
            for r in conn.execute("SELECT DISTINCT source_file FROM broadcasts").fetchall()
        }

    apst_files = find_apst_files(dir_path, _apst_suffix())
    if not apst_files:
        raise HTTPException(status_code=404, detail=f"폴더에 .apst 파일이 없습니다: {apst_dir}")

    results = []
    total_inserted = 0
    total_manual_inserted = 0
    scanned_dates: set[str] = set()

    for fpath in apst_files:
        fname = fpath.name
        d = _date_from_filename(fname)
        if d:
            scanned_dates.add(d)
        if fname in done:
            results.append({"file": fname, "status": "skipped", "inserted": 0})
            continue
        try:
            records = parse_apst(str(fpath), source_file=fname)
            with get_apst_conn() as conn:
                _insert_apst_records(records, conn)
            total_inserted += len(records)

            segments = find_manual_segments(str(fpath))
            manual_inserted = _insert_manual_segments(segments)
            total_manual_inserted += manual_inserted

            results.append({
                "file": fname, "status": "ok",
                "inserted": len(records), "manual_inserted": manual_inserted,
            })
        except Exception as e:
            results.append({"file": fname, "status": "error", "message": str(e)})

    # 스캔한 날짜들의 달력 상태(붉은/파랑) 갱신
    # (파일 누락 + 소재명 미확인 수동송출 여부를 반영)
    from services.ftp_fetcher import refresh_fetch_status
    for d in scanned_dates:
        try:
            refresh_fetch_status(d)
        except Exception:
            pass

    if total_inserted or total_manual_inserted:
        log_event(
            "info", "db_insert",
            f"APST 전체 스캔 적재: {total_inserted}건 (수동 송출 {total_manual_inserted}건 포함)"
        )

    return {
        "message": f"{len(apst_files)}개 파일 스캔 완료.",
        "total_inserted": total_inserted,
        "total_manual_inserted": total_manual_inserted,
        "files": results,
    }


# ── DDR1 디렉터리 전체 스캔 적재 ───────────────────────────────────────────

@router.post("/ddr1/scan")
def scan_ddr1_dir() -> dict:
    """
    환경설정의 ddr1_dir 폴더를 스캔하여 미처리 .Log 파일을 모두 적재.
    파일명에서 날짜(YYYYMMDD)를 자동 추출. 추출 불가 파일은 건너뜀.
    """
    ddr1_dir = _get_setting("ddr1_dir")
    if not ddr1_dir:
        raise HTTPException(
            status_code=400,
            detail="환경설정에서 DDR1 파일 디렉터리(ddr1_dir)를 먼저 설정해 주세요."
        )

    dir_path = Path(ddr1_dir)
    if not dir_path.exists() or not dir_path.is_dir():
        raise HTTPException(
            status_code=400,
            detail=f"디렉터리를 찾을 수 없습니다: {ddr1_dir}"
        )

    # CML 맵 로드
    with get_ddr1_conn() as conn:
        rows = conn.execute("SELECT * FROM clip_map").fetchall()
    cml_map = {
        r["clip_id"]: {
            "full_name": r["full_name"],
            "advertiser": r["advertiser"],
            "duration_sec": r["duration_sec"],
        }
        for r in rows
    }
    if not cml_map:
        raise HTTPException(
            status_code=400,
            detail="clip_map이 비어 있습니다. CML 파일을 먼저 적재해 주세요."
        )

    campaign_names = get_campaign_names()

    # 이미 처리된 파일 목록
    with get_ddr1_conn() as conn:
        done = {
            r["source_file"]
            for r in conn.execute("SELECT DISTINCT source_file FROM broadcasts").fetchall()
        }

    log_files = sorted(dir_path.glob("*.Log")) + sorted(dir_path.glob("*.log"))
    if not log_files:
        raise HTTPException(status_code=404, detail=f"폴더에 .Log 파일이 없습니다: {ddr1_dir}")

    results = []
    total_inserted = 0

    for fpath in log_files:
        fname = fpath.name
        if fname in done:
            results.append({"file": fname, "status": "skipped", "inserted": 0})
            continue

        broadcast_date = _date_from_filename(fname)
        if not broadcast_date:
            results.append({
                "file": fname,
                "status": "skipped",
                "message": "파일명에서 날짜를 추출할 수 없습니다. (YYYYMMDD 형식 필요)"
            })
            continue

        try:
            exclude_windows = _find_manual_windows_for_date(broadcast_date)
            records = parse_ddr1(
                str(fpath),
                broadcast_date=broadcast_date,
                cml_map=cml_map,
                campaign_names=campaign_names,
                source_file=fname,
                exclude_windows=exclude_windows,
            )
            with get_ddr1_conn() as conn:
                conn.executemany(
                    """INSERT INTO broadcasts
                       (broadcast_date, broadcast_time, broadcast_hour,
                        clip_id, item_name_raw, item_name,
                        content_type_label, grade, duration_sec, source_file)
                       VALUES
                       (:broadcast_date, :broadcast_time, :broadcast_hour,
                        :clip_id, :item_name_raw, :item_name,
                        :content_type_label, :grade, :duration_sec, :source_file)""",
                    records,
                )
            total_inserted += len(records)
            results.append({
                "file": fname,
                "status": "ok",
                "broadcast_date": broadcast_date,
                "inserted": len(records),
            })
        except Exception as e:
            results.append({"file": fname, "status": "error", "message": str(e)})

    return {
        "message": f"{len(log_files)}개 파일 스캔 완료.",
        "total_inserted": total_inserted,
        "files": results,
    }


# ── 수동 송출 재추출 ─────────────────────────────────────────────────────────

@router.post("/ddr1/resync-manual")
def resync_manual_segments() -> dict:
    """
    수동 송출(DDR1) 누락 데이터 보완.
    DDR1 로그 파일이 있는 모든 날짜를 대상으로 APST 수동 송출 구간을 다시 추출한다.
    이미 적재된 구간(source_file="manual:로그:트리거ID")은 추출 전에 걸러내므로,
    과거에 일부만 적재된 날짜의 누락 구간도 새로 복구된다(구간 단위 중복검사).
    """
    apst_dir = _get_setting("apst_dir")
    ddr1_dir = _get_setting("ddr1_dir")

    if not apst_dir:
        raise HTTPException(status_code=400, detail="환경설정에서 APST 디렉터리(apst_dir)를 먼저 설정해 주세요.")
    if not ddr1_dir:
        raise HTTPException(status_code=400, detail="환경설정에서 DDR1 디렉터리(ddr1_dir)를 먼저 설정해 주세요.")

    apst_path = Path(apst_dir)
    ddr1_path = Path(ddr1_dir)

    if not apst_path.exists():
        raise HTTPException(status_code=400, detail=f"디렉터리를 찾을 수 없습니다: {apst_dir}")
    if not ddr1_path.exists():
        raise HTTPException(status_code=400, detail=f"디렉터리를 찾을 수 없습니다: {ddr1_dir}")

    # 1. DDR1 로그 파일이 있는 날짜 목록
    ddr1_dates: set[str] = set()
    for fpath in list(ddr1_path.glob("*.Log")) + list(ddr1_path.glob("*.log")):
        d = _date_from_filename(fpath.name)
        if d:
            ddr1_dates.add(d)

    if not ddr1_dates:
        return {"message": "DDR1 로그 파일이 없습니다.", "total_inserted": 0, "files": []}

    # 2. DDR1 로그가 있는 날짜의 APST 파일 전부 수집 (날짜별 다중 파일 허용)
    apst_files_by_date: dict[str, list[str]] = {}
    for fpath in find_apst_files(apst_path, _apst_suffix()):
        d = _date_from_filename(fpath.name)
        if d in ddr1_dates:
            apst_files_by_date.setdefault(d, []).append(str(fpath))

    if not apst_files_by_date:
        return {
            "message": f"DDR1 로그가 있는 날짜({len(ddr1_dates)}일)의 APST 파일을 찾을 수 없습니다.",
            "total_inserted": 0,
            "files": [],
        }

    # 3. 각 날짜의 수동 구간을 추출 → _insert_manual_segments (구간 단위 중복검사)
    total_manual_inserted = 0
    results = []

    for date in sorted(apst_files_by_date.keys()):
        try:
            segments = []
            for f in sorted(apst_files_by_date[date]):
                segments.extend(find_manual_segments(f))
            if not segments:
                continue
            inserted = _insert_manual_segments(segments)
            total_manual_inserted += inserted
            if inserted > 0:
                results.append({"date": date, "inserted": inserted})
        except Exception as e:
            results.append({"date": date, "error": str(e)})

    log_event("info", "db_insert", f"수동 송출 재추출 완료: {total_manual_inserted}건 추가")
    return {
        "message": f"수동 송출 데이터 {total_manual_inserted}건이 추가되었습니다.",
        "total_inserted": total_manual_inserted,
        "files": results,
    }


# ── 폴더 감시 제어 ──────────────────────────────────────────────────────────

@router.get("/watcher")
def watcher_status() -> dict:
    """폴더 감시 현황 조회."""
    from services.file_watcher import get_watcher_status
    return get_watcher_status()


@router.post("/watcher/start")
def watcher_start() -> dict:
    """폴더 실시간 감시 시작."""
    from services.file_watcher import start_watching
    return start_watching()


@router.post("/watcher/stop")
def watcher_stop() -> dict:
    """폴더 실시간 감시 중지."""
    from services.file_watcher import stop_watching
    return stop_watching()


@router.get("/watcher/log")
def watcher_log() -> list:
    """감시 이벤트 로그 조회 (최근 100건)."""
    from services.file_watcher import get_watch_log
    return get_watch_log()


# ── 적재 현황 ───────────────────────────────────────────────────────────────

@router.get("/status")
def ingest_status() -> dict:
    """현재 DB 적재 현황: 날짜 범위, 총 건수, 파일 수."""
    with get_apst_conn() as conn:
        apst = conn.execute("""
            SELECT COUNT(*) as total,
                   COUNT(DISTINCT source_file) as files,
                   MIN(broadcast_date) as from_date,
                   MAX(broadcast_date) as to_date
            FROM broadcasts
        """).fetchone()

    with get_ddr1_conn() as conn:
        ddr1 = conn.execute("""
            SELECT COUNT(*) as total,
                   COUNT(DISTINCT source_file) as files,
                   MIN(broadcast_date) as from_date,
                   MAX(broadcast_date) as to_date
            FROM broadcasts
        """).fetchone()

    return {
        "apst": {
            "total": apst["total"],
            "files": apst["files"],
            "from_date": apst["from_date"],
            "to_date": apst["to_date"],
        },
        "ddr1": {
            "total": ddr1["total"],
            "files": ddr1["files"],
            "from_date": ddr1["from_date"],
            "to_date": ddr1["to_date"],
        },
    }
