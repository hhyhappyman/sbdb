"""
SQLite connection helpers and DB initializer.
- apst.db : APST broadcasts + advertisers + app_settings
- ddr1.db : DDR1 broadcasts + clip_map (CML cache)
"""

import sqlite3
from contextlib import contextmanager
from config import (
    APST_DB_PATH, DDR1_DB_PATH,
    DB_DIR, REPORTS_DIR,
    REPORT_MONTHLY_DIR, REPORT_DAILY_DIR, REPORT_DISASTER_DIR, REPORT_SUMMARY_DIR,
    REPORT_SUBTITLE_DIR, REPORT_EXCEL_DIR,
    SETTINGS_KEYS, ADMIN_PASSWORD_DEFAULT,
    WORKER_ID_DEFAULT, WORKER_PASSWORD_DEFAULT, FTP_PORT_DEFAULT,
    ALLOWED_IP_RANGES_DEFAULT,
    GONGIK_INCLUDE_KEYWORDS_DEFAULT, JAENAN_INCLUDE_KEYWORDS_DEFAULT,
    GONGIK_JAENAN_EXCLUDE_KEYWORDS_DEFAULT,
    COMPANY_NAME_DEFAULT, COMPANY_SHORT_DEFAULT,
    APST_SUFFIX_DEFAULT,
)


# ── Connection helpers ──────────────────────────────────────────────────────

