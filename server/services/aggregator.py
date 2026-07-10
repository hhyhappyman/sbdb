"""
Aggregation queries across both apst.db and ddr1.db.
Uses SQLite ATTACH DATABASE to run UNION queries in a single connection.
"""

import sqlite3
from config import APST_DB_PATH, DDR1_DB_PATH


def _get_conn() -> sqlite3.Connection:
    """Return an in-memory connection with both DBs attached."""
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.execute(f"ATTACH DATABASE '{APST_DB_PATH}' AS apst")
    conn.execute(f"ATTACH DATABASE '{DDR1_DB_PATH}' AS ddr1")
    return conn


def _date_range(year: int, month: int | None) -> tuple[str, str]:
    """Return (start_date, end_date) strings for the given year/month."""
    if month:
        import calendar
        last_day = calendar.monthrange(year, month)[1]
        start = f"{year}-{month:02d}-01"
        end   = f"{year}-{month:02d}-{last_day:02d}"
    else:
        start = f"{year}-01-01"
        end   = f"{year}-12-31"
    return start, end


# ── Dashboard ──────────────────────────────────────────────────────────────

def get_item_counts(year: int, month: int | None = None,
                    content_type_label: str | None = None) -> list[dict]:
    """
    소재별 송출 횟수 + 급지(SA/A/B/C)별 횟수 집계 (양쪽 DB UNION).
    content_type_label: '캠페인' 또는 'ID' 또는 None(전체)
    """
    start, end = _date_range(year, month)
    type_filter = "AND content_type_label = ?" if content_type_label else ""
    params = [start, end]
    if content_type_label:
        params.append(content_type_label)
    # Duplicate params for ddr1 side
    params = params + params

    sql = f"""
        SELECT item_name, content_type_label,
               COUNT(*) AS count,
               SUM(CASE WHEN grade = 'SA' THEN 1 ELSE 0 END) AS sa_count,
               SUM(CASE WHEN grade = 'A'  THEN 1 ELSE 0 END) AS a_count,
               SUM(CASE WHEN grade = 'B'  THEN 1 ELSE 0 END) AS b_count,
               SUM(CASE WHEN grade = 'C'  THEN 1 ELSE 0 END) AS c_count
        FROM (
            SELECT item_name, content_type_label, grade
            FROM apst.broadcasts
            WHERE broadcast_date BETWEEN ? AND ? {type_filter}
            UNION ALL
            SELECT item_name, content_type_label, grade
            FROM ddr1.broadcasts
            WHERE broadcast_date BETWEEN ? AND ? {type_filter}
        )
        GROUP BY item_name, content_type_label
        ORDER BY count DESC, item_name
    """
    conn = _get_conn()
    try:
        rows = conn.execute(sql, params).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def get_hourly_counts(year: int, month: int | None = None,
                      content_type_label: str | None = None) -> list[dict]:
    """시간대별(0~23) 송출 횟수 집계."""
    start, end = _date_range(year, month)
    type_filter = "AND content_type_label = ?" if content_type_label else ""
    params = [start, end]
    if content_type_label:
        params.append(content_type_label)
    params = params + params

    sql = f"""
        SELECT broadcast_hour AS hour, COUNT(*) AS count
        FROM (
            SELECT broadcast_hour, content_type_label
            FROM apst.broadcasts
            WHERE broadcast_date BETWEEN ? AND ? {type_filter}
            UNION ALL
            SELECT broadcast_hour, content_type_label
            FROM ddr1.broadcasts
            WHERE broadcast_date BETWEEN ? AND ? {type_filter}
        )
        GROUP BY broadcast_hour
        ORDER BY broadcast_hour
    """
    conn = _get_conn()
    try:
        rows = conn.execute(sql, params).fetchall()
        # Fill missing hours with 0
        count_map = {r["hour"]: r["count"] for r in rows}
        return [{"hour": h, "count": count_map.get(h, 0)} for h in range(24)]
    finally:
        conn.close()


# ── Calendar ───────────────────────────────────────────────────────────────

