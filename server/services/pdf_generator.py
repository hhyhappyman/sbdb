"""
PDF generator using reportlab.
- generate_monthly_pdf : F-04 '광주MBC 방송홍보 SB송출 현황' format
- generate_daily_pdf   : F-06 일별 프로그램-SB 내역
- generate_disaster_pdf: F-07 일별 재난방송 소재
"""

import os
import calendar
from datetime import datetime, date as date_type
from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.platypus import (
    SimpleDocTemplate, Table, TableStyle, Paragraph,
    Spacer, Image, HRFlowable,
)
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT

from config import (
    REPORT_MONTHLY_DIR, REPORT_DAILY_DIR, REPORT_DISASTER_DIR, REPORT_SUMMARY_DIR,
    REPORT_SUBTITLE_DIR,
)

# ── Korean font registration ────────────────────────────────────────────────
# Uses system fonts if available; falls back to Helvetica

_FONT_REGISTERED = False

def _try_register(name: str, path: str) -> bool:
    """폰트 1개 등록 시도. .ttc(폰트 컬렉션)는 subfontIndex=0 사용."""
    try:
        if path.lower().endswith(".ttc"):
            pdfmetrics.registerFont(TTFont(name, path, subfontIndex=0))
        else:
            pdfmetrics.registerFont(TTFont(name, path))
        return True
    except Exception:
        return False


def _korean_font_candidates() -> list[str]:
    """
    한글 지원 폰트 후보 파일 경로 목록(우선순위 순).
    reportlab은 TrueType(glyf)만 등록 가능하고 Noto CJK 같은 CFF/OpenType는 실패하므로,
    TrueType(.ttf, 특히 Nanum)을 먼저, 그다음 나머지를 시도하도록 정렬한다.
    """
    fixed = [
        "/usr/share/fonts/truetype/nanum/NanumGothic.ttf",
        "/usr/share/fonts/truetype/unfonts-core/UnDotum.ttf",
        "C:/Windows/Fonts/malgun.ttf",
        "/mnt/c/Windows/Fonts/malgun.ttf",
    ]
    result = [p for p in fixed if os.path.exists(p)]

    import glob
    keywords = ("NanumGothic", "NanumBarun", "UnDotum", "malgun", "NotoSansKR", "NotoSansCJK")
    ttf_first: list[str] = []
    others: list[str] = []
    for root in (os.path.expanduser("~/.fonts"), "/usr/local/share/fonts", "/usr/share/fonts"):
        if not os.path.isdir(root):
            continue
        for ext in ("ttf", "ttc", "otf"):
            for f in sorted(glob.glob(f"{root}/**/*.{ext}", recursive=True)):
                base = os.path.basename(f).lower()
                if not any(k.lower() in base for k in keywords):
                    continue
                (ttf_first if ext == "ttf" else others).append(f)
    # 중복 제거하며 순서 유지
    ordered = result + ttf_first + others
    seen = set()
    return [p for p in ordered if not (p in seen or seen.add(p))]


def _register_fonts() -> str:
    """Register a Korean-capable font and return the font name."""
    global _FONT_REGISTERED
    if _FONT_REGISTERED:
        return "KoreanFont"

    for path in _korean_font_candidates():
        if not _try_register("KoreanFont", path):
            continue   # CFF/OpenType(Noto CJK 등) 등록 실패 → 다음 후보
        # Bold 변형 파일이 있으면 사용, 없으면 Regular를 Bold로도 등록
        bold_path = (path.replace("Regular", "Bold")
                         .replace("NanumGothic", "NanumGothicBold")
                         .replace("malgun.ttf", "malgunbd.ttf"))
        if not (bold_path != path and os.path.exists(bold_path)
                and _try_register("KoreanFont-Bold", bold_path)):
            _try_register("KoreanFont-Bold", path)
        _FONT_REGISTERED = True
        return "KoreanFont"

    return "Helvetica"   # Fallback (Korean may not render)


# ── Time conversion ─────────────────────────────────────────────────────────

_DAY_OF_WEEK_KO = ["월", "화", "수", "목", "금", "토", "일"]


def _to_broadcast_hhmm(time_str: str) -> str:
    """
    Convert 'HH:MM:SS' to 4-digit broadcast HHMM with 25-hour convention.
    00:14:00 → '2414',  01:30:00 → '2530',  06:00:00 → '0600'
    Times 00:00~04:59 are treated as next-day (add 24h).
    """
    parts = time_str.split(":")
    if len(parts) < 2:
        return time_str
    h = int(parts[0])
    m = int(parts[1])
    if h < 5:
        h += 24
    return f"{h:02d}{m:02d}"


