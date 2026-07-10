# Design — SB 송출 대시보드

## 시스템 아키텍처

```
┌──────────────────────────────────────────────────────────────┐
│              React Frontend (상단 헤더 띠 없음)                │
│  Dashboard│Calendar│상세조회│송출내역출력│파일적재│광고주│설정  │
│                   store.js (메모리 상태 유지)                  │
└─────────────────────────┬────────────────────────────────────┘
                           │ REST API (HTTP / Vite Proxy)
┌─────────────────────────▼────────────────────────────────────┐
│                   FastAPI Backend (:8000)                     │
│  /api/auth  /api/dashboard  /api/calendar  /api/period       │
│  /api/report  /api/ingest  /api/items  /api/settings         │
│  /api/advertisers                                             │
│                                                               │
│  ┌─────────────────────────────────────────────────────┐     │
│  │  file_watcher.py (watchdog — 별도 스레드)            │     │
│  │  apst_dir 감시 → .apst/.cml 자동 적재               │     │
│  │  ddr1_dir 감시 → .Log 자동 적재                      │     │
│  └─────────────────────────────────────────────────────┘     │
└──────────┬────────────────────────┬─────────────────────────┘
           │ ATTACH DATABASE        │
┌──────────▼──────────┐  ┌─────────▼─────────────────────────┐
│   apst.db           │  │   ddr1.db                         │
│   broadcasts        │  │   broadcasts                      │
│   advertisers       │  │   clip_map (CML 캐시)             │
│   app_settings      │  └───────────────────────────────────┘
└─────────────────────┘

텔레그램 봇 (Phase 5 — 미구현)
```

---

## 폴더 구조 ✅ 구현 완료

```
proj1/
├── server/
│   ├── main.py                 # FastAPI 앱 (startup/shutdown 훅 포함)
│   ├── config.py               # 코드 레벨 고정값 (DB 경로, CORS 등)
│   ├── database.py             # SQLite 연결 컨텍스트 매니저, 스키마 초기화
│   ├── parsers/
│   │   ├── __init__.py
│   │   ├── utils.py            # extract_item_name() 공통 유틸
│   │   ├── apst_parser.py      # APST JSON 파싱 (캠페인·ID 필터)
│   │   ├── ddr1_parser.py      # DDR1 로그 파싱 (Play CLIP 이벤트)
│   │   └── cml_parser.py       # CML 파싱 (CP949 인코딩)
│   ├── routers/
│   │   ├── __init__.py
│   │   ├── auth.py             # POST /api/auth/login|logout, PUT /api/auth/password
│   │   ├── dashboard.py        # GET /api/dashboard
│   │   ├── calendar.py         # GET /api/calendar, /api/calendar/day
│   │   ├── period.py           # GET /api/period (날짜범위·시간·소재명·송출구분)
│   │   ├── report.py           # GET /api/report, /daily, /disaster, /daily-summary + /pdf
│   │   ├── ingest.py           # POST /api/ingest/cml|apst|ddr1, /apst/scan, /ddr1/scan
│   │   │                       # GET|POST /api/ingest/watcher, GET /api/ingest/status
│   │   ├── items.py            # GET /api/items (소재명 검색)
│   │   ├── settings.py         # GET|PUT /api/settings
│   │   └── advertisers.py      # CRUD /api/advertisers
│   ├── services/
│   │   ├── __init__.py
│   │   ├── aggregator.py       # 두 DB UNION 집계 + 소재 검색
│   │   ├── pdf_generator.py    # F-04/F-06/F-07 PDF (reportlab)
│   │   └── file_watcher.py     # watchdog 폴더 감시 서비스
│   └── bot/
│       ├── __init__.py
│       └── telegram_bot.py     # F-05 (Phase 5 — 스텁)
├── client/
│   ├── index.html
│   ├── vite.config.js          # /api → :8000 프록시 설정
│   ├── package.json
│   └── src/
│       ├── main.jsx            # React 진입점 (한국어 locale)
│       ├── App.jsx             # 레이아웃, 관리자 인증, 메뉴 분기
│       ├── store.js            # 탭 이동 후 상태 유지 전역 저장소
│       ├── api/
│       │   └── index.js        # 모든 API 호출 함수
│       └── pages/
│           ├── Dashboard.jsx        # F-01
│           ├── CalendarView.jsx     # F-02
│           ├── PeriodView.jsx       # F-03 상세조회
│           ├── ReportView.jsx       # F-04/F-06/F-07 송출내역 출력
│           ├── IngestPage.jsx       # 파일 적재 + 감시 제어
│           ├── AdvertiserPage.jsx   # 광고주 CRUD
│           └── SettingsPage.jsx     # 환경설정 + 비밀번호 변경
├── db/
│   ├── apst.db
│   └── ddr1.db
├── reports/
│   ├── monthly/               # F-04 PDF
│   ├── daily/                 # F-06 PDF (방송 운행표)
│   ├── disaster/              # F-07 PDF
│   └── summary/               # F-08/F-09 PDF (일일 운행표 / 일일 ID 운행표)
├── data/                      # 예시 데이터 파일
├── requirements.txt
├── .vscode/
│   └── tasks.json             # Ctrl+Shift+B 단축키 실행 설정
└── spec_01_apst_format.md
    spec_02_ddr1_log_format.md
    spec_03_cml_format.md
```

