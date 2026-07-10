"""
DDR1 log file parser.
Extracts 'Play CLIP : N######' events and classifies each clip as
'캠페인' or 'ID' by:
  1. Checking if the clip name contains 'ID' → ID
  2. Matching against campaign names from the APST DB → 캠페인
  3. Otherwise → skip (이이서 etc.)

수동 송출(주장비명=DDR1) 구간 추출:
  APST의 이어서(Con=C) 소재가 MM(주장비명)=DDR1이면 해당 SB 띠는 수동으로
  송출된 것이다. 이 구간에서 실제로 송출된 소재는 DDR1 로그에서:
    - 띠 시작: "Play CLIP : <이어서 clip_id>" (시간 동기화 오차 고려, ±5초 허용)
    - 두 번째 소재부터: 명시적인 "Play CLIP" 라인은 없지만, 실제 전환 시점은
      "O : Play Clip Change Tc : ..." 라인의 타임스탬프다. 이 라인에는 clip_id가
      직접 적혀있지 않으므로, 그 직전에 나온 "O : Load ID : <clip_id>" 또는
      "O : 3Sec Re Load ID : <clip_id>"(다음 소재를 미리 큐에 넣는 이벤트)에서
      clip_id를 가져온다.
      ※ "O : OnAir ID : <clip_id>" 라인은 그 소재가 거의 다 재생된 뒤(보통
      재생 종료 16~20초 전)에야 찍히는 상태 확인 라인이라 실제 시작 시간보다
      훨씬 늦다 — 절대 시작 시간으로 쓰면 안 됨 (과거 버그: 이 라인 시간을
      써서 송출 시작 시간이 실제보다 늦게 기록되고, 구간 종료 경계 근처의
      소재가 누락되는 문제가 있었음).
    - 마지막 소재는 다음 "Play Clip Change"가 없을 수 있음(중간에 정지되는
      경우 등) — 이미 전환이 확인된 마지막 소재까지만 인정한다.
  띠 종료 시간은 짝이 되는 프로그램(AIR) 그룹의 시작 시간(EvtGrp.On)이다.
"""

import re
from datetime import date as _date, timedelta
from pathlib import Path

from parsers.utils import extract_item_name, classify_grade


# ── Regex ──────────────────────────────────────────────────────────────────

# Matches: "HH:MM:SS.mmm : [DDR1] I : Play CLIP : N######"  (SB 띠 시작 트리거)
_PLAY_CLIP_RE = re.compile(
    r"^(\d{2}:\d{2}:\d{2})\.\d{3} : \[DDR1\] I : Play CLIP : (N\d+)$"
)

# Matches: "HH:MM:SS.mmm : [DDR1] O : Load ID : <clip_id>, ..." 또는
#          "HH:MM:SS.mmm : [DDR1] O : 3Sec Re Load ID : <clip_id>, ..."
# 다음에 재생될 소재를 미리 큐에 넣는 이벤트 — clip_id만 기억해두고, 실제 전환
# 시간은 바로 뒤에 오는 "Play Clip Change" 라인에서 가져온다.
_LOAD_RE = re.compile(
    r"^(\d{2}:\d{2}:\d{2})\.\d{3} : \[DDR1\] O : (?:3Sec Re )?Load ID : (\S+?),"
)

# Load ID 라인의 재생 길이(Dur HH:MM:SS:FF) — 소재종류 추정(N 15초=ID)에 사용
_DUR_RE = re.compile(r"Dur (\d{2}):(\d{2}):(\d{2}):")

# Matches: "HH:MM:SS.mmm : [DDR1] O : Play Clip Change Tc : ..."
# 직전에 큐에 들어간 소재로 실제 전환된 시점 (= 그 소재의 진짜 송출 시작 시간)
_PLAY_CHANGE_RE = re.compile(
    r"^(\d{2}:\d{2}:\d{2})\.\d{3} : \[DDR1\] O : Play Clip Change"
)


