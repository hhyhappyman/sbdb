# APST 파일 포맷 스펙 (자동 송출 내역)

## 개요

- **파일 확장자**: `.apst`
- **파일명 예시**: `송출내역.apst`
- **저장 주기**: 매일 1개 파일 생성
- **인코딩**: UTF-8
- **형식**: JSON

---

## 최상위 구조

```json
{
  "lstGrp": [ <GroupObject>, ... ]
}
```

| 필드 | 타입 | 설명 |
|------|------|------|
| `lstGrp` | Array | 프로그램 블록(그룹) 목록 |

---

## GroupObject (프로그램 블록)

```json
{
  "_GrpName_": "MBC 뉴스투데이 1부",
  "lstPgm": [ <ProgramItem>, ... ],
  "EvtGrp": { "eID": "T21227G03", "eTy": "S", "eName": "MBC 뉴스투데이 1부", "On": "20260506 05:53:24", ... }
}
```

| 필드 | 타입 | 설명 |
|------|------|------|
| `_GrpName_` | String | 프로그램 블록 이름 (빈 문자열일 수 있음) |
| `lstPgm` | Array | 블록 내 송출 아이템 목록 |
| `EvtGrp` | Object | 그룹 메타 정보 — `eID`(그룹 식별자), `eTy`(`S`=SB 소재 그룹/`P`=프로그램 그룹), `eName`(그룹명), `On`(그룹 시작 시각, `YYYYMMDD HH:MM:SS`) |

### ✅ 그룹 쌍 구조 (수정)
- 하나의 SB 띠는 동일한 `EvtGrp.eID`를 가진 두 그룹이 연속으로 나타나 짝을 이룸
  - **그룹1** (`EvtGrp.eTy = "S"`): 이어서(`C`) → 광고그룹(`G`, 있을 때만) → 캠페인(`K`)* → ID(`I`) 순서의 SB 소재 목록. `EvtGrp.On`은 이 SB 띠가 시작되는 송출 시간
  - **그룹2** (`EvtGrp.eTy = "P"`, 그룹1과 동일 `eID`): 프로그램(`AIR`) 소재 1개. `EvtGrp.On`은 SB 띠가 끝나고 프로그램이 시작되는 시간, `EvtGrp.eName`이 이 SB 띠의 **정식 그룹명**
- DB 적재 시 그룹1에 속한 소재들의 `program_block`은 그룹1 자신의 `_GrpName_`이 아니라 **그룹2의 `EvtGrp.eName`**을 사용한다

---

## ProgramItem (송출 아이템)

```json
{
  "_PgmName_": "광고 아이템명",
  "m_lstPgmSub": [],
  "OnT": { ... },
  "Dur": { ... },
  "ClipLen": "00:00:00:00",
  "m_sPgmCaptionFlag": "P",
  "TT": 0,
  "DT": 0,
  "Un": false,
  "Hi": "",
  "DuMg": "",
  "GhostPgm": false,
  "GpioPgm": null,
  "IsHdr": false,
  "TM": "",
  "MM": "NET1",
  "BM": "NET2",
  "TrT": "M",
  "TrR": "M",
  "SrcID": "N278282",
  "SOM": "",
  "Snd": "S",
  "Lang": "S",
  "Sp": "U",
  "Con": "K",
  "ID": 2317
}
```

### 주요 필드 상세

#### OnT (방송 시작 시간)

```json
{
  "_bValid": true,
  "_dtOnairTimeSec": "2026-05-06T04:35:00",
  "_nFrame": 0,
  "_sTimePartSec": "04:35:00",
  "_sTimePartFF": "04:35:00:00",
  "_sOnairTimeSec": "20260506 04:35:00",
  "_sOnairTimeFF": "20260506 04:35:00:00"
}
```

| 필드 | 설명 |
|------|------|
| `_dtOnairTimeSec` | ISO 8601 형식의 방송 시작 일시 |
| `_sTimePartSec` | 시간 부분만 추출 (HH:MM:SS) |
| `_sOnairTimeSec` | 날짜+시간 문자열 (YYYYMMDD HH:MM:SS) |
| `_sOnairTimeFF` | 날짜+시간+프레임 (YYYYMMDD HH:MM:SS:FF) |

#### Dur (재생 길이)

```json
{
  "_bNegativeVal": false,
  "_nDurSec": 30,
  "_nFrame": 0,
  "_sDurSec": "00:00:30",
  "_sDurFF": "00:00:30:00"
}
```

| 필드 | 설명 |
|------|------|
| `_nDurSec` | 재생 길이 (초, 정수) |
| `_sDurSec` | 재생 길이 문자열 (HH:MM:SS) |

### 식별 필드 상세

