"""
Logs router — 활동 로그 조회
GET /api/logs?limit=200
"""

from fastapi import APIRouter, Query
from services.activity_log import get_recent_logs, clear_logs

router = APIRouter(prefix="/api/logs", tags=["logs"])


@router.get("")
def list_logs(limit: int = Query(200, ge=1, le=1000)) -> list[dict]:
    """최근 활동 로그 조회 (최신순)."""
    return get_recent_logs(limit=limit)


@router.delete("")
def delete_logs() -> dict:
    """활동 로그 전체 초기화."""
    n = clear_logs()
    return {"message": "로그를 초기화했습니다.", "deleted": n}