def _time_to_sec(time_str: str) -> int:
    h, m, s = (int(x) for x in time_str.split(":"))
    return h * 3600 + m * 60 + s


# ── Classifier ─────────────────────────────────────────────────────────────

def classify_ddr1_clip(
    clip_id: str,
    cml_map: dict,
    campaign_names: set,
) -> tuple[str | None, str, str]:
    """
    Determine the content type of a DDR1 clip.

    Args:
        clip_id:        N-format clip ID (e.g. 'N270944')
        cml_map:        {clip_id: {full_name, duration_sec, ...}} from CML parser
        campaign_names: set of clean campaign names from APST DB

    Returns:
        (content_type_label, item_name_raw, item_name)
        content_type_label is None if the clip should NOT be stored.
    """
    entry = cml_map.get(clip_id)
    if not entry:
        return None, "", ""

    full_name: str = entry["full_name"]
    clean_name: str = extract_item_name(full_name)

    # Step 1: name contains 'ID' → ID type
    if "ID" in full_name:
        return "ID", full_name, clean_name

    # Step 2: matches a known campaign name → 캠페인
    if clean_name in campaign_names:
        return "캠페인", full_name, clean_name

    # Step 3: 이이서 or unknown → skip
    return None, full_name, clean_name


def _guess_label_by_clip(clip_id: str, duration_sec: int) -> tuple[str, int]:
    """
    CML·자동송출 DB 어디에서도 소재명을 못 찾은 clip에 대해 clip_id/재생길이로
    소재종류를 추정한다 (소재명은 clip_id 그대로 유지).
      - clip_id가 'CM'으로 시작 → '광고' (지역 광고)
      - clip_id가 'N'으로 시작하고 재생길이 15초 → 'ID'
      - 그 외 → '캠페인'
    반환: (content_type_label, duration_sec)
    """
    if clip_id.startswith("CM"):
        return "광고", duration_sec
    if clip_id.startswith("N") and duration_sec == 15:
        return "ID", 15
    return "캠페인", duration_sec


# ── 수동 송출(DDR1) 구간 추출 ─────────────────────────────────────────────────

def _load_ddr1_events(file_path: str) -> tuple[list[tuple[int, int, str, str]], list[tuple[int, int, str, str]]]:
    """
    DDR1 로그 파일을 한 번 읽어 Play CLIP 트리거 / 실제 전환(Play Clip Change) 이벤트
    목록을 반환한다. 각 이벤트는 (라인번호, 초단위 시간, 시간문자열 HH:MM:SS, clip_id) 튜플.

    전환 이벤트의 clip_id는 그 직전에 나온 "Load ID"/"3Sec Re Load ID" 라인에서 가져온다
    ("Play Clip Change" 라인 자체에는 clip_id가 없음).
    """
    play_events: list[tuple[int, int, str, str]] = []
    change_events: list[tuple[int, int, str, str, int]] = []
    pending_clip_id: str | None = None
    pending_dur: int = 0

    with open(file_path, "r", encoding="utf-8", errors="replace") as f:
        for line_no, line in enumerate(f):
            line = line.strip()

            m = _PLAY_CLIP_RE.match(line)
            if m:
                time_str = m.group(1)
                play_events.append((line_no, _time_to_sec(time_str), time_str, m.group(2)))
                continue

            m = _LOAD_RE.match(line)
            if m:
                pending_clip_id = m.group(2)
                dm = _DUR_RE.search(line)
                pending_dur = (
                    int(dm.group(1)) * 3600 + int(dm.group(2)) * 60 + int(dm.group(3))
                ) if dm else 0
                continue

            m = _PLAY_CHANGE_RE.match(line)
            if m and pending_clip_id:
                time_str = m.group(1)
                change_events.append(
                    (line_no, _time_to_sec(time_str), time_str, pending_clip_id, pending_dur)
                )

    return play_events, change_events


