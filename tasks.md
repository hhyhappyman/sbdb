# Tasks — SB 송출 대시보드

## 진행 상황 범례
- `[ ]` 미시작
- `[~]` 진행 중
- `[x]` 완료
- `[!]` 블로커 (확인 필요)

---

## Phase 0. 준비 및 분석 ✅ 완료

- [x] 세 가지 데이터 파일 구조 분석 (apst / ddr1 log / cml)
- [x] `spec_01_apst_format.md` 작성
- [x] `spec_02_ddr1_log_format.md` 작성
- [x] `spec_03_cml_format.md` 작성
- [x] `requirements.md` 작성 및 최신화
- [x] `design.md` 작성 및 최신화
- [x] F-04 PDF 레이아웃 확정 — "광주MBC 방송홍보 SB송출 현황" 양식
- [x] F-07 재난 소재 없을 때 → 빈 PDF 생성 ("해당 없음" 문구)
- [x] 소재종류 확정 → 캠페인(Con=K) + ID(Con=IDC) 두 가지만 저장·보고서 대상
- [x] APST 집계 규칙 → Con=K(캠페인), Con=IDC(ID), "ID민" 포함 시 제외
- [x] DDR1 집계 규칙 → CML명 "ID"포함→ID, APST 캠페인 목록 대조→캠페인, 나머지 제외
- [x] 파일 경로 → 앱 환경설정 메뉴에서 사용자 입력 (DB 저장)
- [!] 텔레그램 봇 접근 허용 사용자 범위 → 미확정 (Phase 5에서 결정)

---

## Phase 1. 백엔드 기반 구축 ✅ 완료

### 1-1. 프로젝트 초기 설정
- [x] `requirements.txt` 작성 (fastapi, uvicorn, reportlab, watchdog, python-telegram-bot 등)
- [x] `server/config.py` — DB 경로, CORS, 관리자 기본값 등 코드 레벨 고정값
- [x] `server/database.py` — SQLite 연결 컨텍스트 매니저, 스키마 초기화
  - apst.db: broadcasts, advertisers, app_settings (admin_password 기본값 포함)
  - ddr1.db: broadcasts, clip_map
- [x] `server/routers/settings.py` — 환경설정 GET/PUT API
- [x] `server/routers/advertisers.py` — 광고주 CRUD API
- [x] `server/routers/auth.py` — 로그인/로그아웃/비밀번호 변경 API

### 1-2. 파일 파서
- [x] `server/parsers/utils.py` — `extract_item_name()` 소재명 정제 공통 유틸
- [x] `server/parsers/cml_parser.py` — CML 파싱 (CP949), clip_map 딕셔너리 반환
- [x] `server/parsers/apst_parser.py`
  - `parse_apst()`: 캠페인·ID 소재만 추출
  - `parse_apst_all()`: F-06/F-07용 전체 아이템 추출
  - `_get_store_type()`: Con 코드 → 소재종류 판별
  - [x] **버그 수정** (2026-06): ID 소재의 실제 Con 값이 `IDC`가 아니라 `I`였음 → ID 소재가 거의 누락되던 문제 해결. `"ID민"` 이름 기반 제외 로직 제거 (Con 코드만으로 정확히 구분되므로 불필요)
  - [x] **버그 수정** (2026-06): `program_block`(그룹명)을 자기 그룹의 `_GrpName_` 대신, 짝이 되는 `AIR` 그룹(`EvtGrp.eTy="P"`)의 `EvtGrp.eName`으로 저장하도록 `_resolve_group_name()` 추가
  - [x] **신규 항목 추가** (2026-06): 소재 내용의 `MM`(주장비명) 필드를 `main_equipment` 컬럼으로 DB 저장. `database.py`에 컬럼 마이그레이션(`_ensure_column`) 추가, `ingest.py`/`file_watcher.py`의 APST INSERT문에 반영