---

## DB 스키마 ✅ 확정

### apst.db — `broadcasts`

```sql
CREATE TABLE broadcasts (
    id                 INTEGER PRIMARY KEY AUTOINCREMENT,
    broadcast_date     TEXT NOT NULL,          -- YYYY-MM-DD
    broadcast_time     TEXT NOT NULL,          -- HH:MM:SS
    broadcast_hour     INTEGER NOT NULL,       -- 0~23
    clip_id            TEXT NOT NULL,          -- N######
    item_name_raw      TEXT,                   -- _PgmName_ 원본
    item_name          TEXT,                   -- 정제된 소재명
    duration_sec       INTEGER,
    program_block      TEXT,                   -- _GrpName_
    content_type       TEXT,                   -- Con 코드 (K, I)
    content_type_label TEXT,                   -- '캠페인' 또는 'ID'
    grade              TEXT,                   -- 급지: SA/A/B/C (미분류 시 NULL)
    main_equipment     TEXT,                   -- ✅ 신규: 주장비명 (MM 필드 원본)
    internal_id        INTEGER,
    source_file        TEXT,
    created_at         TEXT DEFAULT (datetime('now'))
);
-- 캠페인·ID 소재만 저장 (이어서·광고그룹·프로그램 등 제외)
-- grade, main_equipment 컬럼은 마이그레이션으로 추가됨: ALTER TABLE (database.py _ensure_column 참조)
```

### apst.db — `advertisers`

```sql
CREATE TABLE advertisers (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    item_name        TEXT NOT NULL UNIQUE,
    company_name     TEXT,
    business_reg_no  TEXT,
    ceo_name         TEXT,
    business_type    TEXT,
    broadcast_medium TEXT DEFAULT 'TV',
    note             TEXT DEFAULT '송출시간은 방송사 상황에 따라 변동될 수 있음',
    created_at       TEXT DEFAULT (datetime('now')),
    updated_at       TEXT DEFAULT (datetime('now'))
);
```

### apst.db — `app_settings`

```sql
CREATE TABLE app_settings (key TEXT PRIMARY KEY, value TEXT NOT NULL DEFAULT '');
-- 키 목록:
-- apst_dir       : APST 파일 디렉터리 경로
-- ddr1_dir       : DDR1 로그 디렉터리 경로
-- cml_path       : CML 매핑 파일 경로
-- report_dir     : PDF 저장 루트 경로
-- logo_path      : 광주MBC 로고 이미지 경로
-- seal_path      : 직인 이미지 경로
-- admin_password : 관리자 비밀번호 (초기값: admin)
-- watcher_enabled: 폴더 감시 상태 ('1'=활성, '0'=비활성)
```

### ddr1.db — `broadcasts`

```sql
CREATE TABLE broadcasts (
    id                 INTEGER PRIMARY KEY AUTOINCREMENT,
    broadcast_date     TEXT NOT NULL,
    broadcast_time     TEXT NOT NULL,
    broadcast_hour     INTEGER NOT NULL,
    clip_id            TEXT NOT NULL,
    item_name_raw      TEXT,
    item_name          TEXT,
    content_type_label TEXT,                   -- '캠페인' 또는 'ID'
    grade              TEXT,                   -- 급지: SA/A/B/C (미분류 시 NULL)
    duration_sec       INTEGER,
    source_file        TEXT,
    created_at         TEXT DEFAULT (datetime('now'))
);
```

### ddr1.db — `clip_map`

```sql
CREATE TABLE clip_map (
    clip_id      TEXT PRIMARY KEY,
    item_type    TEXT,
    full_name    TEXT,
    advertiser   TEXT,
    duration_sec INTEGER
);
```

---

## API 설계 ✅ 구현 완료

### 인증

| Method | Path | 설명 |
|--------|------|------|
| POST | `/api/auth/login` | `{username, password}` → 성공 시 `{success: true}` |
| POST | `/api/auth/logout` | 로그아웃 (서버 stateless) |
| PUT  | `/api/auth/password` | `{current_password, new_password}` |

### 대시보드