def extract_manual_clips(
    file_path: str,
    trigger_clip_id: str,
    start_time: str,
    end_time: str,
    tolerance_sec: int = 5,
) -> list[tuple[str, str, int]]:
    """
    수동(DDR1) 송출 구간에서 실제로 송출된 소재를 시간 순서대로 추출.

    구간 시작점(트리거)은 오직 시작 시간(±tolerance_sec)만으로 찾는다.
    APST 이어서 소재의 clip_id는 DDR1 로그의 실제 Play CLIP id와 다를 수 있어
    (편성표상의 이어서 번호와 실제 송출 클립 번호가 불일치) 매칭 기준으로 쓰지 않는다.
    trigger_clip_id 인자는 하위 호환을 위해 남겨두지만 사용하지 않는다.

    Args:
        file_path:        DDR1 .Log 파일 경로
        trigger_clip_id:  (미사용) 하위 호환용. 시작점은 시간 기준으로만 찾는다.
        start_time:       SB 띠 시작 시간 'HH:MM:SS' (APST 이어서 소재의 OnT 시간)
        end_time:         SB 띠 종료 시간 'HH:MM:SS' (짝이 되는 프로그램 그룹 시작 시간)
        tolerance_sec:    시작 시간 동기화 오차 허용 범위(초). 기본 5초.

    Returns:
        [(time_str, clip_id, duration_sec), ...] 순서대로. 트리거를 못 찾으면 빈 리스트.
        시간은 각 소재가 실제로 전환된 시점("Play Clip Change" 타임스탬프)이고,
        duration_sec는 실제 송출 길이 = "다음 소재 전환 시각 − 이 소재 전환 시각"이다.
        마지막 소재는 구간 종료 시각(end_time)까지로 계산한다.
        (수동 송출은 운영자가 소재를 넘기므로 클립 공칭 길이가 아니라 실제 점유 시간이
         송출 길이이다. 간격을 못 구하면 Load ID의 Dur를 대체로 사용.)
    """
    play_events, change_events = _load_ddr1_events(file_path)

    start_sec = _time_to_sec(start_time)
    end_sec = _time_to_sec(end_time)
    if end_sec < start_sec:
        end_sec += 86400   # 자정 경계를 넘는 SB 띠

    # 시작 시간(±tolerance_sec)에 가장 가까운 Play CLIP을 구간 시작점으로 사용
    # (clip_id 일치 여부는 따지지 않음)
    candidates = [
        e for e in play_events
        if abs(e[1] - start_sec) <= tolerance_sec
    ]
    if not candidates:
        return []
    trigger_line_no = min(candidates, key=lambda e: abs(e[1] - start_sec))[0]

    # 구간 내 전환 이벤트를 순서대로 수집 (time_str, clip_id, 공칭Dur, 초단위 시각)
    collected: list[tuple[str, str, int, int]] = []
    for line_no, sec, time_str, clip_id, dur_sec in change_events:
        if line_no <= trigger_line_no:
            continue
        adj_sec = sec if sec >= start_sec else sec + 86400
        if adj_sec > end_sec:
            break
        collected.append((time_str, clip_id, dur_sec, adj_sec))

    # 실제 송출 길이 = 다음 소재 전환 시각 − 이 소재 전환 시각
    results: list[tuple[str, str, int]] = []
    for i, (time_str, clip_id, nominal_dur, adj_sec) in enumerate(collected):
        next_sec = collected[i + 1][3] if i + 1 < len(collected) else end_sec
        gap = next_sec - adj_sec
        # 간격이 비정상(0 이하)이면 공칭 Dur로 대체
        actual = gap if gap > 0 else (nominal_dur or 0)
        results.append((time_str, clip_id, actual))

    return results