def _date_to_weekday(date_str: str) -> str:
    """'2026-05-06' → '수'"""
    try:
        d = datetime.strptime(date_str, "%Y-%m-%d")
        return _DAY_OF_WEEK_KO[d.weekday()]
    except ValueError:
        return ""


def _format_date_ko(date_str: str) -> str:
    """'2026-05-06' → '26. 5. 6'"""
    try:
        d = datetime.strptime(date_str, "%Y-%m-%d")
        return f"{d.year % 100}. {d.month}. {d.day}"
    except ValueError:
        return date_str


# ── Common table style helpers ───────────────────────────────────────────────

_DARK_GRAY = colors.HexColor("#3A3A3A")
_LIGHT_GRAY = colors.HexColor("#F2F2F2")
_BORDER = colors.HexColor("#888888")
_HEADER_BG = _DARK_GRAY
_HEADER_FG = colors.white


def _base_table_style() -> list:
    return [
        ("FONTNAME",      (0, 0), (-1, -1), "KoreanFont"),
        ("FONTSIZE",      (0, 0), (-1, -1), 9),
        ("GRID",          (0, 0), (-1, -1), 0.5, _BORDER),
        ("ALIGN",         (0, 0), (-1, -1), "CENTER"),
        ("VALIGN",        (0, 0), (-1, -1), "MIDDLE"),
        ("ROWBACKGROUNDS",(0, 1), (-1, -1), [colors.white, _LIGHT_GRAY]),
    ]


_ALIGN_MAP = {"CENTER": TA_CENTER, "LEFT": TA_LEFT, "RIGHT": TA_RIGHT}


def _wrap_cell(text, font: str, size: float = 8, align: str = "CENTER"):
    """
    긴 텍스트(프로그램명·소재명 등)를 Paragraph로 감싸 셀 폭에 맞게 자동 줄바꿈되게
    한다. plain 문자열을 Table에 그대로 넣으면 reportlab이 줄바꿈 없이 셀 밖으로
    흘러넘쳐(overlap) 옆 칸 텍스트와 겹쳐 보인다.
    """
    return Paragraph(
        str(text) if text is not None else "",
        ParagraphStyle(
            "wrap_cell", fontName=font, fontSize=size, leading=size * 1.2,
            alignment=_ALIGN_MAP.get(align, TA_CENTER),
        ),
    )


# ── F-04 : Monthly report ────────────────────────────────────────────────────

