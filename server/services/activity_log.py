"""
활동 로그 — DB 변경(적재/수정) 및 파일 누락 상황을 기록한다.
저장 위치: apst.db의 activity_log 테이블.
"""

from datetime import datetime

from database import get_apst_conn


def log_event(level: str, category: str, message: str) -> None:
    """
    로그 한 건 기록.

    Args:
        level:    'info' | 'warning' | 'error'
        category: 'db_insert' | 'db_update' | 'db_delete' | 'file_missing' 등
        message:  사람이 읽을 수 있는 설명

    created_at는 서버(한국) 로컬 시각으로 명시 저장한다.
    (DB 기본값 datetime('now')는 UTC라 9시간 어긋나므로 사용하지 않음)
    """
    try:
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        with get_apst_conn() as conn:
            conn.execute(
                "INSERT INTO activity_log (level, category, message, created_at) VALUES (?, ?, ?, ?)",
                (level, category, message, now),
            )
    except Exception:
        # 로그 기록 자체의 실패가 본 작업을 막아서는 안 됨
        pass


def clear_logs() -> int:
    """활동 로그 전체 삭제. 삭제된 건수를 반환."""
    with get_apst_conn() as conn:
        n = conn.execute("DELETE FROM activity_log").rowcount
    return n


def get_recent_logs(limit: int = 200) -> list[dict]:
    """최근 로그 최대 limit건 (최신순)."""
    with get_apst_conn() as conn:
        rows = conn.execute(
            "SELECT id, level, category, message, created_at "
            "FROM activity_log ORDER BY id DESC LIMIT ?",
            (limit,),
        ).fetchall()
    return [dict(r) for r in rows]