- [x] `server/parsers/ddr1_parser.py`
  - `parse_ddr1()`: ⚠️ 2026-06 폐기 — 항상 빈 리스트 반환 (아래 "레거시 방식 폐기" 참조)
  - `classify_ddr1_clip()`: 소재종류 판별
  - [x] **신규 기능** (2026-06): 수동 송출(주장비명=DDR1) 구간 추출
    - `apst_parser.find_manual_segments()`: `Con=C`(이어서) AND `MM=DDR1`인 소재의 SB 띠 구간(시작/종료 시간, 트리거 clip_id) 탐지
    - `ddr1_parser.extract_manual_clips()`: 트리거 `Play CLIP` 이벤트를 ±5초 오차 허용으로 매칭, 이후 `OnAir ID` 전환 이벤트를 순서대로 추출
    - `ddr1_parser.extract_manual_segment_records()`: 추출된 클립을 CML로 소재명 변환 후 ddr1.db 레코드로 변환. **CML에 없는 clip_id는 건너뛰지 않고 소재명 대신 파일명을 기록**
    - `routers/ingest.py`(`_insert_manual_segments`), `services/file_watcher.py`(`_ingest_manual_segments`) — APST 적재 직후 자동 연결
    - `source_file = "manual:<로그파일명>:<트리거clip_id>"` 형식으로 일반 DDR1 적재와 중복 검사 분리
    - 검증: 2026-05-06 샘플 데이터 기준 2개 수동 구간에서 13건 정상 추출, 전체 재스캔 시 총 7,289건 추가 적재 확인
  - [x] **버그 수정 + 레거시 방식 폐기** (2026-06): `parse_ddr1()`의 전체 로그 "Play CLIP" 단독 스캔 방식이
    (1) 운영자의 단발성 테스트 재생을 진짜 송출로 오인하고, (2) 정상 자동 송출(apst.db에 이미 기록됨)까지
    중복 적재하는 문제를 발견 → 신뢰할 수 없는 것으로 판단해 폐기, 함수는 항상 `[]` 반환
    - 실데이터 검증: 2026-05-01 07:33:37 우리아이치과(틀니)(OnAir 확인 없는 단발 클릭), 08:25:51 518재단(자기 자신만 OnAir 후 바로 정지, 연속 안 됨) — 둘 다 가짜 "수동 송출"이었음을 확인 후 제거
    - `routers/ingest.py`, `services/file_watcher.py`의 DDR1 업로드/스캔/감시 경로는 API 호환을 위해 유지하되 더 이상 broadcasts 레코드를 생성하지 않음
  - [x] **버그 수정** (2026-06): 수동 송출 소재의 시작 시간 산출 기준을 `OnAir ID`에서 `Play Clip Change`로 변경
    - `OnAir ID` 라인은 해당 소재가 거의 다 재생된 뒤(종료 16~20초 전)에야 찍히는 상태 확인 라인이라 실제 시작보다 훨씬 늦음 — 모든 소재 시간이 16~20초씩 늦게 기록되고, `end_time` 경계 부근 소재 1건이 누락되는 버그로 이어짐
    - `Play Clip Change Tc : ...` 라인의 타임스탬프 + 그 직전 `Load ID`/`3Sec Re Load ID`로 얻은 clip_id 조합으로 변경
    - 실데이터 검증(2026-05-01): 07:45:02/07:45:22/07:45:42/07:46:37 등 사용자가 로그에서 직접 확인한 시간과 정확히 일치, 경계 부근에서 누락됐던 N280296(07:53:48) 항목 복원 확인
  - [x] **신규**: `routers/report.py`의 방송 운행표(F-06) 전용 수동 구간 표시에서, 캠페인/ID로 분류되지 않는 클립(주로 `CM########` 지역 광고)을 건너뛰지 않고 "광고"로 표시 (ddr1.db에는 기존처럼 캠페인/ID만 저장, 화면 표시만 확장)
    - 기존 DB의 비-수동(`source_file NOT LIKE 'manual:%'`) DDR1 레코드 96건 삭제 정리

### 1-3. 집계 서비스
- [x] `server/services/aggregator.py`
  - `get_item_counts()`: 소재별 횟수 집계
  - `get_hourly_counts()`: 시간대별 횟수 집계
  - `get_daily_counts()`: 달력용 날짜별 건수
  - `get_broadcasts_by_date()`: 날짜 상세 내역
  - `get_period_broadcasts()`: 상세조회 (날짜범위·시간·소재명·송출구분 필터)
  - `get_item_monthly_report()`: F-04 날짜별 송출 시간 목록
  - `search_items()`: 소재명 부분 검색
  - `get_campaign_names()`: DDR1 분류용 캠페인 이름 집합

