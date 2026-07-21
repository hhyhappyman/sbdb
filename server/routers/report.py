"""
Report router — F-04, F-06(방송 운행표), F-07, 일일 운행표/일일 ID 운행표
GET /api/report?item=소재명&year=2026&month=05         → F-04 데이터
GET /api/report/pdf?item=소재명&year=2026&month=05     → F-04 PDF 다운로드
GET /api/report/daily?date=2026-05-06                  → 방송 운행표 데이터 (구 일별 SB내역)
GET /api/report/daily/pdf?date=2026-05-06              → 방송 운행표 PDF 다운로드
GET /api/report/disaster?date=2026-05-06               → F-07 데이터
GET /api/report/disaster/pdf?date=2026-05-06           → F-07 PDF 다운로드
GET /api/report/daily-summary?date=&type=캠페인|ID      → 일일 운행표 / 일일 ID 운행표
"""

import re
import sqlite3
import calendar
import holidays
from datetime import date as date_cls, timedelta
from pathlib import Path

from fastapi import APIRouter, Query, HTTPException
from fastapi.responses import FileResponse

from services.aggregator import (
    get_item_monthly_report, get_daily_item_summary, get_campaign_names,
    get_apst_name_map, get_apst_name_before,
)
from services.pdf_generator import (
    generate_monthly_pdf,
    generate_daily_pdf,
    generate_disaster_pdf,
    generate_daily_summary_pdf,
    generate_subtitle_campaign_pdf,
)
from services.excel_generator import generate_gongik_jaenan_xlsx
from services.docx_generator import (
    generate_monthly_docx,
    generate_daily_docx,
    generate_daily_summary_docx,
    generate_subtitle_campaign_docx,
)

_DOCX_MEDIA = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
from services.activity_log import log_event
from parsers.apst_parser import parse_apst_all, find_manual_segments
from parsers.ddr1_parser import extract_manual_clips, classify_ddr1_clip, _guess_label_by_clip
from parsers.cml_parser import parse_cml, resolve_cml_path_for_date
from parsers.utils import (
    classify_grade, clean_prm_campaign_name, extract_item_name,
    find_apst_files,
)
from database import get_apst_conn, get_ddr1_conn
from config import APST_DB_PATH, APST_SUFFIX_DEFAULT

router = APIRouter(prefix="/api/report", tags=["report"])


# ── F-04 : 소재별 월 리포트 ─────────────────────────────────────────────────

@router.get("")
def monthly_report(
    item:  str = Query(..., description="소재명 (정제된 이름)"),
    year:  int = Query(...),
    month: int = Query(..., ge=1, le=12),
) -> dict:
    """F-04 — 소재별 월 송출 내역 조회."""
    rows = get_item_monthly_report(item, year, month)
    total = sum(r["count"] for r in rows)
    return {
        "item_name": item,
        "year":  year,
        "month": month,
        "total": total,
        "days":  rows,
    }


def _sanitize_filename(name: str) -> str:
    return str(name).replace("/", "_").replace("\\", "_").strip()[:80] or "리포트"


def _prepare_monthly_data(item: str, year: int, month: int, content: str | None = None):
    """
    소재별 월 리포트 데이터 준비. item에 ', '가 있으면 여러 소재로 보고
    날짜별로 송출 시간/횟수를 병합한다.

    데이터 조회는 item(검색 소재명)으로 하고, 리포트의 '송출 내용' 표시 문구와
    파일명은 content(사용자가 저장 시 입력)를 사용한다. content가 없으면 소재명을 그대로 쓴다.
    광고주 정보는 더 이상 사용하지 않고 송출매체·비고는 기본값을 쓴다(advertiser={}).

    반환: (days, advertiser, settings, display_name, file_name)
    """
    names = [s.strip() for s in item.split(", ") if s.strip()]

    conn = sqlite3.connect(APST_DB_PATH)
    conn.row_factory = sqlite3.Row
    settings = {r["key"]: r["value"] for r in conn.execute("SELECT key, value FROM app_settings").fetchall()}
    conn.close()

    # 날짜별 병합 (단일/다중 공통)
    day_map: dict = {}
    for n in (names or [item]):
        for d in get_item_monthly_report(n, year, month):
            e = day_map.get(d["date"])
            if e:
                e["times"] = sorted(e["times"] + d["times"])
                e["count"] += d["count"]
            else:
                day_map[d["date"]] = {"date": d["date"], "times": list(d["times"]), "count": d["count"]}
    days = [day_map[k] for k in sorted(day_map)]

    display = (content or "").strip() or ", ".join(names) or item
    file_name = _sanitize_filename(display)
    return days, {}, settings, display, file_name


@router.get("/pdf")
def monthly_report_pdf(
    item:    str = Query(...),
    year:    int = Query(...),
    month:   int = Query(..., ge=1, le=12),
    content: str | None = Query(None, description="'송출 내용' 표시 문구 (없으면 소재명)"),
) -> FileResponse:
    """F-04 — PDF 생성 후 다운로드 (여러 소재는 병합)."""
    days, advertiser, settings, display, fname = _prepare_monthly_data(item, year, month, content)

    pdf_path = generate_monthly_pdf(
        item_name=display, year=year, month=month,
        days=days, advertiser=advertiser, settings=settings,
    )
    filename = f"SB송출현황_{fname}_{year}{month:02d}.pdf"
    return FileResponse(path=pdf_path, media_type="application/pdf", filename=filename)