def generate_monthly_pdf(
    item_name: str,
    year: int,
    month: int,
    days: list[dict],        # [{date, times:[HH:MM:SS,...], count}, ...]
    advertiser: dict,        # from advertisers table
    settings: dict,          # from app_settings
) -> str:
    """
    Generate F-04 '광주MBC 방송홍보 SB송출 현황' PDF.
    Returns the file path of the generated PDF.
    """
    font = _register_fonts()
    bold = font + "-Bold" if font == "KoreanFont" else font
    company = (settings.get("company_name") or "광주문화방송").strip() or "광주문화방송"
    short = (settings.get("company_short") or "광주MBC").strip() or "광주MBC"

    # Output path (여러 소재명은 길거나 특수문자를 포함할 수 있어 안전하게 정리)
    _safe = str(item_name).replace("/", "_").replace("\\", "_")[:80]
    out_path = str(REPORT_MONTHLY_DIR / f"sb_monthly_{_safe}_{year}{month:02d}.pdf")

    doc = SimpleDocTemplate(
        out_path,
        pagesize=A4,
        rightMargin=15 * mm,
        leftMargin=15 * mm,
        topMargin=12 * mm,
        bottomMargin=12 * mm,   # 위/아래 여백 동일. 행 높이는 아래에서 자동 계산.
    )

    W = A4[0] - 30 * mm   # usable width
    story = []

    # ── Logo ── (이미지가 설정된 경우에만 표시. 미설정 시 텍스트 placeholder 없음)
    logo_path = settings.get("logo_path", "")
    if logo_path and os.path.exists(logo_path):
        logo = Image(logo_path, width=40 * mm, height=14 * mm)
        logo.hAlign = "RIGHT"
        story.append(logo)
        story.append(Spacer(1, 3 * mm))

    # ── Title ──
    story.append(Paragraph(
        f"{short} 방송홍보 SB송출 현황",
        ParagraphStyle("title", fontName=bold, fontSize=18,
                       alignment=TA_CENTER, spaceAfter=4 * mm),
    ))

    # ── Info table ──
    cal = calendar.monthrange(year, month)
    last_day = cal[1]
    d_start = date_type(year, month, 1)
    d_end   = date_type(year, month, last_day)
    wd_start = _DAY_OF_WEEK_KO[d_start.weekday()]
    wd_end   = _DAY_OF_WEEK_KO[d_end.weekday()]
    period_str = (
        f"{year}.{month}.1({wd_start})~{year}.{month}.{last_day}({wd_end})"
    )

    # 회사명/사업자등록번호/업태·업종은 광주MBC 고정값. 대표이사는 환경설정값.
    _note = advertiser.get("note") or "송출시간은 방송사 상황에 따라 변동될 수 있음"
    _note_para = Paragraph(
        _note, ParagraphStyle("note", fontName=font, fontSize=8, alignment=TA_LEFT, leading=10)
    )
    info_data = [
        ["회 사 명",  company,
         "사업자등록번호", "410-81-06350"],
        ["송출 내용",  item_name,
         "대 표 이 사", settings.get("ceo_name", "")],
        ["송출 매체",  advertiser.get("broadcast_medium", "TV"),
         "업 태·업 종", "서비스·방송"],
        ["송출 기간",  period_str,
         "비  고",      _note_para],
    ]

    col_w = [22 * mm, 55 * mm, 28 * mm, 65 * mm]
    info_table = Table(info_data, colWidths=col_w)
    info_table.setStyle(TableStyle([
        ("FONTNAME",    (0, 0), (-1, -1), font),
        ("FONTSIZE",    (0, 0), (-1, -1), 9),
        ("FONTNAME",    (0, 0), (0, -1), bold),
        ("FONTNAME",    (2, 0), (2, -1), bold),
        ("BACKGROUND",  (0, 0), (0, -1), _LIGHT_GRAY),
        ("BACKGROUND",  (2, 0), (2, -1), _LIGHT_GRAY),
        ("GRID",        (0, 0), (-1, -1), 0.5, _BORDER),
        ("ALIGN",       (0, 0), (-1, -1), "CENTER"),
        ("ALIGN",       (1, 0), (1, -1), "LEFT"),
        ("ALIGN",       (3, 0), (3, -1), "LEFT"),
        ("VALIGN",      (0, 0), (-1, -1), "MIDDLE"),
        ("LEFTPADDING", (1, 0), (1, -1), 4),
        ("LEFTPADDING", (3, 0), (3, -1), 4),
        ("ROWHEIGHT",   (0, 0), (-1, -1), 7 * mm),
    ]))
    story.append(info_table)
    story.append(Spacer(1, 2.5 * mm))

    # ── Data table ── (비고 컬럼 제거 — 한 페이지에 맞추기 위해 폭/행 높이 축소)
    header = ["일  시", "요일", "횟수", "T  V", "RADIO-AM", "RADIO-FM"]
    col_w2 = [24 * mm, 12 * mm, 14 * mm, 76 * mm, 22 * mm, 22 * mm]

    days_map: dict = {d["date"]: d for d in days}
    total_count = 0
    data_rows = []

    for day_num in range(1, last_day + 1):
        d = date_type(year, month, day_num)
        date_str = d.strftime("%Y-%m-%d")
        wd = _DAY_OF_WEEK_KO[d.weekday()]
        day_info = days_map.get(date_str)
        if day_info:
            cnt = day_info["count"]
            times_str = " ".join(
                _to_broadcast_hhmm(t) for t in day_info["times"]
            )
            total_count += cnt
        else:
            cnt = 0
            times_str = ""

        data_rows.append([
            _format_date_ko(date_str),
            wd,
            str(cnt) if cnt else "",
            # 시간이 많아 칸을 넘치면 자동 줄바꿈(Paragraph). 빈 값은 그대로 둔다.
            _wrap_cell(times_str, font, size=8) if times_str else "",
            "-",
            "-",
        ])

    # Total row
    data_rows.append([
        "총  계",
        f"{last_day} 일",
        f"{total_count} 회",
        f"총 {total_count} 회",
        "-",
        "-",
    ])

    table_data = [header] + data_rows
    data_table = Table(table_data, colWidths=col_w2)

    style = _base_table_style() + [
        ("FONTSIZE",      (0, 0), (-1, -1), 8.5),
        ("TOPPADDING",    (0, 0), (-1, -1), 2.2),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 2.2),
        ("FONTNAME",   (0, 0), (-1, 0), bold),
        ("FONTSIZE",   (0, 0), (-1, 0), 9),
        ("BACKGROUND", (0, 0), (-1, 0), _HEADER_BG),
        ("TEXTCOLOR",  (0, 0), (-1, 0), _HEADER_FG),
        # Total row
        ("FONTNAME",   (0, -1), (-1, -1), bold),
        ("BACKGROUND", (0, -1), (-1, -1), _LIGHT_GRAY),
        ("SPAN",       (3, -1), (5, -1)),
        ("ALIGN",      (3, -1), (3, -1), "CENTER"),
    ]
    data_table.setStyle(TableStyle(style))
    story.append(data_table)
    story.append(Spacer(1, 3 * mm))

    # ── Footer ── (확인함 뒤 날짜 표기 제거)
    seal_path = settings.get("seal_path", "")

    footer_data = [[
        Paragraph(
            "위와 같이 방송 송출 완료하였을 확인함",
            ParagraphStyle("footer_l", fontName=font, fontSize=10, alignment=TA_LEFT),
        ),
        Paragraph(
            f"{company}(주)",
            ParagraphStyle("footer_r", fontName=bold, fontSize=10, alignment=TA_RIGHT),
        ),
    ]]
    footer_col_w = [W * 0.6, W * 0.4]
    footer_table = Table(footer_data, colWidths=footer_col_w)
    footer_table.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("ALIGN",  (1, 0), (1, 0),  "RIGHT"),
    ]))
    story.append(footer_table)

    # Seal image (if available)
    if seal_path and os.path.exists(seal_path):
        seal = Image(seal_path, width=18 * mm, height=18 * mm)
        seal.hAlign = "RIGHT"
        story.append(seal)

    # ── 행 높이 자동 계산 (위/아래 여백 동일 + 한 페이지 채우기) ──
    # 현재 story 전체 높이를 측정한 뒤, 남는 세로 공간을 표의 각 행에 고르게
    # 분배하여 내용이 페이지를 꽉 채우도록 셀 상하 패딩을 다시 정한다.
    # 내용이 많아 넘칠 때는 패딩이 최소값까지 줄어 자동으로 한 페이지에 맞춘다.
    # 상·하 여백(12mm+12mm) + SimpleDocTemplate 프레임 기본 상하 패딩(6pt+6pt)을
    # 제외한 실제 배치 가능 높이. 푸터(하단 확인문구)가 한 행이라 분할되지 않고
    # 통째로 배치돼야 하므로, 측정 합계보다 실제 소요가 커지는 점을 감안해
    # 안전 여유(20pt)를 더 빼 넘침(2페이지)을 방지한다.
    frame_h = A4[1] - 24 * mm - 12 - 20

    # 표를 제외한 나머지 요소(제목/정보표/여백/푸터 등)의 높이를 1회 측정한다.
    # (실제 build에 쓰이는 story 객체는 데이터표를 제외하고만 wrap → 손상 없음)
    others_h = sum(
        f.wrap(W, 100000)[1] for f in story if f is not data_table
    )

    # 데이터표는 '측정 전용 복제본'으로만 반복 측정한다(실제 객체 손상 방지).
    # 큰 패딩부터 0.1pt씩 낮추며, 한 페이지에 들어오는 가장 큰 값을 채택한다.
    #  → 내용이 적으면 넉넉히 벌려 페이지를 채우고(위·아래 여백 균형),
    #    내용이 많으면 자동으로 줄간격을 좁혀 한 페이지에 맞춘다.
    chosen_pad = 1.4
    pad = 6.0
    while pad >= 1.4:
        probe = Table(table_data, colWidths=col_w2)
        probe.setStyle(TableStyle(style + [
            ("TOPPADDING",    (0, 0), (-1, -1), pad),
            ("BOTTOMPADDING", (0, 0), (-1, -1), pad),
        ]))
        table_h = probe.wrap(W, 100000)[1]
        if others_h + table_h <= frame_h:
            chosen_pad = pad
            break
        pad -= 0.1

    data_table.setStyle(TableStyle([
        ("TOPPADDING",    (0, 0), (-1, -1), chosen_pad),
        ("BOTTOMPADDING", (0, 0), (-1, -1), chosen_pad),
    ]))

    doc.build(story)
    return out_path