def extract_manual_segment_records(
    segments: list[dict],
    log_files_by_date: dict[str, str],
    cml_map_by_date: dict[str, dict],
    campaign_names: set,
    apst_map_by_date: dict[str, dict] | None = None,
    apst_lookup=None,
) -> list[dict]:
    """
    APST에서 찾은 수동 송출 구간(segments)들에 대해 해당 날짜의 DDR1 로그를 열어
    실제 송출된 소재를 추출하고, ddr1.db broadcasts 테이블에 적재할 레코드를 만든다.

    Args:
        segments: apst_parser.find_manual_segments()의 결과
                  [{"broadcast_date", "start_time", "end_time", "trigger_clip_id", ...}, ...]
        log_files_by_date: {"YYYY-MM-DD": "/path/to/log"} — 날짜별 DDR1 로그 파일 경로
        cml_map_by_date: {"YYYY-MM-DD": parse_cml() 결과} — 날짜별 CML 매핑 (imc<YYYYMMDD>.cml)
        campaign_names:  get_campaign_names() 결과
        apst_map_by_date: {"YYYY-MM-DD": {clip_id: {item_name_raw, item_name,
                          content_type_label, duration_sec}}} — 해당 날짜 자동송출(apst.db) 소재.
                          CML에 없는 clip_id의 소재명을 여기서 보완한다.

    각 레코드의 source_file은 "manual:<로그파일명>:<트리거clip_id>" 형식으로 지정해,
    일반 DDR1 로그 적재(source_file=로그파일명 그대로)와 중복 검사 범위가 겹치지 않게 한다.

    소재명 결정 순서:
      1) CML(cml_map)에 clip_id가 있으면 CML 이름 사용
      2) 없으면 같은 날짜 자동송출 DB(apst_map)에서 clip_id로 조회
      3) 그래도 없으면 소재명 대신 clip_id를 그대로 기록 (content_type_label='캠페인')
    """
    apst_map_by_date = apst_map_by_date or {}
    records: list[dict] = []
    seen: set = set()

    for seg in segments:
        log_path = log_files_by_date.get(seg["broadcast_date"])
        if not log_path:
            continue

        cml_map = cml_map_by_date.get(seg["broadcast_date"], {})
        apst_map = apst_map_by_date.get(seg["broadcast_date"], {})
        # 어제 날짜 CML (당일 CML·자동송출 DB에 없을 때 마지막 보완)
        try:
            _prev = (_date.fromisoformat(seg["broadcast_date"]) - timedelta(days=1)).isoformat()
        except ValueError:
            _prev = None
        cml_map_prev = cml_map_by_date.get(_prev, {}) if _prev else {}

        clips = extract_manual_clips(
            log_path,
            trigger_clip_id=seg["trigger_clip_id"],
            start_time=seg["start_time"],
            end_time=seg["end_time"],
        )
        if not clips:
            continue

        source_file = f"manual:{Path(log_path).name}:{seg['trigger_clip_id']}"

        for time_str, clip_id, clip_dur in clips:
            key = f"{source_file}|{time_str}|{clip_id}"
            if key in seen:
                continue
            seen.add(key)

            # 소재명/소재종류는 CML·자동송출 DB에서 결정하고,
            # 송출 길이는 실제 송출 간격(clip_dur = 다음 소재까지)을 사용한다.
            # (공칭 길이 nominal은 clip_dur가 0일 때만 대체로 사용)
            nominal: int = 0
            if clip_id in cml_map:
                label, raw_name, clean_name = classify_ddr1_clip(clip_id, cml_map, campaign_names)
                if label is None:
                    continue
                nominal = cml_map.get(clip_id, {}).get("duration_sec", 0) or 0
            elif clip_id in apst_map:
                # 당일 CML에 없으면 같은 날짜 자동송출 DB에서 소재명 보완
                entry = apst_map[clip_id]
                raw_name = entry.get("item_name_raw") or clip_id
                clean_name = entry.get("item_name") or clip_id
                label = entry.get("content_type_label") or "캠페인"
                nominal = entry.get("duration_sec", 0) or 0
            elif clip_id in cml_map_prev:
                # 어제 날짜 CML에서 보완 (00~04시 심야분은 전날 편성)
                label, raw_name, clean_name = classify_ddr1_clip(clip_id, cml_map_prev, campaign_names)
                if label is None:
                    continue
                nominal = cml_map_prev.get(clip_id, {}).get("duration_sec", 0) or 0
            else:
                # 날짜 무관 자동송출 DB — 기준일 이전 가장 가까운 날짜 소재명으로 보완
                entry = apst_lookup(clip_id, seg["broadcast_date"]) if apst_lookup else None
                if entry:
                    raw_name = entry.get("item_name_raw") or clip_id
                    clean_name = entry.get("item_name") or clip_id
                    label = entry.get("content_type_label") or "캠페인"
                    nominal = entry.get("duration_sec", 0) or 0
                else:
                    # 소재명 미확인 → clip_id를 그대로 기록하되, ID 규칙으로 소재종류 추정
                    raw_name, clean_name = clip_id, clip_id
                    label, nominal = _guess_label_by_clip(clip_id, clip_dur)

            duration_sec: int = clip_dur or nominal

            records.append({
                "broadcast_date":     seg["broadcast_date"],
                "broadcast_time":     time_str,
                "broadcast_hour":     _time_to_sec(time_str) // 3600 % 24,
                "clip_id":            clip_id,
                "item_name_raw":      raw_name,
                "item_name":          clean_name,
                "content_type_label": label,
                "grade":              classify_grade(time_str),
                "duration_sec":       duration_sec,
                "source_file":        source_file,
            })

    return records