def get_daily_counts(year: int, month: int,
                     content_type_label: str | None = None) -> list[dict]:
    """월별 날짜별 송출 건수 (달력용). content_type_label: '캠페인' | 'ID' | None(전체)"""
    start, end = _date_range(year, month)
    type_filter = "AND content_type_label = ?" if content_type_label else ""
    params = [start, end]
    if content_type_label:
        params.append(content_type_label)
    params = params + params

    sql = f"""
        SELECT broadcast_date AS date, COUNT(*) AS count
        FROM (
            SELECT broadcast_date, content_type_label FROM apst.broadcasts
            WHERE broadcast_date BETWEEN ? AND ? {type_filter}
            UNION ALL
            SELECT broadcast_date, content_type_label FROM ddr1.broadcasts
            WHERE broadcast_date BETWEEN ? AND ? {type_filter}
        )
        GROUP BY broadcast_date
        ORDER BY broadcast_date
    """
    conn = _get_conn()
    try:
        rows = conn.execute(sql, params).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def get_broadcasts_by_date(date: str, content_type_label: str | None = None) -> list[dict]:
    """특정 날짜의 송출 내역 (grade 포함). content_type_label: '캠페인' | 'ID' | None(전체)"""
    type_filter = "AND content_type_label = ?" if content_type_label else ""
    params = [date]
    if content_type_label:
        params.append(content_type_label)
    params = params + params

    sql = f"""
        SELECT broadcast_time, item_name, content_type_label, grade,
               duration_sec, clip_id, 'apst' AS source
        FROM apst.broadcasts
        WHERE broadcast_date = ? {type_filter}
        UNION ALL
        SELECT broadcast_time, item_name, content_type_label, grade,
               duration_sec, clip_id, 'ddr1' AS source
        FROM ddr1.broadcasts
        WHERE broadcast_date = ? {type_filter}
        ORDER BY broadcast_time
    """
    conn = _get_conn()
    try:
        rows = conn.execute(sql, params).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


# ── Period ─────────────────────────────────────────────────────────────────