@contextmanager
def get_apst_conn():
    conn = sqlite3.connect(APST_DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


@contextmanager
def get_ddr1_conn():
    conn = sqlite3.connect(DDR1_DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


@contextmanager
def get_union_conn():
    """Both DBs attached — use for UNION aggregation queries."""
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.execute(f"ATTACH DATABASE '{APST_DB_PATH}' AS apst")
    conn.execute(f"ATTACH DATABASE '{DDR1_DB_PATH}' AS ddr1")
    try:
        yield conn
    finally:
        conn.close()


# ── Schema ──────────────────────────────────────────────────────────────────

_APST_SCHEMA = """
CREATE TABLE IF NOT EXISTS broadcasts (
    id                 INTEGER PRIMARY KEY AUTOINCREMENT,
    broadcast_date     TEXT    NOT NULL,          -- YYYY-MM-DD
    broadcast_time     TEXT    NOT NULL,          -- HH:MM:SS
    broadcast_hour     INTEGER NOT NULL,          -- 0~23
    clip_id            TEXT    NOT NULL,          -- N######
    item_name_raw      TEXT,                      -- _PgmName_ 원본
    item_name          TEXT,                      -- 정제된 소재명
    duration_sec       INTEGER,
    program_block      TEXT,                      -- _GrpName_
    content_type       TEXT,                      -- Con 코드 (K, IDC …)
    content_type_label TEXT,                      -- '캠페인' 또는 'ID'
    grade              TEXT,                      -- 급지: SA/A/B/C (미분류 시 NULL)
    main_equipment     TEXT,                      -- 주장비명 (MM 필드 원본)
    internal_id        INTEGER,
    source_file        TEXT,
    created_at         TEXT DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_apst_date  ON broadcasts(broadcast_date);
CREATE INDEX IF NOT EXISTS idx_apst_clip  ON broadcasts(clip_id);
CREATE INDEX IF NOT EXISTS idx_apst_hour  ON broadcasts(broadcast_hour);
CREATE INDEX IF NOT EXISTS idx_apst_type  ON broadcasts(content_type_label);
CREATE INDEX IF NOT EXISTS idx_apst_src   ON broadcasts(source_file);
-- idx_apst_grade는 grade 컬럼 마이그레이션 이후 별도로 생성 (init_db 참조)

CREATE TABLE IF NOT EXISTS advertisers (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    item_name        TEXT    NOT NULL UNIQUE,
    company_name     TEXT,
    business_reg_no  TEXT,
    ceo_name         TEXT,
    business_type    TEXT,
    broadcast_medium TEXT    DEFAULT 'TV',
    note             TEXT    DEFAULT '송출시간은 방송사 상황에 따라 변동될 수 있음',
    created_at       TEXT    DEFAULT (datetime('now')),
    updated_at       TEXT    DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS app_settings (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL DEFAULT ''
);

CREATE TABLE IF NOT EXISTS activity_log (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    level      TEXT NOT NULL,         -- info | warning | error
    category   TEXT NOT NULL,         -- db_insert | db_update | file_missing 등
    message    TEXT NOT NULL,
    created_at TEXT DEFAULT (datetime('now', 'localtime'))
);
CREATE INDEX IF NOT EXISTS idx_activity_log_created ON activity_log(created_at);

-- 근무자 수동 입력 송출 내역
CREATE TABLE IF NOT EXISTS manual_entries (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    broadcast_date TEXT    NOT NULL,          -- YYYY-MM-DD (방송일자)
    content_type   TEXT    NOT NULL,          -- 흘림자막 | 공익재난 | 캠페인
    broadcast_time TEXT    NOT NULL,          -- HH:MM:SS
    broadcast_hour INTEGER,
    program_name   TEXT,                      -- 프로그램명
    item_title     TEXT,                      -- 소재제목
    grade          TEXT,                      -- 급지 SA/A/B/C
    worker_name    TEXT,                      -- 근무자 이름
    client_ip      TEXT,                      -- 접속 IP
    created_at     TEXT DEFAULT (datetime('now', 'localtime'))
);
CREATE INDEX IF NOT EXISTS idx_manual_date  ON manual_entries(broadcast_date);
CREATE INDEX IF NOT EXISTS idx_manual_ctype ON manual_entries(content_type);

-- 날짜별 공익광고 송출 근무자 (기능3 공익광고 표의 근무자 칸)
CREATE TABLE IF NOT EXISTS campaign_worker (
    broadcast_date TEXT PRIMARY KEY,          -- YYYY-MM-DD
    worker_name    TEXT,
    updated_at     TEXT DEFAULT (datetime('now', 'localtime'))
);

-- FTP 파일 가져오기 상태 (누락일 붉은 0 표시용)
CREATE TABLE IF NOT EXISTS daily_fetch (
    broadcast_date TEXT PRIMARY KEY,          -- YYYY-MM-DD (방송일)
    status         TEXT,                      -- ok | missing | error
    message        TEXT,
    updated_at     TEXT DEFAULT (datetime('now', 'localtime'))
);
"""

_DDR1_SCHEMA = """
CREATE TABLE IF NOT EXISTS broadcasts (
    id                 INTEGER PRIMARY KEY AUTOINCREMENT,
    broadcast_date     TEXT    NOT NULL,
    broadcast_time     TEXT    NOT NULL,
    broadcast_hour     INTEGER NOT NULL,
    clip_id            TEXT    NOT NULL,
    item_name_raw      TEXT,
    item_name          TEXT,
    content_type_label TEXT,                      -- '캠페인' 또는 'ID'
    grade              TEXT,                      -- 급지: SA/A/B/C (미분류 시 NULL)
    duration_sec       INTEGER,
    source_file        TEXT,
    created_at         TEXT DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_ddr1_date  ON broadcasts(broadcast_date);
CREATE INDEX IF NOT EXISTS idx_ddr1_clip  ON broadcasts(clip_id);
CREATE INDEX IF NOT EXISTS idx_ddr1_hour  ON broadcasts(broadcast_hour);
CREATE INDEX IF NOT EXISTS idx_ddr1_type  ON broadcasts(content_type_label);
CREATE INDEX IF NOT EXISTS idx_ddr1_src   ON broadcasts(source_file);
-- idx_ddr1_grade는 grade 컬럼 마이그레이션 이후 별도로 생성 (init_db 참조)

CREATE TABLE IF NOT EXISTS clip_map (
    clip_id      TEXT    PRIMARY KEY,
    item_type    TEXT,
    full_name    TEXT,
    advertiser   TEXT,
    duration_sec INTEGER
);
"""


def _ensure_column(conn: sqlite3.Connection, table: str, column: str, coltype: str) -> None:
    """테이블에 컬럼이 없으면 ALTER TABLE로 추가 (기존 DB 마이그레이션용)."""
    cols = [r[1] for r in conn.execute(f"PRAGMA table_info({table})").fetchall()]
    if column not in cols:
        conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {coltype}")


def _backfill_grade(conn: sqlite3.Connection) -> None:
    """grade가 비어있는 기존 행에 대해 broadcast_time 기준으로 급지 계산 후 채움."""
    from parsers.utils import classify_grade

    rows = conn.execute(
        "SELECT id, broadcast_time FROM broadcasts WHERE grade IS NULL"
    ).fetchall()
    if not rows:
        return
    updates = [(classify_grade(r[1]), r[0]) for r in rows]
    conn.executemany("UPDATE broadcasts SET grade = ? WHERE id = ?", updates)


def _migrate_apst_dedup(conn: sqlite3.Connection) -> None:
    """
    apst.db broadcasts 행 단위 중복 제거 + 재발 방지.
    파일명이 달라도 같은 (broadcast_date, broadcast_time, clip_id) 행이 중복 적재되던
    문제를 해결한다. 최초 1회: 기존 중복 삭제(가장 작은 id만 남김) → UNIQUE 인덱스 생성.
    (인덱스가 이미 있으면 아무 것도 하지 않아 재시작마다 반복되지 않는다.)
    """
    exists = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='index' AND name='uidx_apst_dtc'"
    ).fetchone()
    if exists:
        return
    # 기존 중복 제거: 같은 키 중 가장 먼저 적재된 행(id 최소)만 남긴다.
    conn.execute(
        """DELETE FROM broadcasts
           WHERE id NOT IN (
               SELECT MIN(id) FROM broadcasts
               GROUP BY broadcast_date, broadcast_time, clip_id
           )"""
    )
    # 재발 방지 UNIQUE 인덱스 (INSERT OR IGNORE와 함께 동작)
    conn.execute(
        "CREATE UNIQUE INDEX uidx_apst_dtc "
        "ON broadcasts(broadcast_date, broadcast_time, clip_id)"
    )


def init_db() -> None:
    """Create directories and initialize both SQLite databases."""
    # Create directories
    for d in [DB_DIR, REPORTS_DIR, REPORT_MONTHLY_DIR, REPORT_DAILY_DIR, REPORT_DISASTER_DIR, REPORT_SUMMARY_DIR, REPORT_SUBTITLE_DIR, REPORT_EXCEL_DIR]:
        d.mkdir(parents=True, exist_ok=True)

    # apst.db
    conn = sqlite3.connect(APST_DB_PATH)
    conn.executescript(_APST_SCHEMA)
    _ensure_column(conn, "broadcasts", "grade", "TEXT")
    _ensure_column(conn, "broadcasts", "main_equipment", "TEXT")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_apst_grade ON broadcasts(grade)")
    _backfill_grade(conn)
    _migrate_apst_dedup(conn)   # 행 단위 중복 제거 + UNIQUE 인덱스(최초 1회)
    # 최초 설치 시에만 채우는 시딩 기본값 (빈 값으로 비워도 복구하지 않음)
    _seed_defaults = {
        "apst_suffix":                    APST_SUFFIX_DEFAULT,
        "company_name":                   COMPANY_NAME_DEFAULT,
        "company_short":                  COMPANY_SHORT_DEFAULT,
        "gongik_include_keywords":        GONGIK_INCLUDE_KEYWORDS_DEFAULT,
        "jaenan_include_keywords":        JAENAN_INCLUDE_KEYWORDS_DEFAULT,
        "gongik_jaenan_exclude_keywords": GONGIK_JAENAN_EXCLUDE_KEYWORDS_DEFAULT,
    }
    # 빈 값이면 기본값으로 복구하는 항목 (로그인·접속 관련)
    _defaults = {
        "admin_password":    ADMIN_PASSWORD_DEFAULT,
        "worker_id":         WORKER_ID_DEFAULT,
        "worker_password":   WORKER_PASSWORD_DEFAULT,
        "ftp_port":          FTP_PORT_DEFAULT,
        "allowed_ip_ranges": ALLOWED_IP_RANGES_DEFAULT,
    }
    _all_seed = {**_seed_defaults, **_defaults}
    for key in SETTINGS_KEYS:
        conn.execute(
            "INSERT OR IGNORE INTO app_settings (key, value) VALUES (?, ?)",
            (key, _all_seed.get(key, ""))
        )
    # 로그인 관련 값이 빈 값인 경우 기본값으로 복구
    for key, default_val in _defaults.items():
        conn.execute(
            "UPDATE app_settings SET value = ? WHERE key = ? AND value = ''",
            (default_val, key)
        )
    conn.commit()
    conn.close()

    # ddr1.db
    conn = sqlite3.connect(DDR1_DB_PATH)
    conn.executescript(_DDR1_SCHEMA)
    _ensure_column(conn, "broadcasts", "grade", "TEXT")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_ddr1_grade ON broadcasts(grade)")
    _backfill_grade(conn)
    conn.commit()
    conn.close()

    print("[DB] Initialized: apst.db / ddr1.db")