# ── Main parser ────────────────────────────────────────────────────────────

def parse_ddr1(
    file_path: str,
    broadcast_date: str,
    cml_map: dict,
    campaign_names: set,
    source_file: str | None = None,
    exclude_windows: list[tuple[str, str]] | None = None,
) -> list[dict]:
    """
    ✅ Deprecated — 항상 빈 리스트를 반환한다.

    원래는 로그 전체에서 독립적인 'Play CLIP : N######' 라인을 찾아 캠페인/ID로
    분류해 저장했으나, 실데이터 검증 결과 이 방식은 신뢰할 수 없는 것으로 확인됨:
      1. 운영자가 화면에서 단발성으로 미리보기/테스트 재생한 클립도 똑같이
         'Play CLIP' 라인을 남겨, 실제 송출이 아닌데도 진짜 송출로 기록되는
         오탐(false positive)이 발생함 (예: 518재단 단발 재생, 우리아이치과(틀니)
         단발 클릭 — 둘 다 연속된 다음 소재로 이어지지 않는 단발성 재생이었음).
      2. 단발성 여부를 "다음 소재로 이어지는지(연속성)"로 검증해도, DDR1 장비가
         (MM=DDR1로 표시되지 않은) 정상 자동 송출 SB 띠까지 함께 기록하고 있어,
         결과적으로 apst.db에 이미 저장된 자동 송출 내역과 거의 동일한 시각의
         중복 데이터가 다시 ddr1.db에 적재되는 문제가 있음.

    수동 송출(주장비명=DDR1) 여부를 신뢰성 있게 판별할 수 있는 유일한 기준은
    APST에서 명시적으로 `MM=DDR1`로 표시된 이어서 소재뿐이다. 따라서 모든 수동
    송출 내역은 `apst_parser.find_manual_segments()` + `extract_manual_clips()`/
    `extract_manual_segment_records()`를 통해서만 추출한다 (APST 적재 직후
    자동으로 연결됨 — routers/ingest.py, services/file_watcher.py 참조).

    이 함수와 DDR1 업로드/스캔 API는 하위 호환을 위해 남겨두지만 더 이상
    broadcasts 레코드를 생성하지 않는다.
    """
    return []