@router.get("/word")
def monthly_report_word(
    item:    str = Query(...),
    year:    int = Query(...),
    month:   int = Query(..., ge=1, le=12),
    content: str | None = Query(None, description="'송출 내용' 표시 문구 (없으면 소재명)"),
) -> FileResponse:
    """F-04 — Word(.docx) 생성 후 다운로드 (여러 소재는 병합)."""
    days, advertiser, settings, display, fname = _prepare_monthly_data(item, year, month, content)

    docx_path = generate_monthly_docx(display, year, month, days, advertiser, settings)
    filename = f"SB송출현황_{fname}_{year}{month:02d}.docx"
    return FileResponse(path=docx_path, media_type=_DOCX_MEDIA, filename=filename)


# ── 공통: apst_dir에서 날짜에 해당하는 파일 목록 조회 ──────────────────────

def _get_settings() -> dict:
    conn = sqlite3.connect(APST_DB_PATH)
    conn.row_factory = sqlite3.Row
    rows = conn.execute("SELECT key, value FROM app_settings").fetchall()
    conn.close()
    return {r["key"]: r["value"] for r in rows}


# 방송일 기준 시작 시간 (04:30 이전은 전날 방송일의 심야 연장분으로 처리)
_BROADCAST_DAY_START_SEC = 4 * 3600 + 30 * 60  # 04:30:00 = 16200초


def _time_to_sec(time_str: str) -> int:
    h, m, s = (int(x) for x in time_str.split(":"))
    return h * 3600 + m * 60 + s


def _broadcast_sort_key(time_str: str) -> int:
    """
    방송일 기준 정렬 키. 04:30 이전 시간은 +24시간으로 환산해 맨 뒤로 보냄.
    예: 04:30 → 16200, 23:59 → 86340, 00:00 → 86400, 04:29 → 102540
    """
    sec = _time_to_sec(time_str)
    if sec < _BROADCAST_DAY_START_SEC:
        sec += 86400
    return sec


def _to_display_time(time_str: str) -> str:
    """
    방송일 기준 표시 시간. 04:30 이전은 24시간을 더해서 표시.
    예: 00:34:20 → 24:34:20 / 01:10:44 → 25:10:44
    """
    h, m, s = (int(x) for x in time_str.split(":"))
    if h * 3600 + m * 60 + s < _BROADCAST_DAY_START_SEC:
        h += 24
    return f"{h:02d}:{m:02d}:{s:02d}"


def _find_apst_files_for_date(date: str) -> list[str]:
    """
    환경설정의 apst_dir에서 해당 날짜의 APST 파일들을 모두 찾아 반환.
    date: 'YYYY-MM-DD'
    """
    settings = _get_settings()
    apst_dir = settings.get("apst_dir", "")
    if not apst_dir:
        raise HTTPException(
            status_code=400,
            detail="환경설정에서 APST 파일 디렉터리(apst_dir)를 먼저 설정해 주세요."
        )

    dir_path = Path(apst_dir)
    if not dir_path.exists():
        raise HTTPException(status_code=400, detail=f"디렉터리를 찾을 수 없습니다: {apst_dir}")

    suffix = settings.get("apst_suffix") or APST_SUFFIX_DEFAULT
    return [str(f) for f in find_apst_files(dir_path, suffix, date)]


def _find_ddr1_log_for_date(date: str) -> str | None:
    """환경설정의 ddr1_dir에서 해당 날짜의 DDR1 로그 파일을 찾는다. 없으면 None."""
    settings = _get_settings()
    ddr1_dir = settings.get("ddr1_dir", "")
    if not ddr1_dir:
        return None
    dir_path = Path(ddr1_dir)
    if not dir_path.exists():
        return None
    date_nodash = date.replace("-", "")
    for f in list(dir_path.glob("*.Log")) + list(dir_path.glob("*.log")):
        if date_nodash in f.name:
            return str(f)
    return None


