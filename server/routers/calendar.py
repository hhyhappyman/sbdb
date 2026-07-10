"""
Calendar router — F-02
GET /api/calendar?year=2026&month=05&type=캠페인   → 날짜별 송출 건수
GET /api/calendar/day?date=2026-05-06&type=캠페인  → 특정 날짜 송출 내역
"""

from fastapi import APIRouter, Query
from services.aggregator import get_daily_counts, get_broadcasts_by_date
from services.ftp_fetcher import get_missing_dates

router = APIRouter(prefix="/api/calendar", tags=["calendar"])


@router.get("")
def monthly_counts(
    year:  int        = Query(...),
    month: int        = Query(..., ge=1, le=12),
    type:  str | None = Query(None, description="소재종류: 캠페인 | ID (없으면 전체)"),
) -> dict:
    """달력용 — 월별 날짜별 송출 건수 + 누락일(FTP 파일 없음) 목록."""
    rows = get_daily_counts(year, month, content_type_label=type)
    return {
        "year":    year,
        "month":   month,
        "filter":  type,
        "days":    rows,
        "missing": get_missing_dates(year, month),   # 붉은 0으로 표시할 날짜
    }


@router.get("/day")
def day_detail(
    date: str        = Query(..., description="YYYY-MM-DD"),
    type: str | None = Query(None, description="소재종류: 캠페인 | ID (없으면 전체)"),
) -> dict:
    """특정 날짜의 송출 내역."""
    rows = get_broadcasts_by_date(date, content_type_label=type)
    return {
        "date":   date,
        "filter": type,
        "total":  len(rows),
        "items":  rows,
    }
