"""
Items router — 소재명 검색 (자동완성 / 선택 팝업용)
GET /api/items?q=영산강          → 소재명 부분 검색
GET /api/items/all               → 전체 소재 목록 (최대 200개, 횟수 내림차순)
GET /api/items/list              → 소재 목록 (추가 날짜 기준, 연도 필터)
GET /api/items/years             → 소재 추가 연도 목록
"""

from fastapi import APIRouter, Query
from services.aggregator import search_items, get_item_list, get_item_list_years


router = APIRouter(prefix="/api/items", tags=["items"])


@router.get("/years")
def item_years() -> list[int]:
    """소재 목록에 존재하는 추가 연도 목록."""
    return get_item_list_years()


@router.get("/list")
def item_list(
    year: int | None = Query(None, description="추가 연도 필터"),
    type: str | None = Query(None, description="소재종류: 캠페인 | ID"),
) -> list[dict]:
    """소재 목록 — 소재명·송출시 소재명·소재종류·추가 날짜. 최신 추가 순."""
    return get_item_list(year, content_type_label=type)


@router.get("")
def search(
    q:     str = Query(..., min_length=1, description="검색어 (부분 일치)"),
    limit: int = Query(30, ge=1, le=100),
    type:  str | None = Query(None, description="소재종류: 캠페인 | ID"),
) -> list[dict]:
    """소재명 부분 검색 — 입력된 글자가 포함된 소재 목록 반환. type 지정 시 해당 종류만."""
    return search_items(q, limit=limit, content_type_label=type)


@router.get("/all")
def all_items(limit: int = Query(200, ge=1, le=500)) -> list[dict]:
    """전체 소재 목록 (횟수 내림차순)."""
    return search_items("", limit=limit)