def _expand_manual_items(all_items: list[dict], files: list[str], date: str) -> list[dict]:
    """
    주장비명(MM)이 DDR1인 이어서 소재를, 그 시간 동안 실제로 수동 송출된 소재
    전체(캠페인/ID)로 확장한다 (방송 운행표 F-06용). 이어서 행은 그대로 두고,
    실제 송출된 캠페인/ID 소재들을 추가로 끼워 넣는다.
    """
    manual_triggers = {
        item["src_id"]
        for item in all_items
        if item.get("con") == "C" and item.get("main_equipment") == "DDR1"
    }
    if not manual_triggers:
        return all_items

    segments = []
    for fpath in files:
        try:
            segments.extend(find_manual_segments(fpath))
        except Exception:
            continue
    segments = [s for s in segments if s["trigger_clip_id"] in manual_triggers]
    if not segments:
        return all_items

    # 당일 / 다음날 DDR1 로그 파일 경로를 미리 준비
    # APST 파일의 04:30 이전(00:00~04:29) 세그먼트는 다음날 달력 날짜의 로그 파일에 기록됨
    next_date = (date_cls.fromisoformat(date) + timedelta(days=1)).isoformat()
    log_path_same = _find_ddr1_log_for_date(date)
    log_path_next = _find_ddr1_log_for_date(next_date)

    if not log_path_same and not log_path_next:
        log_event("warning", "file_missing", f"DDR1 로그 파일을 찾을 수 없습니다 (날짜: {date})")
        return all_items

    prev_date = (date_cls.fromisoformat(date) - timedelta(days=1)).isoformat()
    cml_setting = _get_settings().get("cml_path", "")
    # CML은 날짜별로 로드 (전날 / 당일 / 다음날 분리)
    cml_file_prev = resolve_cml_path_for_date(cml_setting, prev_date)
    cml_file_same = resolve_cml_path_for_date(cml_setting, date)
    cml_file_next = resolve_cml_path_for_date(cml_setting, next_date)
    cml_map_prev: dict = parse_cml(cml_file_prev) if cml_file_prev else {}
    cml_map_same: dict = parse_cml(cml_file_same) if cml_file_same else {}
    cml_map_next: dict = parse_cml(cml_file_next) if cml_file_next else {}

    campaign_names = get_campaign_names()
    # CML에 없는 clip_id 보완용 — 당일/다음날 자동송출(apst.db) 소재명
    _apst_map = get_apst_name_map({date, next_date})
    apst_map_same = _apst_map.get(date, {})
    apst_map_next = _apst_map.get(next_date, {})

    extra_items = []
    for seg in segments:
        # 세그먼트 시작 시간이 04:30 이전이면 다음날 로그·CML 사용
        is_next_day = _time_to_sec(seg["start_time"]) < _BROADCAST_DAY_START_SEC
        log_path = log_path_next if is_next_day else log_path_same
        cml_map  = cml_map_next  if is_next_day else cml_map_same
        apst_map = apst_map_next if is_next_day else apst_map_same
        # 어제 CML: 당일이 다음날이면 어제는 곧 date의 CML, 아니면 전날 CML
        cml_map_yest = cml_map_same if is_next_day else cml_map_prev

        if not log_path:
            log_event(
                "warning", "file_missing",
                f"DDR1 로그 파일을 찾을 수 없습니다 "
                f"(날짜: {next_date if is_next_day else date}, 세그먼트: {seg['start_time']})"
            )
            continue

        clips = extract_manual_clips(
            log_path,
            trigger_clip_id=seg["trigger_clip_id"],
            start_time=seg["start_time"],
            end_time=seg["end_time"],
        )
        for time_str, clip_id, clip_dur in clips:
            if clip_id in cml_map:
                label, raw_name, clean_name = classify_ddr1_clip(clip_id, cml_map, campaign_names)
                if label is None:
                    # 캠페인/ID로 분류되지 않는 항목(주로 CM######## 지역 광고)도
                    # 방송 운행표에는 실제 송출된 그대로 표시 — '광고'로 분류
                    entry = cml_map[clip_id]
                    label, raw_name, clean_name = "광고", entry["full_name"], entry["full_name"]
            elif clip_id in apst_map:
                # 당일 CML에 없으면 같은 날짜 자동송출(apst.db) 소재명으로 보완
                entry = apst_map[clip_id]
                raw_name = entry.get("item_name_raw") or clip_id
                clean_name = entry.get("item_name") or clip_id
                label = entry.get("content_type_label") or "캠페인"
            elif clip_id in cml_map_yest:
                # 어제 날짜 CML에서 보완
                label, raw_name, clean_name = classify_ddr1_clip(clip_id, cml_map_yest, campaign_names)
                if label is None:
                    entry = cml_map_yest[clip_id]
                    label, raw_name, clean_name = "광고", entry["full_name"], entry["full_name"]
            else:
                # 날짜 무관 자동송출 DB — 기준일(항목 날짜) 이전 가장 가까운 날짜 소재명
                item_date = next_date if is_next_day else date
                entry = get_apst_name_before(clip_id, item_date)
                if entry:
                    raw_name = entry.get("item_name_raw") or clip_id
                    clean_name = entry.get("item_name") or clip_id
                    label = entry.get("content_type_label") or "캠페인"
                else:
                    # 소재명 미확인 → clip_id 규칙으로 소재종류 추정 (CM=광고, N 15초=ID)
                    raw_name, clean_name = clip_id, clip_id
                    label, _ = _guess_label_by_clip(clip_id, clip_dur)
            extra_items.append({
                "broadcast_date":        date,
                "broadcast_time":        time_str,
                "broadcast_time_display": _to_display_time(time_str),
                "program_block":         seg["program_block"],
                "item_name_raw":         raw_name,
                "item_name":             clean_name,
                "src_id":                clip_id,
                "con":                   "K" if label == "캠페인" else ("I" if label == "ID" else "G"),
                "main_equipment":        "DDR1",
                "content_type_label":    label,
            })

    if not extra_items:
        return all_items

    combined = all_items + extra_items
    combined.sort(key=lambda x: _broadcast_sort_key(x["broadcast_time"]))
    return combined


