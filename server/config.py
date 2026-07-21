"""
Application configuration — code-level fixed paths only.
Runtime file paths (apst_dir, ddr1_dir, etc.) are stored in app_settings DB table.
"""

from pathlib import Path

# --- Base directories ---
BASE_DIR = Path(__file__).parent.parent   # proj1/
DB_DIR = BASE_DIR / "db"
REPORTS_DIR = BASE_DIR / "reports"

# --- SQLite DB files ---
APST_DB_PATH = str(DB_DIR / "apst.db")
DDR1_DB_PATH = str(DB_DIR / "ddr1.db")

# --- Report subdirectories ---
REPORT_MONTHLY_DIR  = REPORTS_DIR / "monthly"    # F-04
REPORT_DAILY_DIR    = REPORTS_DIR / "daily"      # 방송 운행표 (구 F-06)
REPORT_DISASTER_DIR = REPORTS_DIR / "disaster"   # F-07
REPORT_SUMMARY_DIR  = REPORTS_DIR / "summary"    # 일일 운행표 / 일일 ID 운행표
REPORT_SUBTITLE_DIR = REPORTS_DIR / "subtitle"   # 흘림자막·공익·재난 송출내역
REPORT_EXCEL_DIR    = REPORTS_DIR / "excel"      # 공익/재난 월별 송출내역 (xlsx)

# --- Default app_settings keys ---
SETTINGS_KEYS = [
    "apst_dir",        # APST 파일 저장 디렉터리
    "apst_suffix",     # APST 파일명 날짜 뒤 접미사 (예: AAA/A/P) — 대소문자 무시
    "ddr1_dir",        # DDR1 로그 파일 디렉터리
    "cml_path",        # CML 매핑 파일 경로 (단일 파일)
    "logo_path",       # 광주MBC 로고 이미지 파일 경로
    "seal_path",       # 직인 이미지 파일 경로
    "ceo_name",        # 대표이사명 (F-04 PDF 표기용)
    "admin_password",  # 관리자 비밀번호 (초기값: admin)
    "worker_id",       # 근무자 로그인 아이디 (초기값: user)
    "worker_password", # 근무자 로그인 비밀번호 (초기값: user2450)
    "ftp_host",        # 송출 파일 FTP 서버 주소
    "ftp_port",        # FTP 포트 (기본 21)
    "ftp_user",        # FTP 로그인 아이디
    "ftp_password",    # FTP 로그인 비밀번호
    "ftp_fetch_time",  # 매일 전날 파일 자동 가져오기 시각 (HH:MM)
    "allowed_ip_ranges",  # 접근 허용 IP 대역 (콤마/줄바꿈 구분, 0.0.0.0=전체허용)
    "company_name",    # 회사명 (예: 광주문화방송) — 월 리포트 회사명/푸터 표기
    "company_short",   # 약칭   (예: 광주MBC)     — 좌측 로고/월 리포트 제목 표기
    "gongik_include_keywords",  # 공익으로 포함할 추가 소재명 키워드 (콤마 구분)
    "jaenan_include_keywords",  # 재난으로 포함할 추가 소재명 키워드 (콤마 구분)
    "gongik_jaenan_exclude_keywords",  # 공익/재난에서 제외할 소재명 키워드 (콤마 구분)
]

# 접근 허용 IP 대역 기본값 (환경설정 미입력 시 사용) — 광주MBC 사내망
ALLOWED_IP_RANGES_DEFAULT = "218.237.3.0/24"

# 회사명/약칭 기본값 (환경설정 미입력 시 사용)
COMPANY_NAME_DEFAULT = "광주문화방송"
COMPANY_SHORT_DEFAULT = "광주MBC"

# APST 파일명 접미사 기본값 (예: 20260720AAA.apst → 'AAA'). 대소문자 무시.
# 빈 문자열이면 '20260720.apst'(접미사 없음) 형식을 읽는다.
APST_SUFFIX_DEFAULT = "AAA"

# 공익/재난 포함·제외 키워드 기본값 (환경설정 미입력 시 사용)
GONGIK_INCLUDE_KEYWORDS_DEFAULT = "학교폭력예방"
JAENAN_INCLUDE_KEYWORDS_DEFAULT = ""
GONGIK_JAENAN_EXCLUDE_KEYWORDS_DEFAULT = ""

# --- Admin ---
ADMIN_ID = "admin"
ADMIN_PASSWORD_DEFAULT = "admin2450"

# --- Worker (근무자) ---
WORKER_ID_DEFAULT = "user"
WORKER_PASSWORD_DEFAULT = "user2450"

# --- FTP ---
FTP_PORT_DEFAULT = "21"
# FTP 홈 폴더 아래 파일 종류별 하위 폴더명
FTP_SUBDIRS = {
    "apst": "apst",
    "ddr1": "ddr1_log",
    "cml":  "cml",
}
# 누락일 붉은 0 표시 시작일 (이 날짜 이후부터 적용)
MISSING_MARK_START = "2026-07-01"

# --- CORS allowed origins ---
CORS_ORIGINS = [
    "http://localhost:5173",   # Vite dev server
    "http://localhost:3000",
]