| Method | Path | 설명 |
|--------|------|------|
| GET | `/api/dashboard?year=&month=&type=` | 소재별·시간대별 집계 |

### 달력

| Method | Path | 설명 |
|--------|------|------|
| GET | `/api/calendar?year=&month=&type=` | 날짜별 송출 건수 (`type`: 캠페인\|ID, 없으면 전체) |
| GET | `/api/calendar/day?date=YYYY-MM-DD&type=` | 특정 날짜 내역 (grade 포함) |

### 상세조회

| Method | Path | 설명 |
|--------|------|------|
| GET | `/api/period?start_date=&end_date=&start_hour=&end_hour=&type=&item=&source=` | 복합 필터 조회 |

- `source`: `apst`=자동, `ddr1`=수동, 없으면 전체
- `item`: **완전일치**로 필터 (`item_name = ?`). 프론트엔드가 `/api/items`로 후보를 먼저 정확히 1개로 확정한 뒤 전달하는 것을 전제로 함 — 부분검색이 아님 (과거 LIKE 부분검색 버그 수정됨)

### 소재 검색

| Method | Path | 설명 |
|--------|------|------|
| GET | `/api/items?q=검색어&limit=30` | 소재명 부분 검색 |
| GET | `/api/items/all?limit=200` | 전체 소재 목록 |

### 리포트 + PDF

| Method | Path | 설명 |
|--------|------|------|
| GET | `/api/report?item=&year=&month=` | F-04 날짜별 송출 데이터 조회 |
| GET | `/api/report/pdf?item=&year=&month=` | F-04 PDF 다운로드 |
| GET | `/api/report/daily?date=` | F-06 일별 SB 내역 조회 |
| GET | `/api/report/daily/pdf?date=` | F-06 PDF (apst_dir 자동 사용) |
| GET | `/api/report/disaster?date=` | F-07 재난방송 소재 조회 |
| GET | `/api/report/disaster/pdf?date=` | F-07 PDF (apst_dir 자동 사용) |
| GET | `/api/report/daily-summary?date=&type=캠페인\|ID` | F-08/F-09 소재별 총횟수+급지별 횟수 조회 |
| GET | `/api/report/daily-summary/pdf?date=&type=캠페인\|ID` | F-08/F-09 PDF 다운로드 |

> F-06/F-07: `apst_dir` 환경설정에서 파일 경로 자동 조회, 수동 입력 불필요

### 파일 적재

| Method | Path | 설명 |
|--------|------|------|
| POST | `/api/ingest/cml` | CML 파일 업로드 → clip_map 갱신 |
| POST | `/api/ingest/apst` | APST 파일 업로드 → DB 적재 |
| POST | `/api/ingest/ddr1` | DDR1 파일 업로드 (`broadcast_date` 필요) |
| POST | `/api/ingest/apst/scan` | apst_dir 전체 스캔 적재 |
| POST | `/api/ingest/ddr1/scan` | ddr1_dir 전체 스캔 적재 (파일명 날짜 자동 추출) |
| GET  | `/api/ingest/status` | DB 적재 현황 (날짜 범위, 건수) |
| GET  | `/api/ingest/watcher` | 폴더 감시 상태 + 이벤트 로그 |
| POST | `/api/ingest/watcher/start` | 폴더 감시 시작 |
| POST | `/api/ingest/watcher/stop` | 폴더 감시 중지 |
| GET  | `/api/ingest/watcher/log` | 이벤트 로그 조회 (최근 100건) |

### 광고주 관리

| Method | Path | 설명 |
|--------|------|------|
| GET | `/api/advertisers` | 전체 목록 |
| GET | `/api/advertisers/{item_name}` | 단건 조회 |
| POST | `/api/advertisers` | 등록 |
| PUT | `/api/advertisers/{item_name}` | 수정 |
| DELETE | `/api/advertisers/{item_name}` | 삭제 |

### 환경설정

| Method | Path | 설명 |
|--------|------|------|
| GET | `/api/settings` | 전체 설정 조회 |
| PUT | `/api/settings` | 설정 저장 |

---

## 집계 로직

### 급지(SA/A/B/C) 분류 ✅ 신규

```python
# parsers/utils.py
_GRADE_RANGES = [
    ("SA", [(19*60+30, 23*60+30)]),
    ("A",  [(8*60+30, 9*60+30), (19*60, 19*60+30), (23*60+30, 24*60)]),
    ("B",  [(7*60, 8*60+30), (9*60+30, 12*60), (18*60, 19*60), (0, 60)]),
    ("C",  [(60, 7*60), (12*60, 18*60)]),  # ✅ 12~18시 C급 포함 (총횟수=SA+A+B+C 합계 불일치 버그 수정)
]

def classify_grade(time_str: str) -> str | None:
    """'HH:MM:SS' → SA/A/B/C. 모든 시간대가 분류됨(미분류 없음)."""
    h, m = map(int, time_str.split(":")[:2])
    total = h * 60 + m
    for label, ranges in _GRADE_RANGES:
        for start, end in ranges:
            if start <= total < end:
                return label
    return None
```

