"""
CML file parser — builds a clip_id → info mapping dict.
File encoding: CP949
Format: ^-delimited, one record per line
Header line: '#DTV System Cliplist File'
"""

from pathlib import Path


def parse_cml(file_path: str) -> dict:
    """
    Parse a CML mapping file and return a dict keyed by clip_id.

    Returns:
        {
          'N270944': {
              'item_type': '01',
              'full_name': '26건강하우스깡있는아침',
              'advertiser': '',
              'duration_sec': 10,
          },
          ...
        }
    """
    clip_map: dict = {}

    with open(file_path, "r", encoding="cp949", errors="replace") as f:
        lines = f.readlines()

    for line in lines[1:]:           # Skip '#DTV System Cliplist File' header
        line = line.strip()
        if not line:
            continue

        parts = line.split("^")
        if len(parts) < 5:
            continue

        item_type = parts[0].strip()
        full_name = parts[1].strip()
        advertiser = parts[2].strip()
        duration_raw = parts[3].strip()
        clip_id = parts[4].strip()

        # Skip empty clip IDs and special record types (-1, -7)
        if not clip_id or item_type in ("-1", "-7"):
            continue

        # Parse duration (field is in seconds, zero-padded 6 digits)
        try:
            duration_sec = int(duration_raw)
        except ValueError:
            duration_sec = 0

        clip_map[clip_id] = {
            "item_type": item_type,
            "full_name": full_name,
            "advertiser": advertiser,
            "duration_sec": duration_sec,
        }

    return clip_map


def resolve_cml_path_for_date(cml_setting: str, date: str) -> str | None:
    """
    환경설정의 cml_path 값과 날짜를 받아 실제 사용할 CML 파일 경로를 결정한다.

    - cml_setting이 디렉터리면: 그 안에서 'imc<YYYYMMDD>.cml' 파일을 찾는다
      (예: 2026-05-01 → imc20260501.cml). 없으면 디렉터리 내 가장 최근 .cml
      파일로 대체한다 (과거 단일 파일 운영 방식과의 호환).
    - cml_setting이 파일이면: 그 파일을 그대로 사용한다 (단일 파일 방식, 하위 호환).

    찾지 못하면 None을 반환한다 (호출 측에서 "파일 없음" 로그를 남길 수 있도록).
    """
    if not cml_setting:
        return None

    p = Path(cml_setting)
    date_nodash = date.replace("-", "")

    if p.is_dir():
        dated = p / f"imc{date_nodash}.cml"
        if dated.exists():
            return str(dated)
        candidates = sorted(p.glob("*.cml"))
        return str(candidates[-1]) if candidates else None

    if p.exists():
        return str(p)

    return None


def build_clip_rows(clip_map: dict) -> list[dict]:
    """
    Convert clip_map dict to a list of rows for the clip_map table.
    """
    return [
        {
            "clip_id": clip_id,
            "item_type": info["item_type"],
            "full_name": info["full_name"],
            "advertiser": info["advertiser"],
            "duration_sec": info["duration_sec"],
        }
        for clip_id, info in clip_map.items()
    ]