| 필드 | 타입 | 값 | 설명 |
|------|------|-----|------|
| `SrcID` | String | `N######` | **SB 아이템 클립 ID** (N+숫자 6자리) |
| `SrcID` | String | `BLACK`, `AUDIOTEST`, `GRAY-TONE` 등 | 시스템 클립 |
| `SrcID` | String | `//XXXX-XXXXX` | 기타 클립 |
| `Con` | String | `K` | **캠페인** — DB 저장 대상 (예시 파일 71개) |
| `Con` | String | `I` | **ID** — DB 저장 대상 (예시 파일 20개) ✅ 수정 (과거 `IDC`로 잘못 알고 있었음) |
| `Con` | String | `C` | 이어서 — 저장 안 함 (예시 파일 22개) |
| `Con` | String | `G` | 광고그룹 — 저장 안 함 (예시 파일 9개) |
| `Con` | String | `AIR` | 프로그램 — 저장 안 함 (예시 파일 26개) |
| `Con` | String | `PRM`, `R`, `F`, `E`, `IDC`, `P`, `SBC` 등 | 기타 — 기본 저장 안 함. 단 **이름에 '공익'/'재난'이 있으면 `공익재난`으로 저장** (2026-07, 아래 참조) |
| `TT` | Int | `1` | SB 블록 헤더 |
| `TT` | Int | `0` | 일반 아이템 |
| `DT` | Int | `0` | 일반 |
| `DT` | Int | `2` | 기타 (8개) |
| `m_sPgmCaptionFlag` | String | `P` | 일반 프로그램 아이템 (136개) |
| `m_sPgmCaptionFlag` | String | `R` | 헤더/구분 아이템 (38개) |

### 기타 필드

| 필드 | 설명 |
|------|------|
| `_PgmName_` | 아이템 표시명 |
| `MM` | 주장비명 (예: `DDR4`) — ✅ `main_equipment` 컬럼으로 DB 저장 |
| `BM` | 백업 모니터 출력 (예: `NET2`) |
| `TrT` | 트랜지션 타입 (예: `M`) |
| `TrR` | 트랜지션 리졸브 (예: `M`) |
| `Snd` | 사운드 설정 |
| `Lang` | 언어 |
| `Sp` | 스페셜 설정 |
| `ID` | 내부 아이템 일련번호 (정수) |

---

## SB 아이템 판별 기준 ✅ 수정 (2026-07 공익재난 규칙 반영)

APST 파일에서 DB에 저장하는 소재종류(`content_type_label`)는 `_decide_store_type(con, 이름에_공익재난_여부, 방송종료안내_여부)`로 결정한다:

```
con = I                        → ID
con ∈ {C, G, AIR, SBC}         → 저장 안 함 (이어서/광고그룹/프로그램/광고)
con = K                        → 이름에 공익/재난 + 프로그램='방송 종료 안내' 이면 공익재난, 아니면 캠페인
그 외(PRM, R, F, E, IDC, P …)  → 이름에 공익/재난 있으면 공익재난, 없으면 저장 안 함
```

- **SrcID 필터**: 캠페인/ID는 기존대로 `N######` 형식만 저장. **공익재난은 SrcID 제한 없음** — 재난(`R`) 소재는 SrcID가 `K0000…` 형식이라 N-필터에 걸려 과거에 누락되던 것을 해결.
- `SrcID`의 N-ID는 CML 매핑 파일의 N-ID와 연결됨.
- 같은 SB 띠 안의 `C`/`G`/`AIR` 아이템은 저장하지 않지만, `program_block`(그룹명) 결정에는 짝이 되는 `AIR` 그룹의 `EvtGrp.eName`이 사용됨 (위 "그룹 쌍 구조" 참조).
- 공익재난 소재명은 `clean_prm_campaign_name()`으로 정제(`[※]`, `(30초)`, `(공익)/(재난)` 접두 정리 등).

### 방송 운행표(리포트) 표시용 라벨 (`parse_apst_all` / `_resolve_content_type_label`)
DB 저장과 별개로, 방송 운행표 화면·PDF·Word 표시용 라벨 매핑:

```
P/AIR → 프로그램,  SBC → 광고,  G → 광고그룹,  IDC/F/E → 기타,  PRM+'시보' → 시보
```
표시 단계 추가 규칙: 소재제목에 독립 `ID` 토큰(`\bID\b`)이 있으면 ID로 표기(방송개시/종료 방송국 ID),
'방송 종료 안내' 프로그램은 소재종류와 무관하게 공익/재난 포함 시 공익재난으로 표기.

---

## 날짜 추출

파일명에 날짜가 없는 경우, 아이템의 `OnT._dtOnairTimeSec` 필드에서 날짜 추출:

```python
from datetime import datetime
dt = datetime.fromisoformat(item["OnT"]["_dtOnairTimeSec"])
date = dt.date()
hour = dt.hour
```

---

## DB 적재 시 추출 필드

| DB 컬럼 | 원본 필드 | 비고 |
|---------|-----------|------|
| `broadcast_date` | `OnT._dtOnairTimeSec` (날짜 부분) | |
| `broadcast_time` | `OnT._sTimePartSec` | HH:MM:SS |
| `broadcast_hour` | `OnT._dtOnairTimeSec` (시간 부분) | 시간대별 집계용 |
| `clip_id` | `SrcID` | N-ID |
| `item_name` | `_PgmName_` | |
| `duration_sec` | `Dur._nDurSec` | |
| `program_block` | 짝이 되는 `AIR` 그룹(`EvtGrp.eTy="P"`)의 `EvtGrp.eName` | ✅ 수정 — 자기 그룹의 `_GrpName_`이 아님 |
| `content_type` | `Con` | 원본 con 코드 (K/I/PRM/R/…) |
| `content_type_label` | `_decide_store_type()` | 캠페인/ID/공익재난 — 저장·집계용 소재종류 |
| `grade` | `classify_grade(time)` | SA/A/B/C 급지 |
| `main_equipment` | `MM` | ✅ 신규 — 주장비명 원본 그대로 저장 |
| `internal_id` | `ID` | |
| `source` | `"apst"` | 고정값 |