# 소재제목에 독립된 'ID' 토큰(방송국 ID 소재) 판별용
_ID_TOKEN_RE = re.compile(r"\bID\b")


def _parse_all_for_date(date: str) -> list[dict]:
    """
    해당 날짜의 APST 파일 전체를 파싱해 방송일 순서대로 반환.

    방송일은 당일 04:30 시작 → 익일 04:30 미만 종료 구조이므로,
    파일 내 00:00~04:29 구간 소재는 당일 심야 연장분(24시 이후)으로 간주한다.
    - broadcast_time: 파일 원본 시간 (HH:MM:SS, DB 저장·검색용)
    - broadcast_time_display: 표시 시간 (04:30 이전은 +24h, 예: 24:34:20)
    정렬은 broadcast_time_display 기준으로 04:30 → 23:59 → 24:00(=00:00) 순.
    """
    files = _find_apst_files_for_date(date)
    if not files:
        log_event("warning", "file_missing", f"{date} 날짜에 해당하는 APST 파일이 없습니다.")
        raise HTTPException(
            status_code=404,
            detail=f"{date} 날짜에 해당하는 APST 파일이 없습니다."
        )

    all_items = []
    seen = set()
    for fpath in files:
        items = parse_apst_all(fpath)
        for item in items:
            # 소재명이 빈 칸인 행은 제외 (방송완제/구분용 빈 아이템 등)
            if not item["item_name_raw"].strip():
                continue
            # 동일 시간+소재명 중복 제거
            key = (item["broadcast_time"], item["item_name_raw"])
            if key not in seen:
                seen.add(key)
                item["broadcast_time_display"] = _to_display_time(item["broadcast_time"])
                all_items.append(item)

    # 방송일 기준 정렬: 04:30 이전 항목은 +24h 처리되어 맨 뒤로
    all_items.sort(key=lambda x: _broadcast_sort_key(x["broadcast_time"]))
    all_items = _expand_manual_items(all_items, files, date)

    # 방송 운행표 소재종류 표시 규칙 (수동송출 확장 항목까지 포함):
    #  - 원래 공익재난 소재(PRM·R 등)는 공익재난으로 표시. 캠페인(K)은 그대로 캠페인.
    #  - 단, '방송 종료 안내' 프로그램에서는 소재종류와 상관없이
    #    소재명에 공익/재난이 포함되면 공익재난으로 표시한다.
    for item in all_items:
        raw = item.get("item_name_raw") or ""
        # 방송개시/방송종료의 방송국 ID 소재: 소재제목에 독립된 'ID' 토큰이 있으면
        # 소재종류(con)가 I가 아니어도 'ID'로 표시한다.
        if _ID_TOKEN_RE.search(raw):
            item["content_type_label"] = "ID"
            continue
        if "공익" not in raw and "재난" not in raw:
            continue
        prog = item.get("program_block") or ""
        is_end_notice = "방송 종료" in prog or "방송종료" in prog
        if is_end_notice or item.get("con") not in ("AIR", "C", "G", "K"):
            item["content_type_label"] = "공익재난"

    # 04:30~04:44:59 구간 제외 — 04:45 방송순서안내부터 표시
    _DISPLAY_START_SEC = 4 * 3600 + 45 * 60  # 04:45:00
    all_items = [
        i for i in all_items
        if not (_BROADCAST_DAY_START_SEC <= _time_to_sec(i["broadcast_time"]) < _DISPLAY_START_SEC)
    ]
    return all_items


# ── F-06 : 일별 프로그램-SB 내역 ───────────────────────────────────────────

@router.get("/daily")
def daily_report(date: str = Query(..., description="YYYY-MM-DD")) -> dict:
    """F-06 — 일별 SB 전체 내역 조회 (apst_dir 자동 사용)."""
    items = _parse_all_for_date(date)
    return {
        "date":  date,
        "total": len(items),
        "items": items,
    }


@router.get("/daily/pdf")
def daily_report_pdf(
    date: str = Query(..., description="YYYY-MM-DD"),
) -> FileResponse:
    """F-06 — 일별 SB 내역 PDF 생성 및 다운로드 (apst_dir 자동 사용)."""
    items    = _parse_all_for_date(date)
    settings = _get_settings()
    pdf_path = generate_daily_pdf(date=date, items=items, settings=settings)

    filename = f"방송운행표_{date.replace('-', '')}.pdf"
    return FileResponse(path=pdf_path, media_type="application/pdf", filename=filename)


@router.get("/daily/word")
def daily_report_word(date: str = Query(..., description="YYYY-MM-DD")) -> FileResponse:
    """방송 운행표 — Word(.docx) 생성 및 다운로드."""
    items = _parse_all_for_date(date)
    settings = _get_settings()
    docx_path = generate_daily_docx(date=date, items=items, settings=settings)
    filename = f"방송운행표_{date.replace('-', '')}.docx"
    return FileResponse(path=docx_path, media_type=_DOCX_MEDIA, filename=filename)


