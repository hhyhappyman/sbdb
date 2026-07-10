"""
Period router — 상세조회 (F-03)
GET /api/period
  ?start_date=2026-01-01&end_date=2026-05-31
  &start_hour=6&end_hour=23     ← 선택 (시간 범위)
  &type=캠페인                  ← 선택 (소재종류)
  &item=영산강                  ← 선택 (소재명 부분검색)
  &source=apst                  ← 선택 (apst=자동, ddr1=수동, 없으면 전체)
"""

from fastapi import APIRouter, Query
from services.aggregator import get_period_broadcasts

router = APIRouter(prefix="/api/period", tags=["period"])


@router.get("")
def period_broadcasts(
    start_date:  str        = Query(..., description="시작 날짜 (YYYY-MM-DD)"),
    end_date:    str        = Query(..., description="끝 날짜 (YYYY-MM-DD)"),
    start_hour:  int | None = Query(None, ge=0, le=23, description="시작 시간 (0~23)"),
    end_hour:    int | None = Query(None, ge=0, le=23, description="끝 시간 (0~23)"),
    type:        str | None = Query(None, description="소재종류: 캠페인 | ID"),
    item:        str | None = Query(None, description="소재명 (완전 일치, 단일)"),
    items:       str | None = Query(None, description="소재명 여러 개 (쉼표 구분, 완전 일치)"),
    source:      str | None = Query(None, description="송출구분: apst=자동, ddr1=수동"),
) -> dict:
    """상세조회 — 날짜범위·시간·소재종류·소재명·송출구분 복합 필터."""
    # 날짜 순서 보정
    if start_date > end_date:
        start_date, end_date = end_date, start_date

    item_names = [n for n in items.split(",") if n] if items else None

    rows = get_period_broadcasts(
        start_date=start_date,
        end_date=end_date,
        start_hour=start_hour,
        end_hour=end_hour,
        content_type_label=type,
        item_name=item,
        item_names=item_names,
        source=source,
    )

    return {
        "period":     {"start": start_date, "end": end_date},
        "time_range": {"start_hour": start_hour, "end_hour": end_hour},
        "filter":     {"type": type, "item": item, "items": item_names, "source": source},
        "total":      len(rows),
        "items":      rows,
    }