- `apst_parser.py`, `ddr1_parser.py` 모두 레코드 생성 시 `classify_grade(time_str)` 호출하여 `grade` 필드 채움
- DB 마이그레이션: `database.py`의 `_ensure_column()` + `_backfill_grade()`가 서버 시작 시 자동 실행 (기존 데이터의 NULL grade를 일괄 계산)

### APST 저장 판별 ✅ 수정 (Con 코드 재정의)

```python
def _get_store_type(con: str) -> str | None:
    if con == "K":  return "캠페인"
    if con == "I":  return "ID"
    return None   # C(이어서)/G(광고그룹)/AIR(프로그램) → 저장 안 함
```

- Con 코드: `C`=이어서, `G`=광고그룹, `K`=캠페인, `I`=ID, `AIR`=프로그램
- 과거 ID 판별 조건이 `Con == "IDC"`였으나 실제 데이터에는 거의 등장하지 않아 ID 소재가 누락되는 버그가 있었음. 실제 ID 소재의 Con 값은 `I`로 정정.
- 과거 `Con=K` 항목 중 `"ID민"` 포함 시 제외하던 로직은 제거 — Con 코드만으로 정확히 구분되므로 불필요.

### `program_block`(그룹명) 결정 ✅ 수정

`lstGrp` 안에서 하나의 SB 띠는 두 그룹이 짝을 이룬다:
- 그룹1 (`EvtGrp.eTy == "S"`): 이어서/광고그룹/캠페인/ID 소재 목록(`lstPgm`)
- 그룹2 (`EvtGrp.eTy == "P"`, 그룹1과 동일 `EvtGrp.eID`): 프로그램(`AIR`) 소재 1개

그룹1에 속한 소재들의 `program_block`은 자기 자신의 `_GrpName_`이 아니라 **짝이 되는 그룹2의 `EvtGrp.eName`**을 사용한다 (`apst_parser.py`의 `_resolve_group_name()`).

### DDR1 저장 판별

```python
def classify_ddr1_clip(clip_id, cml_map, campaign_names) -> str | None:
    entry = cml_map.get(clip_id)
    if not entry:   return None
    full_name = entry["full_name"]
    clean_name = extract_item_name(full_name)
    if "ID" in full_name:            return "ID"
    if clean_name in campaign_names: return "캠페인"
    return None
```

### 두 DB UNION 집계 (대시보드 — 급지별 횟수 포함)

```sql
-- 두 DB 모두 캠페인·ID만 저장되어 있으므로 별도 필터 불필요
SELECT item_name, content_type_label,
       COUNT(*) AS count,
       SUM(CASE WHEN grade='SA' THEN 1 ELSE 0 END) AS sa_count,
       SUM(CASE WHEN grade='A'  THEN 1 ELSE 0 END) AS a_count,
       SUM(CASE WHEN grade='B'  THEN 1 ELSE 0 END) AS b_count,
       SUM(CASE WHEN grade='C'  THEN 1 ELSE 0 END) AS c_count
FROM (
    SELECT item_name, content_type_label, grade FROM apst.broadcasts
    WHERE broadcast_date BETWEEN :start AND :end
    UNION ALL
    SELECT item_name, content_type_label, grade FROM ddr1.broadcasts
    WHERE broadcast_date BETWEEN :start AND :end
)
GROUP BY item_name, content_type_label ORDER BY count DESC;
```

### 일일 운행표/일일 ID 운행표 (`get_daily_item_summary`)

```sql
SELECT item_name,
       COUNT(*) AS total_count,
       SUM(CASE WHEN grade='SA' THEN 1 ELSE 0 END) AS sa,
       SUM(CASE WHEN grade='A'  THEN 1 ELSE 0 END) AS a,
       SUM(CASE WHEN grade='B'  THEN 1 ELSE 0 END) AS b,
       SUM(CASE WHEN grade='C'  THEN 1 ELSE 0 END) AS c
FROM (
    SELECT item_name, grade FROM apst.broadcasts
    WHERE broadcast_date = :date AND content_type_label = :type
    UNION ALL
    SELECT item_name, grade FROM ddr1.broadcasts
    WHERE broadcast_date = :date AND content_type_label = :type
)
GROUP BY item_name ORDER BY total_count DESC;
```

---

## 폴더 감시 설계 (file_watcher.py)