# ── F-07 : 일별 재난방송 소재 ──────────────────────────────────────────────

@router.get("/disaster")
def disaster_report(date: str = Query(..., description="YYYY-MM-DD")) -> dict:
    """F-07 — 재난방송 소재 조회 ('재난' 포함 항목, apst_dir 자동 사용)."""
    all_items = _parse_all_for_date(date)
    items = [r for r in all_items if "재난" in r.get("item_name_raw", "")]
    return {
        "date":  date,
        "total": len(items),
        "items": items,
    }


@router.get("/disaster/pdf")
def disaster_report_pdf(
    date: str = Query(..., description="YYYY-MM-DD"),
) -> FileResponse:
    """F-07 — 재난방송 PDF 생성 및 다운로드. 소재 없으면 빈 PDF 생성."""
    all_items = _parse_all_for_date(date)
    items     = [r for r in all_items if "재난" in r.get("item_name_raw", "")]
    settings  = _get_settings()

    pdf_path = generate_disaster_pdf(date=date, items=items, settings=settings)

    filename = f"disaster_{date.replace('-', '')}.pdf"
    return FileResponse(path=pdf_path, media_type="application/pdf", filename=filename)


# ── 일일 운행표 / 일일 ID 운행표 ────────────────────────────────────────────

@router.get("/daily-summary")
def daily_summary(
    date: str = Query(..., description="YYYY-MM-DD"),
    type: str = Query(..., description="캠페인 | ID"),
) -> dict:
    """
    일일 운행표(캠페인) / 일일 ID 운행표(ID).
    소재별 총횟수 + 급지(SA/A/B/C)별 횟수.
    """
    if type not in ("캠페인", "ID"):
        raise HTTPException(status_code=400, detail="type은 '캠페인' 또는 'ID'여야 합니다.")

    rows = get_daily_item_summary(date, content_type_label=type)
    total = sum(r["total_count"] for r in rows)

    return {
        "date":  date,
        "type":  type,
        "total": total,
        "items": rows,
    }


@router.get("/daily-summary/pdf")
def daily_summary_pdf(
    date: str = Query(..., description="YYYY-MM-DD"),
    type: str = Query(..., description="캠페인 | ID"),
) -> FileResponse:
    """일일 운행표(캠페인) / 일일 ID 운행표(ID) PDF 생성 및 다운로드."""
    if type not in ("캠페인", "ID"):
        raise HTTPException(status_code=400, detail="type은 '캠페인' 또는 'ID'여야 합니다.")

    rows = get_daily_item_summary(date, content_type_label=type)
    pdf_path = generate_daily_summary_pdf(date=date, type_label=type, items=rows)

    prefix = "일일ID운행표" if type == "ID" else "일일운행표"
    filename = f"{prefix}_{date.replace('-', '')}.pdf"
    return FileResponse(path=pdf_path, media_type="application/pdf", filename=filename)


@router.get("/daily-summary/word")
def daily_summary_word(
    date: str = Query(..., description="YYYY-MM-DD"),
    type: str = Query(..., description="캠페인 | ID"),
) -> FileResponse:
    """일일 운행표 / 일일 ID 운행표 — Word(.docx) 생성 및 다운로드."""
    if type not in ("캠페인", "ID"):
        raise HTTPException(status_code=400, detail="type은 '캠페인' 또는 'ID'여야 합니다.")
    rows = get_daily_item_summary(date, content_type_label=type)
    docx_path = generate_daily_summary_docx(date=date, type_label=type, items=rows)
    prefix = "일일ID운행표" if type == "ID" else "일일운행표"
    filename = f"{prefix}_{date.replace('-', '')}.docx"
    return FileResponse(path=docx_path, media_type=_DOCX_MEDIA, filename=filename)


# ── 흘림자막·공익광고·재난피해 사전예방 송출내역 ────────────────────────────────

def _parse_duration_from_name(raw: str) -> int:
    """소재명(raw)에 포함된 '(N분M초)', '(N분)', '(N초)' 표현에서 초 단위 추출."""
    m = re.search(r'\((\d+)\s*분\s*(\d+)\s*초\)', raw)
    if m:
        return int(m.group(1)) * 60 + int(m.group(2))
    m = re.search(r'\((\d+)\s*분\)', raw)
    if m:
        return int(m.group(1)) * 60
    m = re.search(r'\((\d+)\s*초\)', raw)
    if m:
        return int(m.group(1))
    return 0


def _campaign_display_name(raw: str) -> str:
    """공익/재난 소재명 정제 후 앞쪽 '(공익)'/'(재난)' 접두어 제거 (표 표시용)."""
    name = clean_prm_campaign_name(extract_item_name(raw))
    name = re.sub(r'^\((?:공익|재난)\)\s*', '', name)
    # 접두어 제거 후 남는 앞쪽 문장부호(쉼표 등) 정리
    name = re.sub(r'^[,\s\-]+', '', name)
    return name.strip()


