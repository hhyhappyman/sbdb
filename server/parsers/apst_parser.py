"""
APST file parser (JSON format, daily broadcast schedule).

하나의 SB 띠(band)는 lstGrp 안에서 한 쌍의 그룹으로 표현된다:
  - 그룹1 (EvtGrp.eTy == "S"): 실제 SB 소재 목록(lstPgm) — 이어서(C) → 광고그룹(G, 있을 때만)
    → 캠페인(K)* → ID(I) 순서로 들어있음
  - 그룹2 (EvtGrp.eTy == "P", 그룹1과 동일 EvtGrp.eID): 프로그램(AIR) 소재 1개
    그룹2의 EvtGrp.eName이 해당 SB 띠의 정식 그룹명이며, 그룹1에 속한 소재들의
    program_block 값으로 사용한다.

Con 코드:
  C   = 이어서      (저장 안 함)
  G   = 광고그룹    (저장 안 함)
  K   = 캠페인      (저장)
  I   = ID          (저장)
  AIR = 프로그램    (저장 안 함)

Only '캠페인' (Con=K) and 'ID' (Con=I) items are stored.
"""

import json
from pathlib import Path

from parsers.utils import extract_item_name, classify_grade, clean_prm_campaign_name


def _parse_onair_time(on_t: dict) -> tuple[str, str, int] | None:
    """
    OnT 객체에서 (broadcast_date, time_str, broadcast_hour)를 반환.
    _sOnairTimeSec = "YYYYMMDD HH:MM:SS" 형식에서 날짜+시간을 추출.
    파싱 불가 시 None 반환.
    """
    s = on_t.get("_sOnairTimeSec", "")
    # Expected: "20260502 01:04:20"
    if not s or len(s) < 17:
        return None
    try:
        broadcast_date = f"{s[0:4]}-{s[4:6]}-{s[6:8]}"
        time_str = s[9:17]          # "HH:MM:SS"
        broadcast_hour = int(s[9:11])
        return broadcast_date, time_str, broadcast_hour
    except (ValueError, IndexError):
        return None


# ── Con code → content_type_label mapping (표시/리포트용) ──────────────────

_CON_LABEL: dict[str, str] = {
    "C":   "이어서",
    "G":   "광고그룹",
    "K":   "캠페인",
    "I":   "ID",
    "AIR": "프로그램",
    "P":   "프로그램",
    "SBC": "광고",
    "IDC": "기타",
    "F":   "기타",
    "E":   "기타",
}


def _resolve_content_type_label(con: str, raw_name: str) -> str:
    """
    con 코드 → 방송 운행표 표시용 소재종류 라벨.
    PRM 소재는 원래 '공익'/'재난' 판별과 별개로, 소재제목에 '시보'가 있으면 '시보'로 표시한다.
    """
    if con == "PRM" and "시보" in raw_name:
        return "시보"
    return _CON_LABEL.get(con, con)


def _get_store_type(con: str) -> str | None:
    """
    Determine whether this item should be stored and return its label.
    Returns None if the item must be skipped (이어서/광고그룹/프로그램 등).
    """
    if con == "K":
        return "캠페인"
    if con == "I":
        return "ID"
    return None


# 저장 제외 대상 con: 이어서(C)·광고그룹(G)·프로그램(AIR)·광고(SBC)
_NON_STORE_CON = {"C", "G", "AIR", "SBC"}


def _decide_store_type(con: str, has_gj: bool, is_end_notice: bool) -> tuple[str | None, bool]:
    """
    소재종류(content_type_label) 결정. 반환: (label, is_gongik_jaenan)
      - I → ID
      - C/G/AIR/SBC → 저장 안 함
      - K → 기본 캠페인. 단, '방송 종료 안내' 프로그램 + 공익/재난 이름 → 공익재난
      - 그 외(PRM·R·F·E 등) → 이름에 공익/재난 있으면 공익재난, 없으면 저장 안 함
    """
    if con == "I":
        return "ID", False
    if con in _NON_STORE_CON:
        return None, False
    if con == "K":
        if has_gj and is_end_notice:
            return "공익재난", True
        return "캠페인", False
    # 기타 con (PRM, R, F, E, E01, IDC, P ...)
    if has_gj:
        return "공익재난", True
    return None, False


def _resolve_group_name(groups: list[dict], i: int) -> str:
    """
    그룹 i가 속한 SB 띠의 정식 그룹명을 반환.
    그룹 i가 EvtGrp.eTy == "S"이고 바로 다음 그룹(i+1)이 같은 eID로 짝을 이루는
    EvtGrp.eTy == "P" 그룹이면, 그 짝 그룹의 EvtGrp.eName을 사용한다.
    짝을 찾지 못하면 그룹 자신의 _GrpName_/eName으로 대체한다.
    """
    grp = groups[i]
    evt = grp.get("EvtGrp", {})
    fallback = evt.get("eName") or grp.get("_GrpName_", "")

    if evt.get("eTy") == "S" and i + 1 < len(groups):
        next_evt = groups[i + 1].get("EvtGrp", {})
        if next_evt.get("eID") == evt.get("eID"):
            return next_evt.get("eName", "") or fallback

    return fallback


# ── Main parser ────────────────────────────────────────────────────────────