---

## Phase 2. API 구현 ✅ 완료

- [x] `server/main.py` — FastAPI 앱, 라우터 등록, startup/shutdown 훅
- [x] `server/routers/dashboard.py` — GET /api/dashboard
- [x] `server/routers/calendar.py` — GET /api/calendar, /api/calendar/day
- [x] `server/routers/period.py` — GET /api/period (날짜범위·시간·소재명·송출구분)
- [x] `server/routers/report.py`
  - F-04: GET /api/report, /api/report/pdf
  - F-06: GET /api/report/daily, /api/report/daily/pdf (apst_dir 자동 사용)
  - F-07: GET /api/report/disaster, /api/report/disaster/pdf (apst_dir 자동 사용)
- [x] `server/routers/ingest.py`
  - POST /api/ingest/cml|apst|ddr1 (단일 파일 업로드)
  - POST /api/ingest/apst/scan, /ddr1/scan (폴더 전체 스캔)
  - GET /api/ingest/status (DB 적재 현황)
  - GET|POST /api/ingest/watcher, /watcher/start, /watcher/stop, /watcher/log
- [x] `server/routers/items.py` — GET /api/items (소재명 검색)

---

## Phase 3. PDF 생성 ✅ 완료

- [x] `server/services/pdf_generator.py` — reportlab 기반
  - `generate_monthly_pdf()`: F-04 "광주MBC 방송홍보 SB송출 현황" 양식
    - 25시제 시간 변환 (`HH:MM:SS` → `HHMM`, 자정 이후 +24시간)
    - 로고·직인: `app_settings.logo_path`, `app_settings.seal_path` 동적 로드
    - 광고주 정보: `advertisers` 테이블 조회
  - `generate_daily_pdf()`: F-06 일별 SB 내역 (방송시작시간/프로그램명/소재제목)
  - `generate_disaster_pdf()`: F-07 재난방송 (소재 없을 시 빈 PDF 생성)
- [x] 한국어 폰트 자동 감지 (NanumGothic, UnDotum, malgun.ttf 순서)

---

## Phase 3-ext. 폴더 감시 (watchdog) ✅ 완료

- [x] `server/services/file_watcher.py`
  - `start_watching()` / `stop_watching()` / `get_watcher_status()`
  - `.apst` → APST 자동 적재
  - `.Log` → DDR1 자동 적재 (파일명에서 YYYYMMDD 날짜 추출)
  - `.cml` → clip_map 자동 갱신
  - FTP rename 방식 대응 (`on_moved` 이벤트)
  - 이벤트 로그 최근 100건 메모리 보관
  - 서버 재시작 시 `app_settings.watcher_enabled` 기준으로 자동 재개

---

## Phase 4. 프론트엔드 구현 ✅ 완료

### 4-1. 기반 설정
- [x] `client/` — Vite + React 초기화
- [x] `vite.config.js` — /api 프록시 설정 (:5173 → :8000)
- [x] `src/api/index.js` — 모든 API 호출 함수
- [x] `src/store.js` — 탭 이동 후 상태 유지 전역 메모리 저장소
- [x] `src/main.jsx` — antd 한국어 locale, dayjs 한국어 설정
- [x] `.vscode/tasks.json` — Ctrl+Shift+B 단축키 설정

### 4-2. 레이아웃 및 인증
- [x] `src/App.jsx`
  - 고정 사이드바 (180px) + 메인 콘텐츠 레이아웃
  - `isAdmin` 상태로 메뉴 분기 (일반 4개 / 관리자 추가 3개)
  - 사이드바 하단 "관리자" 버튼 → 로그인 모달
  - 사이드바 로고: "방송"(구 "광주MBC") / "SB 송출 관리" — 두 줄 폰트 크기 동일(13px) ✅
  - 상단 Header(텍스트+띠) **완전 제거** — Content가 화면 맨 위부터 시작 ✅
  - 관리자 전용 URL 비인증 접근 시 "권한 없음" 화면

### 4-3. 페이지