# ── F-06 : Daily SB report ───────────────────────────────────────────────────

def generate_daily_pdf(date: str, items: list[dict], settings: dict) -> str:
    """
    F-06 — 일별 프로그램-SB 내역 PDF.
    Columns: 방송시작시간 | 프로그램명 | SB 소재 제목
    """
    font = _register_fonts()
    bold = font + "-Bold" if font == "KoreanFont" else font

    date_nodash = date.replace("-", "")
    out_path = str(REPORT_DAILY_DIR / f"sb_report_{date_nodash}.pdf")

    doc = SimpleDocTemplate(
        out_path, pagesize=A4,
        rightMargin=15 * mm, leftMargin=15 * mm,
        topMargin=15 * mm, bottomMargin=15 * mm,
    )
    W = A4[0] - 30 * mm
    story = []

    # Header
    story.append(Paragraph(
        f"방송 운행표  —  {date}",
        ParagraphStyle("h", fontName=bold, fontSize=14,
                       alignment=TA_CENTER, spaceAfter=6 * mm),
    ))
    story.append(HRFlowable(width=W, thickness=1, color=_DARK_GRAY))
    story.append(Spacer(1, 4 * mm))

    if not items:
        story.append(Paragraph(
            "해당 날짜의 SB 송출 내역이 없습니다.",
            ParagraphStyle("empty", fontName=font, fontSize=10, alignment=TA_CENTER),
        ))
    else:
        header = ["방송시작시간", "프로그램명", "소재종류", "SB 소재 제목"]
        col_w = [28 * mm, 48 * mm, 22 * mm, W - 28 * mm - 48 * mm - 22 * mm]

        # 소재종류별 음영/구분선 색
        _SKY   = colors.HexColor("#DCE6F1")   # 프로그램 행
        _GREEN = colors.HexColor("#E2EFDA")   # 광고/광고그룹 행

        # '이어서' 행은 굵게 — 표에 넣기 전에 프로그램명/소재제목 폰트를 결정해
        # Paragraph 자체에 굵기를 반영한다.
        def _is_end_notice(prog):
            return "방송 종료" in (prog or "") or "방송종료" in (prog or "")

        rows = [header]
        extra = []
        for i, r in enumerate(items):
            lbl = r.get("content_type_label", "")
            is_ct = lbl == "이어서"
            f = bold if is_ct else font
            rows.append([
                r.get("broadcast_time_display") or r["broadcast_time"],
                _wrap_cell(r["program_block"], f, size=8),
                lbl,
                _wrap_cell(r["item_name_raw"], f, size=8, align="LEFT"),
            ])
            ridx = i + 1
            if is_ct:
                # 프로그램 그룹 시작 → 위쪽에 굵은 구분선 + 이어서 행 굵게
                extra.append(("LINEABOVE", (0, ridx), (-1, ridx), 1.5, _DARK_GRAY))
                extra.append(("FONTNAME", (0, ridx), (0, ridx), bold))
                extra.append(("FONTNAME", (2, ridx), (2, ridx), bold))
            elif lbl == "프로그램" and "방송순서" not in (r.get("program_block") or ""):
                # 첫부분 '방송순서 안내'는 프로그램이어도 하늘색 음영 제외
                extra.append(("BACKGROUND", (0, ridx), (-1, ridx), _SKY))
            elif lbl in ("광고", "광고그룹"):
                extra.append(("BACKGROUND", (0, ridx), (-1, ridx), _GREEN))

            # 방송종료 안내 시작 행 → 위쪽 굵은 구분선 (이어서로 이미 처리된 경우 제외)
            if not is_ct and _is_end_notice(r.get("program_block", "")) \
                    and not (i > 0 and _is_end_notice(items[i - 1].get("program_block", ""))):
                extra.append(("LINEABOVE", (0, ridx), (-1, ridx), 1.5, _DARK_GRAY))

        # 표 외곽선 굵게: 맨 윗줄 / 헤더(제목) 아래 / 맨 밑줄
        last = len(items)
        extra += [
            ("LINEABOVE", (0, 0), (-1, 0), 1.5, _DARK_GRAY),
            ("LINEBELOW", (0, 0), (-1, 0), 1.5, _DARK_GRAY),
            ("LINEBELOW", (0, last), (-1, last), 1.5, _DARK_GRAY),
        ]

        t = Table(rows, colWidths=col_w)
        t.setStyle(TableStyle(_base_table_style() + [
            # 방송운행표는 회색 교차 음영(zebra) 제거 — 본문 전체 흰색으로 덮어씀.
            # (프로그램/광고 등 개별 음영은 아래 extra에서 다시 덮어써 유지됨)
            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white]),
            ("FONTNAME",   (0, 0), (-1, 0), bold),
            ("BACKGROUND", (0, 0), (-1, 0), _HEADER_BG),
            ("TEXTCOLOR",  (0, 0), (-1, 0), _HEADER_FG),
            ("ALIGN",      (3, 1), (3, -1), "LEFT"),
            ("LEFTPADDING",(3, 1), (3, -1), 4),
        ] + extra))
        story.append(t)

    # Footer
    story.append(Spacer(1, 6 * mm))
    story.append(Paragraph(
        f"총 {len(items)}건 | 생성일시: {datetime.now().strftime('%Y-%m-%d %H:%M')}",
        ParagraphStyle("ft", fontName=font, fontSize=8,
                       alignment=TA_RIGHT, textColor=colors.gray),
    ))

    doc.build(story)
    return out_path