def parse_apst(file_path: str, source_file: str | None = None) -> list[dict]:
    """
    Parse an APST JSON file and return a list of broadcast records
    for '캠페인' and 'ID' items only.

    Each record dict matches the apst.db broadcasts table columns.
    """
    path = Path(file_path)
    if source_file is None:
        source_file = path.name

    with open(file_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    groups: list[dict] = data.get("lstGrp", [])
    records: list[dict] = []

    for i, grp in enumerate(groups):
        program_block: str = _resolve_group_name(groups, i)

        is_end_notice = "방송 종료" in program_block or "방송종료" in program_block

        for item in grp.get("lstPgm", []):
            src_id: str = item.get("SrcID", "")
            con: str = item.get("Con", "")
            raw_name: str = item.get("_PgmName_", "")
            has_gj = ("공익" in raw_name) or ("재난" in raw_name)

            store_type, is_prm_campaign = _decide_store_type(con, has_gj, is_end_notice)
            if store_type is None:
                continue

            # 캠페인/ID는 기존대로 N-형식 SrcID만 처리.
            # 공익재난은 SrcID 제한 없음 (재난 소재는 SrcID가 K0000… 형식이라 N필터에 걸림)
            if store_type in ("캠페인", "ID") and not src_id.startswith("N"):
                continue

            # ── Parse on-air time ──
            on_t = item.get("OnT", {})
            parsed = _parse_onair_time(on_t)
            if parsed is None:
                continue
            broadcast_date, time_str, broadcast_hour = parsed

            # ── Parse duration ──
            dur = item.get("Dur", {})
            duration_sec: int = dur.get("_nDurSec", 0) or 0

            # PRM 공익/재난은 소재명 정제 적용
            base_name = extract_item_name(raw_name)
            item_name = clean_prm_campaign_name(base_name) if is_prm_campaign else base_name

            records.append({
                "broadcast_date":     broadcast_date,
                "broadcast_time":     time_str,
                "broadcast_hour":     broadcast_hour,
                "clip_id":            src_id,
                "item_name_raw":      raw_name,
                "item_name":          item_name,
                "duration_sec":       duration_sec,
                "program_block":      program_block,
                "content_type":       con,
                "content_type_label": store_type,
                "grade":              classify_grade(time_str),
                "main_equipment":     item.get("MM", ""),
                "internal_id":        item.get("ID"),
                "source_file":        source_file,
            })

    return records


def find_manual_segments(file_path: str) -> list[dict]:
    """
    APST 파일에서 주장비명(MM)이 'DDR1'인 이어서(Con=C) 소재를 찾아,
    해당 SB 띠가 수동으로 송출되었음을 나타내는 구간 정보를 반환한다.

    각 구간의 시작 시간은 이어서 소재의 OnT 시간, 종료 시간은 짝이 되는
    프로그램(AIR) 그룹의 EvtGrp.On 시간이다 (없으면 다음 그룹의 첫 소재 시간으로 대체).

    Returns:
        [{"broadcast_date": "YYYY-MM-DD", "start_time": "HH:MM:SS",
          "end_time": "HH:MM:SS", "trigger_clip_id": "N######",
          "program_block": "..."}, ...]
    """
    with open(file_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    groups: list[dict] = data.get("lstGrp", [])
    segments: list[dict] = []

    for i, grp in enumerate(groups):
        for item in grp.get("lstPgm", []):
            if item.get("Con") != "C" or item.get("MM") != "DDR1":
                continue

            on_t = item.get("OnT", {})
            parsed = _parse_onair_time(on_t)
            if parsed is None:
                continue
            broadcast_date, start_time, _ = parsed

            # 종료 시간: 짝이 되는 프로그램(AIR) 그룹의 EvtGrp.On
            end_time = start_time
            evt = grp.get("EvtGrp", {})
            matched = False
            if evt.get("eTy") == "S" and i + 1 < len(groups):
                next_evt = groups[i + 1].get("EvtGrp", {})
                if next_evt.get("eID") == evt.get("eID"):
                    parts = next_evt.get("On", "").split(" ")
                    if len(parts) == 2:
                        end_time = parts[1]
                        matched = True
            if not matched and i + 1 < len(groups):
                next_items = groups[i + 1].get("lstPgm", [])
                if next_items:
                    nt = next_items[0].get("OnT", {}).get("_sTimePartSec", "")
                    if nt:
                        end_time = nt

            segments.append({
                "broadcast_date":  broadcast_date,
                "start_time":      start_time,
                "end_time":        end_time,
                "trigger_clip_id": item.get("SrcID", ""),
                "program_block":   _resolve_group_name(groups, i),
            })

    return segments


def parse_apst_all(file_path: str, source_file: str | None = None) -> list[dict]:
    """
    Parse ALL items from an APST file (not filtered by content type).
    Used for F-06 daily SB report and F-07 disaster report.
    Returns records with fields: broadcast_time, program_block, item_name_raw, item_name
    """
    path = Path(file_path)
    if source_file is None:
        source_file = path.name

    with open(file_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    groups: list[dict] = data.get("lstGrp", [])
    records: list[dict] = []

    for i, grp in enumerate(groups):
        program_block: str = _resolve_group_name(groups, i)

        for item in grp.get("lstPgm", []):
            src_id: str = item.get("SrcID", "")
            raw_name: str = item.get("_PgmName_", "")
            con: str = item.get("Con", "")

            on_t = item.get("OnT", {})
            parsed = _parse_onair_time(on_t)
            if parsed is None:
                continue
            broadcast_date, time_str, _ = parsed

            dur = item.get("Dur", {})
            duration_sec = dur.get("_nDurSec", 0) or 0

            records.append({
                "broadcast_date": broadcast_date,
                "broadcast_time": time_str,
                "program_block":  program_block,
                "item_name_raw":  raw_name,
                "item_name":      extract_item_name(raw_name),
                "src_id":         src_id,
                "con":            con,
                "duration_sec":   duration_sec,
                "main_equipment": item.get("MM", ""),
                "content_type_label": _resolve_content_type_label(con, raw_name),
            })

    return records