#### Dashboard.jsx (F-01)
- [x] 좌측 소재별 횟수 테이블(SA/A/B/C 컬럼 포함), 우측 시간대별 차트
- [x] 페이지당 10/20/30/40/50개 선택
- [x] 페이지 이동 시 순위 번호 연속 (2페이지 → 11번부터)
- [x] 탭 복귀 시 마지막 검색 결과 유지 (store.js)
- [x] **차트 높이 고정(`CHART_HEIGHT = 428`)** — 페이지 크기 선택과 무관 ✅

#### CalendarView.jsx (F-02) ✅ 대개편 완료
- [x] 헤더에 종류 필터(전체/캠페인/ID, 기본 캠페인) 추가
- [x] antd 기본 날짜 숫자 숨기고 직접 렌더링 — 앞자리 0 제거, 폰트 30% 축소
- [x] 토/일/공휴일 빨간색 표시 (`HOLIDAYS` 2025~2027 데이터 내장)
- [x] 날짜 클릭 시 시안색 강조 (`selectedDate` 직접 관리, antd 기본 selected 무력화)
- [x] **Drawer 제거 → flex 분할 레이아웃**으로 교체 (달력이 패널에 가려지지 않음)
- [x] 마우스 드래그로 패널 폭 조절 (`panelWidthRef`로 stale closure 방지)
- [x] 상세 패널: ①소재별 횟수 요약(총횟수+SA/A/B/C) + ②시간순 목록, 둘 다 전체 컬럼 정렬 토글
- [x] CSV 저장 버튼 (①, ② 각각 제목 옆)
- [x] **표시 순서 변경**: "소재별 송출 횟수"를 위로, "송출내역"을 아래로 (`CalendarView.jsx`)
- [x] **상태 유지 버그 수정**: `save()` 전체 스냅샷 헬퍼 제거 → `patchStore()`로 필드별 직접 병합 (선택일이 메뉴 이동 후 다른 날짜로 보이던 stale closure 버그 해결)

#### PeriodView.jsx (F-03 상세조회)
- [x] 기간: RangePicker (달력 + 날짜 직접 선택, 연·월·일 모두)
- [x] 송출시간: 시작 시 ~ 끝 시 (지정 안 하면 24시간 전체)
- [x] 소재종류 + 송출구분(자동/수동) 필터
- [x] 소재명 검색 — **완전일치 확정 방식** ✅
  - 1개 매칭 → 자동으로 그 소재 조회
  - 0개/복수 매칭 → 선택 모달 표시 → 클릭 시 그 소재만 정확히 조회
  - 백엔드 `item_name = ?` 완전일치로 수정 (과거 LIKE 부분검색 버그 — "무등산" 선택해도 "무등산캠페인" 등 같이 검색되던 문제 해결)
- [x] 탭 복귀 시 마지막 검색 결과 유지

#### ReportView.jsx ("송출내역 출력" — F-04/F-06/F-07/F-08/F-09)
- [x] 탭 1 — 소재별 월 리포트 (F-04)
  - 소재명 직접 타이핑 가능
  - 조회 시: 정확 일치 → 바로 결과 / 불일치 → 유사 소재 목록 모달
  - 모달에서 소재 클릭 → 선택 즉시 리포트 조회
  - 송출 시간 표시를 `HH:MM`으로 축약 (초 단위 생략)
  - PDF 저장 버튼 별도 제공 / 탭 복귀 시 마지막 검색 결과 유지
- [x] 탭 2 — 방송 운행표 (F-06, 명칭 변경) / 재난방송 소재 (F-07)
  - 날짜 선택 → "방송 운행표" 클릭 → 화면에 결과 표시 → PDF 저장 버튼
  - 날짜 선택 → "재난방송 소재" 클릭 → 화면에 결과 표시 → PDF 저장 버튼
  - apst_dir 자동 사용 (경로 입력창 없음) / 빈 안내 Alert 제거
  - 탭 복귀 시 마지막 결과 유지
- [x] 탭 3 — 일일 운행표 (F-08, 캠페인 전용) ✅ 신규
  - 소재명/총횟수/SA/A/B/C, 소재명·총횟수 정렬 토글(기본 총횟수 내림차순)
  - PDF 저장 버튼
- [x] 탭 4 — 일일 ID 운행표 (F-09, ID 전용) ✅ 신규
  - F-08과 동일 구조, ID 소재만