- 라이브러리: `watchdog`
- 실행: FastAPI startup 훅에서 자동 시작 (이전 상태 복원)
- 이벤트:
  - `on_created` / `on_moved` (FTP rename 방식 대응)
  - 파일 쓰기 완료 대기: 1.5초 지연 후 파싱
- 새 파일 적재 흐름:
  1. `.apst` → `parse_apst()` → apst.db INSERT → `find_manual_segments()`로 수동 송출 구간 탐지 → `_ingest_manual_segments()` → ddr1.db INSERT
  2. `.Log`  → 파일명에서 날짜 추출 → `parse_ddr1()` → ddr1.db INSERT
  3. `.cml`  → `parse_cml()` → clip_map 전체 갱신
- 중복 적재 방지: `source_file` 컬럼 확인 (수동 송출 구간은 `manual:<로그파일명>:<트리거clip_id>` 형식으로 별도 분리)
- 이벤트 로그: 메모리 내 최근 100건 유지

---

## 수동 송출(DDR1) 구간 추출 설계 ✅ 신규

### 배경
APST의 이어서(`Con=C`) 소재 중 주장비명(`MM`)이 `DDR4`(정상 자동 송출)가 아니라 `DDR1`인 경우는
운영자가 DDR1 장비로 수동 개입하여 송출한 것이다. 이 경우 APST 스케줄에는 캠페인/ID 소재가
비어있거나(전부 수동으로 대체) 실제 송출 내용과 다를 수 있어, DDR1 로그를 직접 분석해
실제 송출된 소재를 복원해야 한다.

### DDR1 로그 이벤트 패턴 ✅ 시간 산출 방식 수정 (2026-06)
- SB 띠 시작: `I : Play CLIP : <이어서 clip_id>` — 이어서 소재만 명시적으로 기록됨
- 두 번째 소재부터: 명시적인 `Play CLIP` 기록 없이, `O : Play Clip Change Tc : ...` 라인의
  타임스탬프가 실제 전환(= 진짜 송출 시작) 시점이다. 이 라인엔 clip_id가 없으므로, 그 직전의
  `O : Load ID : <clip_id>` 또는 `O : 3Sec Re Load ID : <clip_id>`에서 clip_id를 가져온다.
- ⚠️ `O : OnAir ID : <clip_id>, SOM:..., EOM:...` 라인은 **시작 시간으로 쓰면 안 됨** — 그 소재가
  거의 다 재생된 뒤(재생 종료 16~20초 전, 다음 소재 Load와 동시)에야 찍히는 상태 확인 라인이라
  실제 시작보다 훨씬 늦다. 과거 이 라인을 시작 시간으로 썼다가 (1) 모든 소재 시간이 16~20초씩
  늦게 기록되고 (2) `end_time` 경계 부근의 마지막 소재가 누락되는 버그가 있었음 (2026-05-01
  사례로 발견·수정: 07:46:33→07:46:37 등 시간 오차, 경계 근처 소재 1건 누락).
- 마지막 소재는 다음 `Play Clip Change`가 없을 수 있음(운영자가 중간에 정지하는 경우 등) —
  이미 전환이 확인된 마지막 소재까지만 인정

### 추출 알고리즘 (`apst_parser.find_manual_segments` + `ddr1_parser.extract_manual_clips`)
1. `find_manual_segments(apst_path)`: APST에서 `Con=C` AND `MM=DDR1`인 이어서 소재를 찾아
   `{broadcast_date, start_time, end_time, trigger_clip_id, program_block}` 구간 목록 반환
   - `start_time` = 이어서 소재의 `OnT._sTimePartSec`
   - `end_time` = 짝이 되는 프로그램(AIR) 그룹의 `EvtGrp.On` (없으면 다음 그룹 첫 소재 시간으로 대체)
2. `extract_manual_clips(log_path, trigger_clip_id, start_time, end_time, tolerance_sec=5)`:
   - `start_time` ±5초 범위 내에서 `trigger_clip_id`와 일치하는 `Play CLIP` 라인 탐색 (시간 동기화 오차 보정)
   - 그 지점부터 `end_time`까지의 `Play Clip Change` 전환 이벤트(직전 `Load ID`로 clip_id 결정)를
     시간 순서대로 수집
3. `extract_manual_segment_records(segments, log_files_by_date, cml_map, campaign_names)`:
   - 각 클립을 `classify_ddr1_clip()`으로 캠페인/ID 분류
   - **CML에 없는 clip_id는 건너뛰지 않고, 소재명 대신 파일명(clip_id)을 그대로 기록** (`content_type_label='캠페인'`으로 처리)
   - `source_file = "manual:<로그파일명>:<트리거clip_id>"` — 일반 DDR1 적재와 중복 검사 범위 분리