def _parse_calendar_date_items(date: str) -> list[dict]:
    """
    달력 날짜(00:00~24:00) 기준으로 해당 날짜에 송출된 APST 항목을 반환.
    방송일 파일은 04:30~익일04:30 구조라, 달력 날짜 D의 항목은
    D 파일(D 04:30~23:59)과 D-1 파일(D 00:00~04:29)에 나뉘어 있으므로
    두 파일을 모두 파싱해 broadcast_date == D 인 항목만 추린다.
    """
    prev_date = (date_cls.fromisoformat(date) - timedelta(days=1)).isoformat()
    files: list[str] = []
    for d in (prev_date, date):
        try:
            files.extend(_find_apst_files_for_date(d))
        except HTTPException:
            continue

    items: list[dict] = []
    seen: set = set()
    for fpath in files:
        for item in parse_apst_all(fpath):
            if item["broadcast_date"] != date:
                continue
            if not item["item_name_raw"].strip():
                continue
            key = (item["broadcast_time"], item["item_name_raw"])
            if key in seen:
                continue
            seen.add(key)
            items.append(item)
    items.sort(key=lambda x: x["broadcast_time"])
    return items


def _split_keywords(raw: str | None) -> list[str]:
    """콤마/줄바꿈으로 구분된 키워드 문자열을 리스트로 변환."""
    if not raw:
        return []
    return [w.strip() for w in raw.replace("\n", ",").split(",") if w.strip()]


def _get_gj_keywords() -> tuple[list[str], list[str], list[str]]:
    """
    환경설정에서 공익/재난 포함·제외 키워드를 읽어
    (공익 포함, 재난 포함, 제외) 리스트를 반환한다.
    """
    keys = ("gongik_include_keywords", "jaenan_include_keywords",
            "gongik_jaenan_exclude_keywords")
    with get_apst_conn() as conn:
        rows = conn.execute(
            f"SELECT key, value FROM app_settings WHERE key IN ({','.join('?' * len(keys))})",
            keys,
        ).fetchall()
    s = {r["key"]: r["value"] for r in rows}
    # 저장된 값을 그대로 사용 (빈 값이면 키워드 없음 — 사용자가 비울 수 있도록).
    # 기본값(학교폭력예방 등)은 최초 설치 시 DB 시딩(init_db)으로만 채운다.
    gongik = _split_keywords(s.get("gongik_include_keywords"))
    jaenan = _split_keywords(s.get("jaenan_include_keywords"))
    exclude = _split_keywords(s.get("gongik_jaenan_exclude_keywords"))
    return gongik, jaenan, exclude


def _query_gongik_jaenan_db(date_pattern: str) -> list[dict]:
    """
    apst.db + ddr1.db에서 공익/재난 소재를 조회한다.
    date_pattern: SQL LIKE 패턴 (예: '2026-07-%' 또는 '2026-07-02').

    apst.db  : content_type_label='공익재난'  또는
               캠페인(K) 이면서 소재명에 공익/재난 + 환경설정 포함 키워드
    ddr1.db  : 소재명(raw/정제)에 공익/재난 + 환경설정 포함 키워드
    환경설정 제외 키워드가 소재명에 있으면 결과에서 제외한다.
    각 행에 '_gj_kind'('공익'/'재난') 분류 결과를 붙여 반환한다.
    """
    gongik_kw, jaenan_kw, exclude_kw = _get_gj_keywords()
    # 소재명 매칭 키워드: 기본 공익/재난 + 포함 키워드 (중복 제거, 순서 유지)
    match_kw: list[str] = []
    for k in ["공익", "재난"] + gongik_kw + jaenan_kw:
        if k not in match_kw:
            match_kw.append(k)

    _COLS = "broadcast_date, broadcast_time, item_name_raw, item_name, duration_sec, grade"
    rows: list[dict] = []

    raw_like = " OR ".join("item_name_raw LIKE ?" for _ in match_kw)
    raw_params = [f"%{k}%" for k in match_kw]
    with get_apst_conn() as conn:
        for r in conn.execute(
            f"""SELECT {_COLS} FROM broadcasts
                WHERE broadcast_date LIKE ?
                  AND ( content_type_label = '공익재난'
                     OR ( content_type_label = '캠페인' AND ( {raw_like} ) ) )""",
            (date_pattern, *raw_params),
        ).fetchall():
            rows.append(dict(r))

    name_like = " OR ".join("item_name_raw LIKE ? OR item_name LIKE ?" for _ in match_kw)
    name_params: list[str] = []
    for k in match_kw:
        name_params += [f"%{k}%", f"%{k}%"]
    with get_ddr1_conn() as conn:
        for r in conn.execute(
            f"""SELECT {_COLS} FROM broadcasts
                WHERE broadcast_date LIKE ? AND ( {name_like} )""",
            (date_pattern, *name_params),
        ).fetchall():
            rows.append(dict(r))

    # 제외 키워드 필터 + 공익/재난 분류 (재난 우선)
    result: list[dict] = []
    for r in rows:
        text = f"{r['item_name_raw'] or ''} {r['item_name'] or ''}"
        if any(x in text for x in exclude_kw):
            continue
        is_jaenan = ("재난" in text) or any(k in text for k in jaenan_kw)
        r["_gj_kind"] = "재난" if is_jaenan else "공익"
        result.append(r)
    return result