# ── F-07 : Disaster broadcast report ────────────────────────────────────────

def generate_disaster_pdf(date: str, items: list[dict], settings: dict) -> str:
    """
    F-07 — 재난방송 소재 PDF.
    Columns: 방송시작시간 | 프로그램명 | SB 소재 제목
    소재 없을 경우 '해당 없음' 문구 포함 빈 PDF 생성.
    """
    font = _register_fonts()
    bold = font + "-Bold" if font == "KoreanFont" else font

    date_nodash = date.replace("-", "")
    out_path = str(REPORT_DISASTER_DIR / f"disaster_report_{date_nodash}.pdf")

    doc = SimpleDocTemplate(
        out_path, pagesize=A4,
        rightMargin=15 * mm, leftMargin=15 * mm,
        topMargin=15 * mm, bottomMargin=15 * mm,
    )
    W = A4[0] - 30 * mm
    story = []

    # Header
    story.append(Paragraph(
        f"재난방송 소재 송출 내역  —  {date}",
        ParagraphStyle("h", fontName=bold, fontSize=14,
                       alignment=TA_CENTER, spaceAfter=6 * mm),
    ))
    story.append(HRFlowable(width=W, thickness=1, color=colors.HexColor("#CC0000")))
    story.append(Spacer(1, 4 * mm))

    if not items:
        # F-07: no disaster items → include "해당 없음" message
        story.append(Paragraph(
            "해당 없음",
            ParagraphStyle("none", fontName=bold, fontSize=14,
                           alignment=TA_CENTER, textColor=colors.gray,
                           spaceBefore=20 * mm),
        ))
        story.append(Paragraph(
            f"({date} 에 재난방송 소재 송출 내역이 없습니다.)",
            ParagraphStyle("sub", fontName=font, fontSize=9,
                           alignment=TA_CENTER, textColor=colors.gray),
        ))
    else:
        header = ["방송시작시간", "프로그램명", "SB 소재 제목"]
        col_w = [30 * mm, 55 * mm, W - 30 * mm - 55 * mm]

        rows = [header] + [
            [r["broadcast_time"],
             _wrap_cell(r["program_block"], font, size=8),
             _wrap_cell(r["item_name_raw"], font, size=8, align="LEFT")]
            for r in items
        ]

        t = Table(rows, colWidths=col_w)
        t.setStyle(TableStyle(_base_table_style() + [
            ("FONTNAME",   (0, 0), (-1, 0), bold),
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#CC0000")),
            ("TEXTCOLOR",  (0, 0), (-1, 0), _HEADER_FG),
            ("ALIGN",      (2, 1), (2, -1), "LEFT"),
            ("LEFTPADDING",(2, 1), (2, -1), 4),
        ]))
        story.append(t)

    # Footer
    story.append(Spacer(1, 6 * mm))
    story.append(Paragraph(
        f"재난방송 {len(items)}건 | 생성일시: {datetime.now().strftime('%Y-%m-%d %H:%M')}",
        ParagraphStyle("ft", fontName=font, fontSize=8,
                       alignment=TA_RIGHT, textColor=colors.gray),
    ))

    doc.build(story)
    return out_path