### 연결 지점
- `routers/ingest.py`: `ingest_apst()`(단일 업로드), `scan_apst_dir()`(전체 스캔) — APST 적재 직후 `_insert_manual_segments()` 호출
- `services/file_watcher.py`: `_ingest_apst()` — 자동 감시로 새 APST 파일 적재 시 동일하게 `_ingest_manual_segments()` 호출
- 두 위치 모두 `ddr1_dir` 환경설정으로 로그 파일을 찾고, `clip_map`/캠페인 이름은 ddr1.db / apst.db에서 로드

### ✅ 레거시 `parse_ddr1()` 전체 로그 스캔 폐기 (2026-06)
실데이터 검증 결과, 로그 전체에서 독립적인 `Play CLIP : N######` 라인을 찾아 캠페인/ID로
분류하던 기존 방식은 신뢰할 수 없는 것으로 확인되어 **폐기**(`parse_ddr1()`은 항상 빈 리스트 반환):

1. **오탐(false positive)**: 운영자가 화면에서 단발성으로 미리보기/테스트 재생한 클립도
   `Play CLIP` 라인을 남기지만, 다음 소재로 이어지지 않는 단발성 재생이라 실제 송출이 아님
   (예: 2026-05-01 07:33:37 우리아이치과(틀니) — OnAir 확인조차 없음, 08:25:51 518재단 —
   자기 자신만 OnAir 후 바로 정지, 다음 소재로 이어지지 않음).
2. **중복**: 단발성 여부를 "다음 소재로 이어지는 연속성"으로 검증해도, DDR1 장비가
   (`MM=DDR1`로 표시되지 않은) 정상 자동 송출 SB 띠까지 함께 기록하고 있어, apst.db에
   이미 저장된 자동 송출 내역과 거의 동일한 시각의 중복 데이터가 다시 적재됨.

→ 수동 송출 여부를 신뢰성 있게 판별할 수 있는 유일한 기준은 APST에서 명시적으로
`MM=DDR1`로 표시된 이어서 소재뿐이다. 모든 수동 송출 내역은 `find_manual_segments()` +
`extract_manual_clips()`/`extract_manual_segment_records()`를 통해서만 추출한다.
`/api/ingest/ddr1`, `/api/ingest/ddr1/scan` API와 `parse_ddr1()` 시그니처는 하위 호환을
위해 유지하되, 더 이상 broadcasts 레코드를 생성하지 않는다.

---

## 달력(CalendarView) 상세 설계 ✅ 신규

### 레이아웃 — Drawer 대신 리사이즈 가능한 분할 패널
- antd `Drawer`는 오버레이(포털)로 렌더링되어 본문 레이아웃과 무관하게 달력을 가리는 문제가 있어 **제거**
- `display:flex` 컨테이너 안에 좌측(달력, `flex:1`, 최소 420px) + 8px 드래그 핸들 + 우측(상세 패널, 기본 520px, 최소 360px)을 같은 행에 배치
- 드래그 리사이즈: `mousedown`(시작) → `window` 레벨 `mousemove`/`mouseup` 리스너로 폭 계산
  - `panelWidthRef`(useRef)로 최신 폭을 동기 추적 → `stopResize`의 stale closure로 인해 옛 폭이 저장되는 문제 방지

### 날짜 셀 커스터마이징
- antd 기본 날짜 숫자(`.ant-picker-calendar-date-value`)는 CSS `display:none`으로 숨기고, `cellRender`에서 직접 렌더링
  - 이유: CSS만으로는 "01"→"1" 같은 텍스트 포맷 변경이 불가능하므로 완전히 자체 렌더링 필요
- antd 기본 "선택됨" 배경(controlled `value`가 항상 1일이라 1일이 늘 선택된 것처럼 보이던 문제)도 CSS로 무력화하고, `selectedDate` state로 직접 관리

### 상태 유지 버그와 수정 (★중요)
- **문제**: 범용 `save(patch)` 헬퍼가 매 호출마다 `current/typeFilter/countMap/panelWidth/panel/selectedDate` 전체를 스냅샷하여 store에 덮어쓰는 구조였음.
  비동기 콜백(`onSelect`의 `await getDayDetail(...)` 이후) 내부에서 호출된 `save({panel: next})`가 **클릭 시점 이전 렌더의 stale `selectedDate` 값**을 기본값으로 함께 덮어써, 메뉴 이동 후 복귀 시 우측 패널 데이터는 맞는데 달력의 강조 표시(선택일)만 다른 날짜로 보이는 버그 발생