#### IngestPage.jsx (파일 적재)
- [x] 폴더 실시간 감시 카드 (ON/OFF 스위치, 감시 폴더 표시, 이벤트 로그)
- [x] DB 적재 현황 카드 (자동·수동 건수, 날짜 범위)
- [x] 탭: CML / APST / DDR1 수동 업로드
- [x] APST/DDR1 탭: 전체 스캔 + 단일 파일 업로드 모두 지원
- [x] 파일 적재 순서 안내 (CML → APST → DDR1)

#### AdvertiserPage.jsx (광고주 관리)
- [x] 광고주 목록 테이블
- [x] 등록/수정/삭제 Modal 폼

#### SettingsPage.jsx (환경설정)
- [x] 파일 경로 6개 입력 폼 (apst_dir, ddr1_dir, cml_path, report_dir, logo_path, seal_path)
- [x] 관리자 비밀번호 변경 섹션 (현재 비밀번호 확인 후 변경)

---

## Phase 4-ext. 급지(SA/A/B/C) 분류 시스템 ✅ 완료

- [x] `server/parsers/utils.py` — `classify_grade(time_str)`: 시간 구간별 SA/A/B/C 분류
- [x] **버그 수정**: 대시보드/달력에서 총횟수 ≠ SA+A+B+C 합계 문제 발견 → 12:00~18:00을 C급에 포함시켜 해결 (서버 재시작 시 `_backfill_grade`가 기존 NULL 행 자동 재계산)
- [x] `server/database.py` — `grade` 컬럼 마이그레이션(`_ensure_column`) + 기존 데이터 backfill(`_backfill_grade`)
- [x] `apst_parser.py`, `ddr1_parser.py` — 레코드 생성 시 `grade` 필드 계산·포함
- [x] `routers/ingest.py`, `services/file_watcher.py` — INSERT문에 `grade` 컬럼 반영
- [x] `services/aggregator.py`
  - `get_item_counts()` — 급지별 SUM 추가 (대시보드용)
  - `get_daily_item_summary()` — 신규 (일일 운행표/일일 ID 운행표용)
  - `get_daily_counts()`, `get_broadcasts_by_date()` — `content_type_label` 필터 파라미터 추가, `grade` 컬럼 포함
- [x] `services/pdf_generator.py` — `generate_daily_summary_pdf()` 신규 (F-08/F-09 PDF)
- [x] `config.py` — `REPORT_SUMMARY_DIR` 추가

---

## Phase 5. 텔레그램 봇 [ ] 미시작

- [ ] BotFather에서 봇 생성 → 토큰 발급
- [ ] `server/bot/telegram_bot.py` 구현 (현재 스텁)
  - `/report 소재명 year month` → PDF 생성 → 파일 전송
  - `/count 소재명 year month` → 텍스트 응답
  - `/help` → 사용 방법 안내
- [ ] 봇 토큰: 환경설정에 `bot_token` 설정키 추가
- [ ] 접근 허용 사용자 범위 결정 (미확정)
- [ ] FastAPI startup 훅에서 봇 동시 실행

---

## Phase 6. 테스트 및 마무리 [~] 부분 완료

- [x] 파서 실제 데이터 검증 (APST 71건, DDR1 6건, CML 12,411건)
- [x] 전체 스캔 적재 검증 (241개 파일, 9,046건 적재)
- [x] API 응답 확인 (health, settings, login, period, items 등)
- [x] 폴더 감시 API 동작 확인
- [ ] 프론트엔드 화면 전체 동작 확인 (npm install 후)
- [ ] F-04 PDF 출력 품질 확인 (로고·직인 포함)
- [ ] F-06/F-07 PDF 출력 확인
- [ ] 텔레그램 봇 동작 확인 (Phase 5 이후)

---

## Phase 7. 2026-07 기능 추가·개선 ✅ 완료

### 7-1. 공익/재난 소재 분류 체계 재정비 (핵심)
- [x] `apst_parser.parse_apst` 저장 규칙 변경 (`_decide_store_type`)
  - PRM·R·F·E 등 + 이름에 공익/재난 → **공익재난**으로 저장
  - K(캠페인) + 공익/재난 → 기본은 캠페인 유지, 단 **'방송 종료 안내' 프로그램**이면 공익재난
  - 이어서(C)·광고그룹(G)·프로그램(AIR)·광고(SBC)는 저장 제외
  - 재난(R) 소재는 SrcID가 `K0000…` 형식이라 기존 N-필터에 걸려 누락되던 문제 해결(공익재난은 SrcID 제한 없이 저장)