def _gather_subtitle_campaign(date: str) -> dict:
    """흘림자막·공익광고·재난피해 사전예방 송출내역 집계 (DB 기반 + 수동입력 DB)."""
    auto_items = _parse_calendar_date_items(date)

    # ── UHD방송홍보 영상: 소재명에 'UHD' 포함 (자동송출 파일) ──
    uhd_video = [
        {"time": it["broadcast_time"], "program": it.get("program_block", "") or ""}
        for it in auto_items
        if "UHD" in it["item_name_raw"]
    ]
    # 수동송출(DDR1) DB에서도 UHD 검색 (프로그램명 없음)
    with get_ddr1_conn() as conn:
        for r in conn.execute(
            "SELECT broadcast_time FROM broadcasts WHERE broadcast_date = ? AND item_name LIKE '%UHD%' ORDER BY broadcast_time",
            (date,),
        ).fetchall():
            uhd_video.append({"time": r["broadcast_time"], "program": ""})
    uhd_video.sort(key=lambda x: x["time"])

    # ── 공익광고 / 재난피해 ──
    # apst.db(공익재난 + 캠페인K 공익/재난) + ddr1.db(수동송출 공익/재난)에서 조회.
    campaign: list[dict] = []
    disaster: list[dict] = []
    for r in _query_gongik_jaenan_db(date):
        raw = r["item_name_raw"] or ""
        name = r["item_name"] or ""
        entry = {
            "time": r["broadcast_time"],
            "program": _campaign_display_name(raw or name),
            "duration": r["duration_sec"] or _parse_duration_from_name(raw),
            "grade": r["grade"] or classify_grade(r["broadcast_time"]) or "",
        }
        if r["_gj_kind"] == "재난":
            disaster.append(entry)
        else:
            campaign.append(entry)

    # ── 수동입력(DB): 흘림자막 3종 + 공익재난 + 공익광고 근무자 ──
    with get_apst_conn() as conn:
        def _manual_subtitle(title: str) -> list[dict]:
            return [
                {"time": r["broadcast_time"], "program": r["program_name"] or ""}
                for r in conn.execute(
                    """SELECT broadcast_time, program_name FROM manual_entries
                       WHERE broadcast_date = ? AND content_type = '흘림자막' AND item_title = ?
                       ORDER BY broadcast_time""",
                    (date, title),
                ).fetchall()
            ]

        uhd_sub        = _manual_subtitle("UHD방송홍보")
        tv_direct      = _manual_subtitle("TV직접수신")
        viewer_opinion = _manual_subtitle("시청자의견")

        # 수동입력 공익재난도 공익/재난 표에 합산
        for r in conn.execute(
            """SELECT broadcast_time, program_name, item_title, grade FROM manual_entries
               WHERE broadcast_date = ? AND content_type = '공익재난'
               ORDER BY broadcast_time""",
            (date,),
        ).fetchall():
            title = r["item_title"] or ""
            entry = {"time": r["broadcast_time"], "program": title,
                     "duration": 0, "grade": r["grade"] or ""}
            if "공익" in title:
                campaign.append(entry)
            elif "재난" in title:
                disaster.append(entry)

        cw = conn.execute(
            "SELECT worker_name FROM campaign_worker WHERE broadcast_date = ?", (date,)
        ).fetchone()
        campaign_worker = cw["worker_name"] if cw else ""

    campaign.sort(key=lambda x: x["time"])
    disaster.sort(key=lambda x: x["time"])

    return {
        "date": date,
        "campaign_worker": campaign_worker,
        "uhd_video": uhd_video,
        "uhd_sub": uhd_sub,
        "tv_direct": tv_direct,
        "viewer_opinion": viewer_opinion,
        "campaign": campaign,
        "disaster": disaster,
    }


@router.get("/subtitle-campaign")
def subtitle_campaign_report(date: str = Query(..., description="YYYY-MM-DD")) -> dict:
    """흘림자막·공익·재난 송출내역 조회 (화면 표출용)."""
    return _gather_subtitle_campaign(date)


@router.get("/subtitle-campaign/pdf")
def subtitle_campaign_report_pdf(date: str = Query(..., description="YYYY-MM-DD")) -> FileResponse:
    """흘림자막·공익·재난 송출내역 PDF 생성 및 다운로드."""
    data = _gather_subtitle_campaign(date)
    pdf_path = generate_subtitle_campaign_pdf(data)
    filename = f"흘림자막,공익재난송출내역_{date.replace('-', '')}.pdf"
    return FileResponse(path=pdf_path, media_type="application/pdf", filename=filename)