def get_period_broadcasts(
    start_date: str,                 # YYYY-MM-DD
    end_date: str,                   # YYYY-MM-DD
    start_hour: int | None = None,   # 0~23, None이면 제한 없음
    end_hour: int | None = None,     # 0~23, None이면 제한 없음
    content_type_label: str | None = None,
    item_name: str | None = None,    # 완전 일치 단일 소재명, None이면 전체
    item_names: list[str] | None = None,  # 완전 일치 다중 소재명 (체크박스 다중 선택)
    source: str | None = None,       # 'apst'=자동, 'ddr1'=수동, None=전체
) -> list[dict]:
    """상세조회 — 날짜범위·시간대·소재종류·소재명·송출구분 필터 지원."""
    # 공통 WHERE 조건
    filters = ["broadcast_date BETWEEN ? AND ?"]
    base_params = [start_date, end_date]

    if content_type_label:
        filters.append("content_type_label = ?")
        base_params.append(content_type_label)
    if item_names:
        # 체크박스로 선택한 여러 소재명 중 하나와 완전 일치
        placeholders = ",".join("?" * len(item_names))
        filters.append(f"item_name IN ({placeholders})")
        base_params.extend(item_names)
    elif item_name:
        # 정확히 일치하는 소재명만 필터 (프론트엔드에서 /api/items로 후보를 먼저
        # 확정한 뒤 정확한 이름을 넘겨주므로 부분검색이 아닌 완전일치 사용)
        filters.append("item_name = ?")
        base_params.append(item_name)
    if start_hour is not None:
        filters.append("broadcast_hour >= ?")
        base_params.append(start_hour)
    if end_hour is not None:
        filters.append("broadcast_hour <= ?")
        base_params.append(end_hour)

    where = " AND ".join(filters)

    # 송출구분 필터 적용
    if source == "apst":
        sql = f"""
            SELECT broadcast_date, broadcast_time, item_name,
                   content_type_label, duration_sec, clip_id, 'apst' AS source
            FROM apst.broadcasts WHERE {where}
            ORDER BY broadcast_date, broadcast_time
        """
        params = base_params
    elif source == "ddr1":
        sql = f"""
            SELECT broadcast_date, broadcast_time, item_name,
                   content_type_label, duration_sec, clip_id, 'ddr1' AS source
            FROM ddr1.broadcasts WHERE {where}
            ORDER BY broadcast_date, broadcast_time
        """
        params = base_params
    else:
        sql = f"""
            SELECT broadcast_date, broadcast_time, item_name,
                   content_type_label, duration_sec, clip_id, 'apst' AS source
            FROM apst.broadcasts WHERE {where}
            UNION ALL
            SELECT broadcast_date, broadcast_time, item_name,
                   content_type_label, duration_sec, clip_id, 'ddr1' AS source
            FROM ddr1.broadcasts WHERE {where}
            ORDER BY broadcast_date, broadcast_time
        """
        params = base_params + base_params

    conn = _get_conn()
    try:
        rows = conn.execute(sql, params).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def search_items(query: str, limit: int = 30, content_type_label: str | None = None) -> list[dict]:
    """
    소재명 부분 검색 — 소재명·종류·총 송출 횟수·최초 추가 일시 반환 (월 관계없이 전체).
    content_type_label: '캠페인' | 'ID' | None(전체) — 지정 시 해당 종류만 검색.
    최근 추가된 소재부터 정렬.
    """
    type_filter = "AND content_type_label = ?" if content_type_label else ""
    like = f"%{query}%"
    params = [like]
    if content_type_label:
        params.append(content_type_label)
    params = params + params

    sql = f"""
        SELECT item_name, content_type_label, COUNT(*) AS count,
               MIN(broadcast_date) AS first_added
        FROM (
            SELECT item_name, content_type_label, broadcast_date FROM apst.broadcasts
            WHERE item_name LIKE ? {type_filter}
            UNION ALL
            SELECT item_name, content_type_label, broadcast_date FROM ddr1.broadcasts
            WHERE item_name LIKE ? {type_filter}
        )
        GROUP BY item_name, content_type_label
        ORDER BY first_added DESC, count DESC
        LIMIT ?
    """
    conn = _get_conn()
    try:
        rows = conn.execute(sql, params + [limit]).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def get_item_list(year: int | None = None,
                  content_type_label: str | None = None) -> list[dict]:
    """
    소재 목록 — 소재명·송출시 소재명·소재종류·추가 날짜. 최신 추가 순.
    year: 추가 연도 필터 / content_type_label: '캠페인' | 'ID' | None(전체)
    """
    type_filter = "AND content_type_label = ?" if content_type_label else ""
    having_parts = []
    params: list = []

    if content_type_label:
        params.append(content_type_label)
        params.append(content_type_label)

    if year:
        having_parts.append(f"strftime('%Y', MIN(broadcast_date)) = ?")
        params.append(str(year))

    having_clause = ("HAVING " + " AND ".join(having_parts)) if having_parts else ""

    sql = f"""
        SELECT item_name, item_name_raw, content_type_label,
               MIN(broadcast_date) AS added_at
        FROM (
            SELECT item_name, item_name_raw, content_type_label, broadcast_date
            FROM apst.broadcasts
            WHERE 1=1 {type_filter}
            UNION ALL
            SELECT item_name, item_name_raw, content_type_label, broadcast_date
            FROM ddr1.broadcasts
            WHERE 1=1 {type_filter}
        )
        GROUP BY item_name
        {having_clause}
        ORDER BY MIN(broadcast_date) DESC
    """
    conn = _get_conn()
    try:
        rows = conn.execute(sql, params).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def get_item_list_years() -> list[int]:
    """소재 목록에 존재하는 추가 연도 목록 (내림차순)."""
    sql = """
        SELECT DISTINCT strftime('%Y', added_at) AS year
        FROM (
            SELECT item_name, MIN(broadcast_date) AS added_at
            FROM (
                SELECT item_name, broadcast_date FROM apst.broadcasts
                UNION ALL
                SELECT item_name, broadcast_date FROM ddr1.broadcasts
            )
            GROUP BY item_name
        )
        WHERE added_at IS NOT NULL
        ORDER BY year DESC
    """
    conn = _get_conn()
    try:
        rows = conn.execute(sql).fetchall()
        return [int(r["year"]) for r in rows if r["year"]]
    finally:
        conn.close()


# ── Report (F-04) ──────────────────────────────────────────────────────────

def get_item_monthly_report(item_name: str, year: int, month: int) -> list[dict]:
    """
    특정 소재의 월별 날짜별 송출 시간 목록.
    Returns list of {date, times: [HH:MM:SS, ...], count}.
    """
    start, end = _date_range(year, month)
    sql = """
        SELECT broadcast_date AS date, broadcast_time AS time
        FROM (
            SELECT broadcast_date, broadcast_time
            FROM apst.broadcasts
            WHERE item_name = ? AND broadcast_date BETWEEN ? AND ?
            UNION ALL
            SELECT broadcast_date, broadcast_time
            FROM ddr1.broadcasts
            WHERE item_name = ? AND broadcast_date BETWEEN ? AND ?
        )
        ORDER BY date, time
    """
    conn = _get_conn()
    try:
        rows = conn.execute(sql, [item_name, start, end, item_name, start, end]).fetchall()
    finally:
        conn.close()

    # Group by date
    from collections import defaultdict
    grouped: dict = defaultdict(list)
    for r in rows:
        grouped[r["date"]].append(r["time"])

    return [
        {"date": d, "times": times, "count": len(times)}
        for d, times in sorted(grouped.items())
    ]