- [x] 기존 apst.db 마이그레이션(`server/migrate_gongik_jaenan.py`): R 소재 589건 추가, 방송종료K 153건 재분류, PRM 공익재난 5,052건 duration 보정(0초→파일 Dur)
- [x] **월별·흘림자막 집계를 파일 파싱 → DB 조회로 전환** (`report._query_gongik_jaenan_db`)
  - apst.db(공익재난 + 캠페인K 공익/재난) + ddr1.db(수동송출 공익/재난) 통합 조회
  - 수동송출(DDR1) 공익/재난 소재가 이제 월별·흘림자막에 정상 합산됨
- [x] 방송운행표(F-06)는 파일 기반 유지하되 표시 규칙 정리(아래 7-4)

### 7-2. 공익/재난 분류 키워드 환경설정화
- [x] `config.py`/`settings.py` — `gongik_include_keywords`, `jaenan_include_keywords`, `gongik_jaenan_exclude_keywords` 3개 설정키 추가
- [x] 소재명에 포함 키워드가 있으면 공익/재난으로 포함, 제외 키워드가 있으면 집계에서 제외
- [x] 기본값 `학교폭력예방`(공익) 최초 설치 시 시딩(비워도 복구 안 함)
- [x] `SettingsPage.jsx` — '공익/재난 분류 키워드' 섹션 입력란 3개 추가
- [x] **근무자 모드 키워드 편집** — `WorkerKeywordPage.jsx` 신규(키워드 3개만 표시·저장), 근무자 메뉴 '공익/재난 키워드'(`/worker-keywords`) + 라우트 추가(`App.jsx`). 관리자 로그인 없이 근무자가 키워드만 수정 가능

### 7-3. FTP 파일 가져오기 (폴더 감시 대체)
- [x] `config.py` — `ftp_host/port/user/password/fetch_time` 설정키, `FTP_SUBDIRS`, `MISSING_MARK_START`
- [x] `services/ftp_fetcher.py` — 날짜별 다운로드·적재(`_download_date`/`fetch_and_ingest`), 매일 지정 시각 전날 파일 자동 수집 스케줄러
- [x] `routers/ftp.py` — `/ftp/test`, `/ftp/fetch`(날짜 지정), `/ftp/fetch-yesterday`
- [x] 달력: 누락일 붉은 0 표시(`daily_fetch` missing, MISSING_MARK_START 이후) + 클릭 재수집
- [x] **스케줄러 재시도 로직** — 예약 시각 실패(네트워크 오류 등) 시 2분 간격 최대 5회 재시도 (No route to host 등 일시 장애 대응)
- [x] **버그 수정** — 네트워크 오류 미수집일이 달력에 붉은색으로 표시되지 않던 문제 해결. `daily_fetch` 상태가 파일 없음은 `missing`, 네트워크 오류는 `error`로 갈리는데 `get_missing_dates`가 `missing`만 조회하던 것을 `status IN ('missing','error')`로 변경
- [x] **FTP ↔ 폴더 감시 상호 배타** — 예약 시각에 `watcher_enabled`(폴더 감시)가 ON이면 FTP 자동 가져오기를 건너뜀(둘 중 하나만 동작). 수동 가져오기 버튼은 영향 없음
- [x] **폴더 감시 모드 누락일 표시** — 감시 모드에서 예약 시각에 전날 파일 존재 여부를 점검(`refresh_fetch_status`)해 미완이면 `missing`으로 기록 → 달력 붉은색. 이후 감시기가 늦게 적재하면 `_ingest_apst`가 상태를 재평가해 자동 갱신
- [x] **감시 시작 시 기존 파일 초기 스캔** — `start_watching`이 `_initial_scan`(CML→APST→DDR1, 이미 처리된 건 건너뜀)을 백그라운드 실행 → 파일을 먼저 올리고 감시를 켜도 자동 적재·붉은색 해제
- [x] **폴더 감시 순서 의존성 버그 수정** — 감시는 파일별 개별 이벤트라 APST가 DDR1/CML보다 먼저 처리되면 수동송출이 누락되던 문제. 감시 3핸들러(`_ingest_apst/_ddr1/_cml`)가 공통 `_reconcile_date(date)`를 거쳐 앱과 동일한 `ingest_date()`(CML→APST→DDR1 순서 보장 + 중복검사)를 실행하도록 변경 → **파일 도착 순서 무관하게 수동송출 생성** + `refresh_fetch_status`로 붉은색 자동 해제. (기존 감시 전용 DDR1 로그 탐색이 `.log`를 못 찾던 문제도 `ingest_date` 경로가 `*.Log`/`*.log` 모두 검색해 우회)
- [x] **로그 노이즈 정리 (3건)**:
  - 수동송출 추출 중 DDR1 로그 미발견 `file_missing` 경고 제거(`_insert_manual_segments`) — 순서상 일시적이고 붉은색 3파일 점검이 이미 누락을 알림
  - 스케줄러의 "폴더 감시 모드 — FTP 자동 가져오기 건너뜀" 로그 미기록(조용히 전날 적재 점검만)
  - **폴더 감시 모드에서 `/ftp/fetch`·`/fetch-yesterday`는 FTP 대신 로컬 재적재**(`_reingest_local`) → FTP 미접근 환경(EC2)에서 붉은날짜 클릭 시 timeout 오류 로그가 남지 않고 로컬 파일로 붉은색 해제
