"""
Dashboard router — F-01
GET /api/dashboard?year=2026&month=05&type=캠페인
"""

from fastapi import APIRouter, Query
from services.aggregator import get_item_counts, get_hourly_counts

router = APIRouter(prefix="/api/dashboard", tags=["dashboard"])


@router.get("")
def dashboard(
    year:  int        = Query(..., description="년도"),
    month: int | None = Query(None, ge=1, le=12, description="월 (없으면 연간)"),
    type:  str | None = Query(None, description="소재종류 필터: 캠페인 | ID"),
) -> dict:
    """
    대시보드 데이터 반환.
    - by_item : 소재별 송출 횟수
    - by_hour : 시간대별 송출 횟수
    """
    by_item  = get_item_counts(year, month, content_type_label=type)
    by_hour  = get_hourly_counts(year, month, content_type_label=type)
    total    = sum(r["count"] for r in by_item)

    return {
        "period": {"year": year, "month": month},
        "filter": type,
        "total":  total,
        "by_item": by_item,   # 각 항목에 count, sa_count, a_count, b_count, c_count 포함
        "by_hour": by_hour,
    }