def get_daily_item_summary(date: str, content_type_label: str) -> list[dict]:
    """
    일일 운행표 / 일일 ID 운행표 — 특정 날짜·소재종류의 소재별 총횟수 + 급지별 횟수.
    content_type_label: '캠페인' 또는 'ID' (필수)
    """
    sql = """
        SELECT item_name,
               COUNT(*) AS total_count,
               SUM(CASE WHEN grade = 'SA' THEN 1 ELSE 0 END) AS sa,
               SUM(CASE WHEN grade = 'A'  THEN 1 ELSE 0 END) AS a,
               SUM(CASE WHEN grade = 'B'  THEN 1 ELSE 0 END) AS b,
               SUM(CASE WHEN grade = 'C'  THEN 1 ELSE 0 END) AS c
        FROM (
            SELECT item_name, grade FROM apst.broadcasts
            WHERE broadcast_date = ? AND content_type_label = ?
            UNION ALL
            SELECT item_name, grade FROM ddr1.broadcasts
            WHERE broadcast_date = ? AND content_type_label = ?
        )
        GROUP BY item_name
        ORDER BY total_count DESC, item_name
    """
    conn = _get_conn()
    try:
        rows = conn.execute(
            sql, [date, content_type_label, date, content_type_label]
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def get_apst_name_map(dates: set[str]) -> dict:
    """
    지정한 날짜들의 자동송출(apst.db) 소재를 clip_id로 조회할 수 있는 매핑 반환.
    수동 송출 추출 시 CML에 없는 clip_id의 소재명을 보완하는 용도.

    반환: {"YYYY-MM-DD": {clip_id: {item_name_raw, item_name,
                                    content_type_label, duration_sec}}}
    """
    if not dates:
        return {}
    conn = sqlite3.connect(APST_DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        placeholders = ",".join("?" * len(dates))
        rows = conn.execute(
            f"""SELECT broadcast_date, clip_id, item_name_raw, item_name,
                       content_type_label, duration_sec
                FROM broadcasts WHERE broadcast_date IN ({placeholders})""",
            list(dates),
        ).fetchall()
    finally:
        conn.close()

    result: dict = {}
    for r in rows:
        result.setdefault(r["broadcast_date"], {})[r["clip_id"]] = {
            "item_name_raw":      r["item_name_raw"],
            "item_name":          r["item_name"],
            "content_type_label": r["content_type_label"],
            "duration_sec":       r["duration_sec"] or 0,
        }
    return result


def get_apst_name_before(clip_id: str, before_date: str) -> dict | None:
    """
    clip_id를 자동송출(apst.db)에서 날짜 무관하게 조회하되,
    기준 날짜(before_date) 이전 날짜 중 가장 가까운(최신) 날짜의 소재를 반환한다.
    (어제 → 그 이전 순서로 찾는 것과 동일한 효과)

    찾지 못하면 None.
    """
    conn = sqlite3.connect(APST_DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        r = conn.execute(
            """SELECT item_name_raw, item_name, content_type_label, duration_sec, broadcast_date
               FROM broadcasts
               WHERE clip_id = ? AND broadcast_date < ?
               ORDER BY broadcast_date DESC LIMIT 1""",
            (clip_id, before_date),
        ).fetchone()
    finally:
        conn.close()
    if not r:
        return None
    return {
        "item_name_raw":      r["item_name_raw"],
        "item_name":          r["item_name"],
        "content_type_label": r["content_type_label"],
        "duration_sec":       r["duration_sec"] or 0,
        "source_date":        r["broadcast_date"],
    }


def get_campaign_names() -> set:
    """APST DB에 저장된 캠페인 소재명 집합 반환 (DDR1 분류용)."""
    conn = sqlite3.connect(APST_DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        rows = conn.execute(
            "SELECT DISTINCT item_name FROM broadcasts WHERE content_type_label = '캠페인'"
        ).fetchall()
        return {r["item_name"] for r in rows}
    finally:
        conn.close()
