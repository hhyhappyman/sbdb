"""
Shared utility functions for all parsers.
"""

import re
from pathlib import Path


# ── APST 파일명 매칭 (대소문자 무시 + 접미사 설정) ─────────────────────────────
# 파일명 형식: <YYYYMMDD><접미사>.apst  (예: 20260720AAA.apst)
# 접미사(suffix)는 환경설정값. 대소문자를 구분하지 않으며, 확장자도 .apst/.APST 모두 허용.

def apst_name_matches(filename: str, suffix: str, date_iso: str | None = None) -> bool:
    """
    파일명이 '<YYYYMMDD><suffix>.apst' 형태인지 대소문자 무시로 검사한다.
      - suffix: 환경설정 접미사(예: 'AAA'/'A'/'P'). 앞뒤 공백·대소문자 무시.
                빈 값이면 '<YYYYMMDD>.apst'(접미사 없음)만 일치.
      - date_iso: 'YYYY-MM-DD'가 주어지면 그 날짜와도 일치해야 함(없으면 날짜 무관).
    """
    name = filename.strip().lower()
    if not name.endswith(".apst"):
        return False
    stem = name[: -len(".apst")]
    m = re.match(r"^(\d{8})(.*)$", stem)
    if not m:
        return False
    date8, rest = m.group(1), m.group(2)
    if rest != (suffix or "").strip().lower():
        return False
    if date_iso is not None and date8 != date_iso.replace("-", ""):
        return False
    return True


def find_apst_files(dir_path, suffix: str, date_iso: str | None = None) -> list:
    """
    지정 폴더에서 접미사(suffix) 규칙에 맞는 APST 파일(Path)들을 정렬해 반환한다.
    date_iso가 주어지면 그 날짜 파일만, 없으면 규칙에 맞는 모든 날짜 파일을 반환한다.
    (대소문자 무시 — .apst/.APST 및 접미사 대소문자 모두 허용)
    """
    p = Path(dir_path)
    if not p.is_dir():
        return []
    return sorted(
        f for f in p.iterdir()
        if f.is_file() and apst_name_matches(f.name, suffix, date_iso)
    )


# ── 급지(SA/A/B/C) 분류 ──────────────────────────────────────────────────────
# 시작시간은 그 시간 이상부터 포함, 끝 시간은 그 시간 미만까지 포함 ([start, end))
# 분 단위(0~1439)로 비교. 모든 24시간이 SA/A/B/C 중 하나로 분류됨(미분류 없음).
_GRADE_RANGES: list[tuple[str, list[tuple[int, int]]]] = [
    ("SA", [(19 * 60 + 30, 23 * 60 + 30)]),
    ("A",  [(8 * 60 + 30, 9 * 60 + 30), (19 * 60, 19 * 60 + 30), (23 * 60 + 30, 24 * 60)]),
    ("B",  [(7 * 60, 8 * 60 + 30), (9 * 60 + 30, 12 * 60), (18 * 60, 19 * 60), (0, 60)]),
    ("C",  [(60, 7 * 60), (12 * 60, 18 * 60)]),
]


def classify_grade(time_str: str) -> str | None:
    """
    'HH:MM:SS' 또는 'HH:MM' 형식의 송출 시간을 SA/A/B/C 등급으로 분류.
    """
    try:
        parts = time_str.split(":")
        h, m = int(parts[0]), int(parts[1])
    except (ValueError, IndexError):
        return None

    total = h * 60 + m
    for label, ranges in _GRADE_RANGES:
        for start, end in ranges:
            if start <= total < end:
                return label
    return None