- **수정**: 전체 스냅샷 방식의 `save()`를 제거하고, `patchStore(patch) = setStore(STORE_KEY, patch)` 형태로 **호출부마다 변경할 필드만 명시적으로 병합**하도록 전면 교체. (다른 컴포넌트에서 유사 패턴을 새로 만들 경우 이 함정을 피할 것)

### 휴일 표시
- `HOLIDAYS` 객체에 2025~2027년 공휴일(고정일+대체공휴일+음력 환산 근사치) 하드코딩
- 토(`day()===6`)/일(`day()===0`)/공휴일 매칭 시 날짜 숫자 빨간색

### CSV 내보내기
- `downloadCSV(filename, headers, rows)` — UTF-8 BOM(`﻿`) 포함 Blob 생성 후 `<a download>` 클릭으로 다운로드 (엑셀 한글 깨짐 방지)
- "송출내역" 표와 "소재별 송출 횟수" 표 각각 제목 옆에 독립된 CSV 저장 버튼

---

## 프론트엔드 상태 유지 (store.js)

```js
// 모듈 레벨 전역 객체 — 탭 이동 시에도 유지, 새로고침 시 초기화
const _store = {}
export const getStore = (key) => _store[key] ?? {}
export const setStore = (key, partial) => { _store[key] = { ..._store[key], ...partial } }
```

⚠️ **사용 패턴 주의**: 위 "달력 상태 유지 버그" 항목 참조 — 비동기 콜백에서 store에 저장할 때는
전체 상태를 스냅샷하는 헬퍼 대신, 변경된 필드만 `setStore(key, {그 필드만})`으로 병합할 것.

- 대시보드: `year, month, type, data, pageSize, currentPage`
- 달력: `current, typeFilter, countMap, panelWidth, panel, selectedDate`
- 상세조회: `dateRange, startHour, endHour, typeFilter, sourceFilter, itemFilter, data`
- 소재별 월 리포트: `item, year, month, data`
- 방송 운행표/재난방송: `date, dailyData, disasterData, activeResult`
- 일일 운행표/일일 ID 운행표: `date, data` (각각 별도 store 키)

---

## 관리자 인증 설계

- **서버 stateless** — 토큰 없음
- 프론트엔드 `isAdmin` React state로 UI 분기
- 로그인: `POST /api/auth/login` → 성공 시 `isAdmin = true`
- 로그아웃: `isAdmin = false`, 관리자 전용 페이지 접근 시 대시보드로 이동
- 비밀번호: `app_settings.admin_password` 컬럼에 평문 저장
- 관리자 전용 라우트: `/ingest`, `/advertiser`, `/settings` — 비관리자 접근 시 "권한 없음" 화면
- 관리자 모드 표시는 **사이드바 하단**에서만 (이전에는 상단 Header에도 배지가 있었으나 Header 자체가 제거되어 사라짐)

---

## PDF 리포트 설계

### F-04 — 소재별 월 리포트

- 파일명: `sb_monthly_{소재명}_{YYYYMM}.pdf`
- 저장: `reports/monthly/`
- 로고·직인: `app_settings.logo_path`, `app_settings.seal_path` 에서 동적 로드
- TV 시간 형식: `HHMM` (25시제: 자정~04:59 → +24시간)

### F-06 — 일별 SB 내역

- 파일명: `sb_daily_YYYYMMDD.pdf`
- 저장: `reports/daily/`
- 데이터 소스: `apst_dir`에서 해당 날짜 파일 자동 검색 (YYYYMMDD 포함 파일명)
- 컬럼: 방송시작시간 / 프로그램명 / SB 소재 제목

### F-07 — 일별 재난방송

- 파일명: `disaster_report_YYYYMMDD.pdf`
- 저장: `reports/disaster/`
- 필터: `item_name_raw`에 "재난" 포함
- 재난 없을 시: "해당 없음" 문구 포함 빈 PDF 생성

### F-08/F-09 — 일일 운행표 / 일일 ID 운행표 ✅ 신규

- 파일명: `campaign_summary_YYYYMMDD.pdf` (캠페인) / `id_summary_YYYYMMDD.pdf` (ID)
- 저장: `reports/summary/`
- 컬럼: 소재명 / 총횟수 / SA / A / B / C + 마지막 "총계" 행
- 강조색: 캠페인=`#1677ff`, ID=`#722ed1`
- 데이터: `get_daily_item_summary(date, content_type_label)` 결과 그대로 사용 (총횟수 내림차순)

---

## 2026-07 설계 추가·변경