@router.get("/subtitle-campaign/word")
def subtitle_campaign_report_word(date: str = Query(..., description="YYYY-MM-DD")) -> FileResponse:
    """흘림자막·공익·재난 송출내역 — Word(.docx) 생성 및 다운로드."""
    data = _gather_subtitle_campaign(date)
    docx_path = generate_subtitle_campaign_docx(data)
    filename = f"흘림자막,공익재난송출내역_{date.replace('-', '')}.docx"
    return FileResponse(path=docx_path, media_type=_DOCX_MEDIA, filename=filename)


# ── 공익/재난 월별 송출내역 (엑셀) ──────────────────────────────────────────────

_KR_HOLIDAYS = holidays.SouthKorea(years=range(2020, 2036))
_WEEKDAY_KO = ["월", "화", "수", "목", "금", "토", "일"]


def _is_weighted(date_str: str, time_str: str) -> bool:
    """
    가중치 적용 시간대 여부.
    - 평일(공휴일 아님): 19:00 ~ 23:00
    - 주말(토/일) 또는 공휴일: 18:00 ~ 23:00
    """
    d = date_cls.fromisoformat(date_str)
    sec = _time_to_sec(time_str)
    weekend_or_holiday = d.weekday() >= 5 or d in _KR_HOLIDAYS
    start = 18 * 3600 if weekend_or_holiday else 19 * 3600
    return start <= sec < 23 * 3600


def _parse_calendar_month_items(year: int, month: int) -> list[dict]:
    """
    달력 월(1일 00:00 ~ 말일 24:00) 기준으로 해당 월 APST 항목을 반환.
    각 파일을 한 번씩만 파싱하고 broadcast_date가 해당 월인 항목만 추린다.
    """
    last = calendar.monthrange(year, month)[1]
    start = date_cls(year, month, 1) - timedelta(days=1)   # 1일 00:00~04:29는 전날 파일에 있음
    end = date_cls(year, month, last)
    ym = f"{year:04d}-{month:02d}"

    items: list[dict] = []
    seen: set = set()
    d = start
    while d <= end:
        try:
            files = _find_apst_files_for_date(d.isoformat())
        except HTTPException:
            files = []
        for f in files:
            for item in parse_apst_all(f):
                bd = item["broadcast_date"]
                if not bd.startswith(ym):
                    continue
                if not item["item_name_raw"].strip():
                    continue
                key = (bd, item["broadcast_time"], item["item_name_raw"])
                if key in seen:
                    continue
                seen.add(key)
                items.append(item)
        d += timedelta(days=1)

    items.sort(key=lambda x: (x["broadcast_date"], x["broadcast_time"]))
    return items


def _gather_gongik_jaenan_monthly(year: int, month: int) -> dict:
    """
    공익/재난 월별 송출내역 집계 (가중치 계산 포함).
    apst.db(공익재난 + 캠페인K 공익/재난) + ddr1.db(수동송출 공익/재난)에서 조회.
    """
    campaign: list[dict] = []
    disaster: list[dict] = []

    date_pattern = f"{year:04d}-{month:02d}-%"
    for r in _query_gongik_jaenan_db(date_pattern):
        raw = r["item_name_raw"] or ""
        name = r["item_name"] or ""
        bd = r["broadcast_date"]
        bt = r["broadcast_time"]
        dur = r["duration_sec"] or _parse_duration_from_name(raw)
        weighted = _is_weighted(bd, bt)
        row = {
            "date": bd,
            "weekday": _WEEKDAY_KO[date_cls.fromisoformat(bd).weekday()],
            "time": bt,
            "name": _campaign_display_name(raw or name),
            "duration": dur,
            "grade": r["grade"] or classify_grade(bt) or "",
            "weighted": weighted,
            "weighted_value": round(dur * 1.5, 1) if weighted else dur,
            "unweighted_value": dur,
        }
        if r["_gj_kind"] == "재난":
            disaster.append(row)
        else:
            campaign.append(row)

    campaign.sort(key=lambda x: (x["date"], x["time"]))
    disaster.sort(key=lambda x: (x["date"], x["time"]))
    return {"year": year, "month": month, "campaign": campaign, "disaster": disaster}


@router.get("/gongik-jaenan-monthly")
def gongik_jaenan_monthly(
    year: int = Query(...),
    month: int = Query(..., ge=1, le=12),
) -> dict:
    """공익/재난 월별 송출내역 조회 (화면 표출용)."""
    return _gather_gongik_jaenan_monthly(year, month)


@router.get("/gongik-jaenan-monthly/xlsx")
def gongik_jaenan_monthly_xlsx(
    year: int = Query(...),
    month: int = Query(..., ge=1, le=12),
) -> FileResponse:
    """공익/재난 월별 송출내역 엑셀 생성 및 다운로드."""
    data = _gather_gongik_jaenan_monthly(year, month)
    xlsx_path = generate_gongik_jaenan_xlsx(year, month, data)
    filename = f"공익광고, 재난피해 사전예방 송출내역 - {year % 100:02d}{month:02d}.xlsx"
    return FileResponse(
        path=xlsx_path,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        filename=filename,
    )