def clean_prm_campaign_name(item_name: str) -> str:
    """
    PRM 공익/재난 소재명 정제.
    출력 형식: (공익)소재명  또는  (재난)소재명  (괄호와 소재명 사이 공백 없음)
    """
    name = item_name.strip()

    # Remove leading junk like "** DISCARDED EVENT : "
    name = re.sub(r'^\*+\s*DISCARDED\s*EVENT\s*:\s*', '', name).strip()

    # Remove leading letter+) prefix like "K)", "L)"
    name = re.sub(r'^[A-Za-z]\)', '', name).strip()

    keyword = '공익' if '공익' in name else '재난' if '재난' in name else None
    if not keyword:
        return name

    # Extract content portion — strip keyword marker in various positions
    # Already-clean format: "(공익)content" or "(공익) content"
    m = re.match(rf'^\({keyword}\)\s*(.*)', name, re.DOTALL)
    if m:
        content = m.group(1).strip()
    else:
        # Pattern A: keyword(content) — e.g. "공익(운전 문화)"
        m = re.match(rf'^{keyword}\((.+)\)$', name)
        if m:
            content = m.group(1).strip()
        else:
            # Pattern B: content(keyword) — e.g. "일터에서 국민안전(공익)"
            m = re.match(rf'^(.+)\({keyword}\)\s*$', name)
            if m:
                content = m.group(1).strip()
            else:
                # Pattern C: keyword[-space]content — e.g. "재난-시각장애인 도움"
                m = re.match(rf'^{keyword}[-\s]+(.+)$', name)
                if m:
                    content = m.group(1).strip()
                else:
                    # Fallback: remove keyword wherever it appears
                    content = re.sub(rf'{keyword}', '', name).strip()
                    content = re.sub(r'^[-_\s]+|[-_\s]+$', '', content)

    # --- Clean the content portion ---

    # Remove [...] bracket expressions (e.g. [※], [재인증])
    content = re.sub(r'\[[^\]]*\]', '', content)

    # Remove # symbol (used as special marker in some PRM names)
    content = re.sub(r'#', '', content)

    # Remove (K) (L) type letter-prefix parens
    content = re.sub(r'\([A-Za-z]\)', '', content)

    # Remove duration expressions like (30초), (1분), (1분30초), (3분6초) etc.
    content = re.sub(r'\(\d+분?\d*초?\)', '', content)

    # Remove empty parentheses ()
    content = re.sub(r'\(\s*\)', '', content)

    # Remove leading ) left over from partial parens
    content = re.sub(r'^\s*\)', '', content)

    # Remove trailing patterns like "4/", "12/", "9/1-1", "-3/5" etc.
    content = re.sub(r'\s*[-\d/]+\s*$', lambda m: '' if re.search(r'/', m.group()) else m.group(), content)

    # Remove stray special characters: ※ ★ ▶ ▷ ◆ □ ■
    content = re.sub(r'[※★▶▷◆□■]', '', content)

    # Remove trailing number sequences with slashes like "9/1-1", "10", "-3/5", "(2)"
    content = re.sub(r'\s*\(\d+\)\s*$', '', content)
    content = re.sub(r'\s+\d+$', '', content)
    content = re.sub(r'\s+[-\d/][-\d/]+$', '', content)

    # Collapse multiple spaces
    content = re.sub(r'\s{2,}', ' ', content).strip()

    # Remove trailing punctuation: - , .
    content = re.sub(r'[-,.\s]+$', '', content).strip()

    return f'({keyword}){content}' if content else f'({keyword})'


def extract_item_name(raw_name: str) -> str:
    """
    Remove duration info from a broadcast item name and return the clean name.

    Examples:
      '영산강 55초~60초(5월용)'              -> '영산강'
      '행정통합 30초 (2월11일~7월10일)'      -> '행정통합'
      '미라클의원(여성달모) 1분7초~12초'      -> '미라클의원(여성달모)'
      '장가게(문화탐방)40~45초(~소재교체시)' -> '장가게(문화탐방)'
      '유네스코(무등산재인증)1분~1분5초'      -> '유네스코(무등산재인증)'
      '26ID(민)-금남로'                      -> '26ID(민)-금남로'  (no duration)
    """
    # Match duration marker:
    #   - preceded by whitespace, closing parenthesis, OR a Hangul syllable
    #     (예: '안유성1분7초'처럼 공백 없이 한글 뒤에 바로 붙는 경우도 인식)
    #   - digits + optional range + 분/초 unit
    match = re.search(r'(\s+\d|\)\d|[가-힣]\d)(?:[~\-\d분]*)[초분]', raw_name)
    if match:
        idx = match.start()
        # 앞 문자가 ')' 또는 한글이면 그 문자는 이름의 일부이므로 자르는 위치를 한 칸 뒤로
        if raw_name[idx] == ')' or '가' <= raw_name[idx] <= '힣':
            idx += 1
        return raw_name[:idx].strip()
    return raw_name.strip()