### 공익/재난 저장 판별 (`apst_parser._decide_store_type`)
```
con == I                         → ID
con in {C, G, AIR, SBC}          → 저장 안 함
con == K                         → 공익/재난 이름 + '방송 종료 안내' 프로그램이면 공익재난, 아니면 캠페인
그 외(PRM, R, F, E, …)           → 이름에 공익/재난 있으면 공익재난, 없으면 저장 안 함
```
- 공익재난은 SrcID N-필터 예외(재난 R 소재는 SrcID가 `K0000…`). 캠페인/ID는 기존대로 N-형식만.
- 일회성 마이그레이션: `server/migrate_gongik_jaenan.py` (파일 재스캔 → 공익재난 upsert + PRM duration 보정).

### 공익/재난 집계 (DB 기반, `report._query_gongik_jaenan_db`)
- apst.db: `content_type_label='공익재난'` OR (`캠페인` AND 소재명 ⊇ {공익, 재난, 포함키워드})
- ddr1.db: 소재명(raw/정제) ⊇ {공익, 재난, 포함키워드} — **수동송출 포함**
- 제외 키워드가 소재명에 있으면 결과에서 제거, 각 행 `_gj_kind`(공익/재난, 재난 우선) 부여
- 포함/제외 키워드는 `_get_gj_keywords()`가 `app_settings`에서 읽음(`gongik_include_keywords` 등)
- 월별(`_gather_gongik_jaenan_monthly`)·흘림자막(`_gather_subtitle_campaign`)이 공용 사용
- ⚠️ 이 변경으로 기존 파일 기반 `_parse_calendar_month_items`는 월별에서 미사용

### 방송운행표 표시 규칙 (`report._parse_all_for_date`, 파일 기반)
- `_expand_manual_items`(수동송출 확장) 이후 최종 패스에서 라벨 보정:
  - 소재제목에 `\bID\b` → `ID`
  - '방송 종료 안내' 프로그램 → 공익/재난 포함 시 con 무관 `공익재난`
  - 그 외 → 원래 공익재난 소재(PRM·R 등)만 `공익재난`, K는 `캠페인` 유지
- `parse_apst_all._resolve_content_type_label`: P/AIR→프로그램, SBC→광고, IDC/F/E→기타, PRM+'시보'→시보

### 방송운행표 스타일 (화면/PDF/Word 공통)
- 프로그램 행=하늘색(#DCE6F1), 광고/광고그룹=연두색(#E2EFDA), 단 program_block ⊇ '방송순서'는 음영 제외
- 프로그램 경계·'방송 종료 안내' 시작=위쪽 굵은 선, 헤더 상·하단 굵은 선
- 화면: `ReportView.jsx` `_dailyRowClass` + scoped CSS(`.daily-report-wrap`), 페이지네이션 제거
- PDF: `generate_daily_pdf`에서 표 전체 흰색으로 덮어 zebra 제거(공용 `_base_table_style`는 유지)

### FTP 가져오기 (`services/ftp_fetcher.py`)
- `_download_date(date)`: FTP 홈/apst·ddr1_log·cml에서 파일명에 `YYYYMMDD` 포함 파일을 종류별 로컬 폴더로 수신
- `fetch_and_ingest`: 다운로드 → `ingest_date` 적재 → `daily_fetch`(ok/missing/error) 기록
- 스케줄러: 매일 `ftp_fetch_time`에 전날 파일 수집. 실패 시 `_RETRY_INTERVAL_SEC=120`s 간격 `_MAX_RETRIES=5`회 재시도, 성공/파일없음/소진 시 종료
- `routers/ftp.py`: `/ftp/test`, `/ftp/fetch?date=`, `/ftp/fetch-yesterday`

### 접근 제한 (`main.py`)
- 요청 미들웨어가 `app_settings.allowed_ip_ranges`를 매 요청 로드 → `ipaddress`로 대역 판정
- `0.0.0.0` 포함 시 전체 허용, `127.0.0.1`/`::1`은 항상 허용(저장 즉시 반영)

### 공용 XLSX 내보내기
- 서버 `routers/export.py`: `POST /api/export/xlsx {filename, sheet_name, headers, rows}` → openpyxl 생성(헤더 굵게·열너비 자동)
- 클라이언트 `src/xlsx.js` `downloadXLSX()`가 계산된 표 데이터를 POST → Blob 다운로드
- 대시보드·달력·상세조회·소재목록 4개 화면 CSV 로직 제거 후 공용 헬퍼로 대체

### 설정키 변경 요약 (`config.SETTINGS_KEYS`)
- 추가: `ftp_host/port/user/password/fetch_time`, `allowed_ip_ranges`,
  `gongik_include_keywords`, `jaenan_include_keywords`, `gongik_jaenan_exclude_keywords`
- 제거: `report_dir`(미사용)
- 시딩 전용 기본값(비워도 복구 안 함): 공익/재난 키워드 3종 — `init_db`에서 `_seed_defaults`로 분리