- [x] **누락 판정 3파일 확대** — `refresh_fetch_status(date)` 신규: 로컬 폴더의 APST/DDR1/CML 존재 여부로 판정(모두 있으면 ok, 하나라도 없으면 missing + 없는 파일 종류 메시지). FTP·폴더감시·감시기 적재 후처리 공용 사용(기존 APST 단독 판정 대체)

### 7-4. 방송운행표(F-06) 표시·양식 개선
- [x] 소재종류 라벨 매핑 추가: P→프로그램, SBC→광고, IDC/F/E→기타, PRM+시보→시보
- [x] '방송 종료 안내' 프로그램은 소재종류와 무관하게 공익/재난 포함 시 공익재난으로 표시(수동송출 확장분 포함)
- [x] 소재제목에 독립 `ID` 토큰(`\bID\b`)이 있으면 con이 I가 아니어도 ID로 표시(방송개시/종료 방송국 ID 소재)
- [x] 화면 표를 저장본과 동일 스타일로: 프로그램 행 하늘색·광고/광고그룹 연두색 음영, 프로그램 경계/방송종료 시작 굵은 선, 헤더 상·하단 굵은 선
- [x] 첫부분 '방송순서 안내'는 프로그램이어도 음영 제외(화면·PDF·Word)
- [x] PDF 회색 교차 음영(zebra) 제거 → Word와 동일하게 무음영
- [x] 검색 결과 화면 페이지네이션 제거 → 전체 한 번에 표시(페이지당 개수 콤보 삭제)

### 7-5. 리포트/문서 양식 및 데이터 정확도
- [x] PDF/Word 표 폭·1페이지 맞춤, 긴 소재명 자동 줄바꿈(`_wrap_cell`)
- [x] 방송운행표(PDF/Word) 프로그램 구분 굵은 선·행 음영 스타일 도입
- [x] 수동송출 소재 길이 = 다음 소재까지의 실제 간격(마지막 소재는 APST 프로그램 시작 시각 기준), 전체 재추출
- [x] 미해결 수동 소재 보정: N+15초 → ID, CM 소재 → 광고
- [x] `extract_item_name` — 한글 결합형 길이 표기(예: 안유성1분7초) 정제 대응 + 기존 DB 일괄 재정제
- [x] 로그 기록 시각 KST로 수정(`datetime('now')` UTC 문제), 스케줄러 시작 로그 스팸 제거

### 7-6. 소재별 월 리포트 / 광고주 관리
- [x] 광고주 관리 메뉴 삭제 — 월 리포트는 송출매체·비고 기본값만 사용
- [x] 저장 시 '송출 내용' 입력 모달(기본값=검색 소재명), content 파라미터로 표시/파일명 반영