# ── 일일 운행표 / 일일 ID 운행표 ──────────────────────────────────────────────

def generate_daily_summary_pdf(date: str, type_label: str, items: list[dict]) -> str:
    """
    일일 운행표(캠페인) / 일일 ID 운행표(ID) PDF.
    컬럼: 소재명 | 총횟수 | SA | A | B | C
    items: get_daily_item_summary() 결과 (총횟수 내림차순 정렬된 상태로 전달됨)
    """
    font = _register_fonts()
    bold = font + "-Bold" if font == "KoreanFont" else font

    date_nodash = date.replace("-", "")
    prefix = "id_summary" if type_label == "ID" else "campaign_summary"
    out_path = str(REPORT_SUMMARY_DIR / f"{prefix}_{date_nodash}.pdf")

    doc = SimpleDocTemplate(
        out_path, pagesize=A4,
        rightMargin=15 * mm, leftMargin=15 * mm,
        topMargin=15 * mm, bottomMargin=15 * mm,
    )
    W = A4[0] - 30 * mm
    story = []

    title = f"일일 {'ID' if type_label == 'ID' else ''} 운행표".replace("  ", " ")
    accent = colors.HexColor("#722ed1") if type_label == "ID" else colors.HexColor("#1677ff")

    story.append(Paragraph(
        f"{title}  —  {date}",
        ParagraphStyle("h", fontName=bold, fontSize=14,
                       alignment=TA_CENTER, spaceAfter=6 * mm),
    ))
    story.append(HRFlowable(width=W, thickness=1, color=accent))
    story.append(Spacer(1, 4 * mm))

    if not items:
        story.append(Paragraph(
            f"해당 날짜에 {type_label} 송출 내역이 없습니다.",
            ParagraphStyle("empty", fontName=font, fontSize=10, alignment=TA_CENTER),
        ))
    else:
        header = ["소재명", "총횟수", "SA", "A", "B", "C"]
        col_w = [W - 5 * 22 * mm, 22 * mm, 22 * mm, 22 * mm, 22 * mm, 22 * mm]

        rows = [header] + [
            [
                _wrap_cell(r["item_name"], font, size=8, align="LEFT"), f'{r["total_count"]}회',
                str(r["sa"] or 0), str(r["a"] or 0), str(r["b"] or 0), str(r["c"] or 0),
            ]
            for r in items
        ]

        total_row = [
            "총계",
            f'{sum(r["total_count"] for r in items)}회',
            str(sum(r["sa"] or 0 for r in items)),
            str(sum(r["a"] or 0 for r in items)),
            str(sum(r["b"] or 0 for r in items)),
            str(sum(r["c"] or 0 for r in items)),
        ]
        rows.append(total_row)

        t = Table(rows, colWidths=col_w)
        t.setStyle(TableStyle(_base_table_style() + [
            ("FONTNAME",   (0, 0), (-1, 0), bold),
            ("BACKGROUND", (0, 0), (-1, 0), accent),
            ("TEXTCOLOR",  (0, 0), (-1, 0), _HEADER_FG),
            ("ALIGN",      (0, 1), (0, -1), "LEFT"),
            ("LEFTPADDING",(0, 1), (0, -1), 4),
            ("FONTNAME",   (0, -1), (-1, -1), bold),
            ("BACKGROUND", (0, -1), (-1, -1), _LIGHT_GRAY),
        ]))
        story.append(t)

    # Footer
    story.append(Spacer(1, 6 * mm))
    story.append(Paragraph(
        f"소재 {len(items)}종 | 생성일시: {datetime.now().strftime('%Y-%m-%d %H:%M')}",
        ParagraphStyle("ft", fontName=font, fontSize=8,
                       alignment=TA_RIGHT, textColor=colors.gray),
    ))

    doc.build(story)
    return out_path


# ── 흘림자막·공익광고·재난피해 사전예방 송출내역 ────────────────────────────────

def _fmt_dur(sec) -> str:
    """초 단위 → '30\"' 또는 \"1'09\\\"\" 형식."""
    if not sec:
        return ""
    sec = int(sec)
    if sec < 60:
        return f'{sec}"'
    return f"{sec // 60}'{sec % 60:02d}\""


def _hhmm_ko(t: str) -> str:
    """'HH:MM:SS' → 'HH시MM분'."""
    if not t:
        return ""
    p = t.split(":")
    try:
        return f"{int(p[0]):02d}시{int(p[1]):02d}분"
    except (ValueError, IndexError):
        return t


def generate_subtitle_campaign_pdf(data: dict) -> str:
    """
    흘림자막 및 공익광고/재난피해 사전예방 송출내역 PDF.
    data: aggregator.get_subtitle_campaign_report() 결과.
    """
    font = _register_fonts()
    bold = font + "-Bold" if font == "KoreanFont" else font

    date = data["date"]
    date_nodash = date.replace("-", "")
    out_path = str(REPORT_SUBTITLE_DIR / f"subtitle_campaign_{date_nodash}.pdf")

    doc = SimpleDocTemplate(
        out_path, pagesize=A4,
        rightMargin=12 * mm, leftMargin=12 * mm,
        topMargin=12 * mm, bottomMargin=12 * mm,
    )
    W = A4[0] - 24 * mm
    story = []

    # ── 제목 + 날짜 ──
    story.append(Paragraph(
        "□ 흘림자막 및 공익광고/재난피해 사전예방 송출내역 □",
        ParagraphStyle("t", fontName=bold, fontSize=15, alignment=TA_CENTER, spaceAfter=3 * mm),
    ))
    try:
        d = datetime.strptime(date, "%Y-%m-%d")
        wd = _date_to_weekday(date)
        date_line = f"{d.year}년 {d.month}월 {d.day}일 ({wd}) (00:00 ~ 24:00)"
    except ValueError:
        date_line = f"{date} (00:00 ~ 24:00)"
    story.append(Paragraph(
        date_line,
        ParagraphStyle("dl", fontName=bold, fontSize=12, alignment=TA_CENTER, spaceAfter=5 * mm),
    ))

    sec_style = ParagraphStyle("sec", fontName=bold, fontSize=10, spaceBefore=3 * mm, spaceAfter=1.5 * mm)

    def _section_title(txt):
        story.append(Paragraph(f"□ {txt}", sec_style))

    def _table(rows, col_w, header_rows=1):
        t = Table(rows, colWidths=col_w)
        t.setStyle(TableStyle(_base_table_style() + [
            ("FONTNAME",   (0, 0), (-1, header_rows - 1), bold),
            ("BACKGROUND", (0, 0), (-1, header_rows - 1), _LIGHT_GRAY),
            ("FONTSIZE",   (0, 0), (-1, -1), 9),
        ]))
        story.append(t)

    # ── 1. UHD방송홍보 (영상 좌 / 자막 우) ──
    _section_title("UHD방송홍보")
    uhd_v, uhd_s = data["uhd_video"], data["uhd_sub"]
    n = max(len(uhd_v), len(uhd_s), 1)
    rows = [["송출시간(영상)", "프로그램", "송출시간(자막)", "프로그램"]]
    for i in range(n):
        v = uhd_v[i] if i < len(uhd_v) else {}
        s = uhd_s[i] if i < len(uhd_s) else {}
        rows.append([
            _hhmm_ko(v.get("time", "")), _wrap_cell(v.get("program", ""), font, size=8),
            _hhmm_ko(s.get("time", "")), _wrap_cell(s.get("program", ""), font, size=8),
        ])
    _table(rows, [30 * mm, W / 2 - 30 * mm, 30 * mm, W / 2 - 30 * mm])

    # ── 2. TV직접수신 (자막, 2쌍씩 배치) ──
    _section_title("TV직접수신")
    tv = data["tv_direct"]
    rows = [["송출시간(자막)", "프로그램", "송출시간(자막)", "프로그램"]]
    n = max((len(tv) + 1) // 2, 1)
    for i in range(n):
        a = tv[2 * i]     if 2 * i     < len(tv) else {}
        b = tv[2 * i + 1] if 2 * i + 1 < len(tv) else {}
        rows.append([
            _hhmm_ko(a.get("time", "")), _wrap_cell(a.get("program", ""), font, size=8),
            _hhmm_ko(b.get("time", "")), _wrap_cell(b.get("program", ""), font, size=8),
        ])
    _table(rows, [30 * mm, W / 2 - 30 * mm, 30 * mm, W / 2 - 30 * mm])

    # ── 3. 시청자의견 (근무자/비고 칸 삭제) ──
    _section_title("시청자의견 (주1회 목요일)")
    vo = data["viewer_opinion"]
    rows = [["송출시간(자막)", "프로그램"]]
    for i in range(max(len(vo), 1)):
        r = vo[i] if i < len(vo) else {}
        rows.append([_hhmm_ko(r.get("time", "")), _wrap_cell(r.get("program", ""), font, size=8)])
    _table(rows, [35 * mm, W - 35 * mm])

    # ── 4. 공익광고 송출내역 (본사 포함) ──
    _section_title("공익광고 송출내역 (본사 포함)")
    camp = data["campaign"]
    worker = data.get("campaign_worker", "")
    rows = [["방송시간", "프로그램", "초수", "시급", "근무자"]]
    for i in range(max(len(camp), 8)):
        r = camp[i] if i < len(camp) else {}
        has = i < len(camp)
        rows.append([
            r.get("time", ""), _wrap_cell(r.get("program", ""), font, size=8),
            _fmt_dur(r.get("duration")), r.get("grade", ""),
            worker if has else "",
        ])
    _table(rows, [28 * mm, W - 28 * mm - 22 * mm - 18 * mm - 24 * mm, 22 * mm, 18 * mm, 24 * mm])

    # ── 5. 재난피해 사전예방 프로그램 송출내역 (본사 포함) ──
    _section_title("재난피해 사전예방 프로그램 송출내역 (본사 포함)")
    dis = data["disaster"]
    rows = [["방송시간", "프로그램", "초수", "근무자"]]
    for i in range(max(len(dis), 6)):
        r = dis[i] if i < len(dis) else {}
        has = i < len(dis)
        rows.append([
            r.get("time", ""), _wrap_cell(r.get("program", ""), font, size=8),
            _fmt_dur(r.get("duration")), worker if has else "",
        ])
    _table(rows, [28 * mm, W - 28 * mm - 22 * mm - 24 * mm, 22 * mm, 24 * mm])

    # ── Footer ──
    story.append(Spacer(1, 5 * mm))
    story.append(Paragraph(
        f"생성일시: {datetime.now().strftime('%Y-%m-%d %H:%M')}",
        ParagraphStyle("ft", fontName=font, fontSize=8, alignment=TA_RIGHT, textColor=colors.gray),
    ))

    doc.build(story)
    return out_path