### 7-7. 접근 제한(허용 IP) 환경설정화
- [x] `allowed_ip_ranges` 설정키 — 대역/단일 IP 콤마·줄바꿈 구분, `0.0.0.0`=전체 허용, localhost 항상 허용
- [x] `main.py` — 요청마다 DB에서 허용 대역 동적 로드(저장 즉시 반영)

### 7-8. 엑셀(xlsx) 저장 통일
- [x] `routers/export.py` — 공용 `POST /api/export/xlsx`(openpyxl, 헤더 굵게·열너비 자동)
- [x] `client/src/xlsx.js` — 공용 `downloadXLSX` 헬퍼
- [x] 대시보드·달력·상세조회·소재목록의 CSV 저장을 모두 진짜 xlsx 저장으로 교체

### 7-9. 환경설정 화면 정리
- [x] 섹션 순서 변경: 공익/재난 키워드 → 월 리포트 표기 → 접근 제한 → FTP → 데이터 경로 → 이미지 → 근무자 로그인
- [x] 섹션 간 간격 확대 + 구분선
- [x] `report_dir`(PDF 저장 루트 경로) 설정 제거(미사용)

### 7-10. 배포 · 버전관리
- [x] `.gitignore` 추가 — venv/node_modules/db/*.db/data/reports 및 토큰 포함 스크립트 제외
- [x] `upload_to_github.sh` — 로컬(WSL)→GitHub 커밋·푸시(상단 변수에 토큰 입력, 푸시 후 원격 URL 토큰 제거). `.gitignore`로 미업로드
- [x] `setup_ec2.sh` — EC2(Amazon Linux) 초기 셋업: 패키지 설치 → 한글 폰트(NanumGothic) 설치 → clone/pull → venv+pip → npm build → 접근제한 IP 초기화(0.0.0.0)
- [x] **한글 폰트 자동 설치** — `setup_ec2.sh [1-b]`에서 NanumGothic(TrueType) TTF를 `~/.fonts`에 다운로드(멱등). reportlab이 CFF(Noto CJK)를 등록 못 해 PDF/Word에서 `KeyError: 'KoreanFont'` 500이 나던 문제를 신규 서버에서 원천 차단. `pdf_generator._register_fonts`는 후보 폰트를 우선순위대로 시도(TrueType 우선, 실패 폰트는 건너뜀)하도록 개선
- [x] `run_server.sh` — 수동 서버 실행/백그라운드(nohup+PID)/종료
- [x] `install_service.sh` — systemd 서비스(`sbdb`) 등록: 부팅 자동 시작 + 크래시 자동 복구, uninstall 지원
- [x] `update.sh` — 재배포: git pull → 백엔드 의존성 갱신 → 프론트 재빌드 → 서비스 재시작
- [x] `README.md` — 프로젝트 개요 + 로컬 개발 + EC2 배포(setup/service/run/update 스크립트) + GitHub 업로드 + 배포 확인사항 정리

---

## 현재 상태

**완료된 Phase**: 0, 1, 2, 3, 3-ext, 4, 4-ext(급지 분류), 7(2026-07 개선)
**진행 중**: Phase 6 테스트
**다음 작업**: Phase 5 텔레그램 봇 구현

> 참고: 광고주 관리 메뉴(Phase 4-3 AdvertiserPage), `report_dir` 설정, 폴더 실시간 감시(watchdog)는
> 2026-07 개편으로 각각 삭제/대체(FTP 가져오기)되었습니다. 위 Phase 4/3-ext 기록은 이력 보존용입니다.

### 다른 컴퓨터로 이전 시 체크리스트
1. `proj1/` 폴더 전체 복사 (`db/*.db` 포함하면 데이터 유지, 제외하면 빈 DB로 시작)
2. WSL Ubuntu에 Python 3.12 + pip 환경 구성, `pip install -r requirements.txt --break-system-packages`
3. Node.js 20 설치 후 `client/` 에서 `npm install`
4. 서버 최초 기동 시 `database.py`의 `init_db()`가 테이블·grade 컬럼·관리자 비밀번호 기본값을 자동 생성/마이그레이션
5. 환경설정 메뉴에서 `apst_dir`, `ddr1_dir`, `cml_path`, `logo_path`, `seal_path` 등 경로 재입력 필요 (DB가 새로 시작된 경우)
6. `.vscode/tasks.json`으로 `Ctrl+Shift+B` 실행 확인
