"""
MS Word(.docx) generator — 송출내역 출력 메뉴의 각 보고서를 Word로 저장.
PDF(pdf_generator.py)와 동일한 데이터를 사용해 표 중심으로 생성한다.
"""

import calendar
from datetime import datetime, date as date_type

from docx import Document
from docx.shared import Pt, RGBColor, Mm
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.enum.table import WD_TABLE_ALIGNMENT, WD_ROW_HEIGHT_RULE, WD_ALIGN_VERTICAL
from docx.oxml import OxmlElement
from docx.oxml.ns import qn

from config import (
    REPORT_MONTHLY_DIR, REPORT_DAILY_DIR, REPORT_SUMMARY_DIR, REPORT_SUBTITLE_DIR,
)

_KO_FONT = "Malgun Gothic"
_DAY_OF_WEEK_KO = ["월", "화", "수", "목", "금", "토", "일"]


# ── 공통 헬퍼 ────────────────────────────────────────────────────────────────

def _new_doc() -> Document:
    """한글 폰트가 적용된 새 문서."""
    doc = Document()
    style = doc.styles["Normal"]
    style.font.name = _KO_FONT
    style.font.size = Pt(10)
    rpr = style.element.get_or_add_rPr()
    rfonts = rpr.get_or_add_rFonts()
    rfonts.set(qn("w:eastAsia"), _KO_FONT)
    # Word 기본 스타일의 문단 간격/줄간격(보통 8pt·1.08배)을 0으로 낮춘다.
    # 그대로 두면 표의 행(문단)마다 여분 간격이 누적되어, PDF에서는 한 페이지에
    # 들어가는 표(월 31행 등)가 Word에서는 여러 페이지로 넘어간다.
    pf = style.paragraph_format
    pf.space_before = Pt(0)
    pf.space_after = Pt(0)
    pf.line_spacing = 1.0
    return doc


def _title(doc: Document, text: str, size: int = 16):
    p = doc.add_paragraph()
    p.paragraph_format.space_after = Pt(6)
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    run = p.add_run(text)
    run.bold = True
    run.font.size = Pt(size)
    run.font.name = _KO_FONT
    run._element.rPr.rFonts.set(qn("w:eastAsia"), _KO_FONT)
    return p


def _set_cell(cell, text, bold=False, align="center", size=9):
    p = cell.paragraphs[0]
    # 셀에 남아있는 run 제거 후 새로 작성 (앞쪽 빈 run 방지)
    for _r in list(p.runs):
        _r._element.getparent().remove(_r._element)
    p.alignment = {
        "center": WD_ALIGN_PARAGRAPH.CENTER,
        "left":   WD_ALIGN_PARAGRAPH.LEFT,
        "right":  WD_ALIGN_PARAGRAPH.RIGHT,
    }.get(align, WD_ALIGN_PARAGRAPH.CENTER)
    run = p.add_run("" if text is None else str(text))
    run.font.name = _KO_FONT
    run._element.rPr.rFonts.set(qn("w:eastAsia"), _KO_FONT)
    run.font.size = Pt(size)
    if bold:
        run.bold = True
    return cell


def _set_page(doc: Document, margin_mm: int = 15):
    """
    A4 페이지 + PDF와 동일한 여백으로 설정. PDF 쪽 col_w(mm) 값을 그대로 재사용할 수
    있도록 여백을 맞춰, 표 폭 비율이 PDF와 일치하게 한다.
    """
    section = doc.sections[0]
    section.page_width = Mm(210)
    section.page_height = Mm(297)
    section.left_margin = Mm(margin_mm)
    section.right_margin = Mm(margin_mm)
    section.top_margin = Mm(margin_mm)
    section.bottom_margin = Mm(margin_mm)


def _set_col_widths(table, widths_mm: list[float]):
    """
    표의 열 폭을 PDF와 동일한 비율(mm)로 고정한다.
    Word의 고정(fixed) 레이아웃에서 실제 열 폭은 각 셀의 tcW가 아니라 표의
    tblGrid(gridCol) 값으로 결정되므로, 둘 다 갱신해야 한다. tblGrid만 빠뜨리면
    표마다 렌더링 폭이 달라지거나(표 간 폭 불일치), 의도한 폭보다 좁게 그려져
    텍스트가 줄바꿈되는 문제가 생긴다.
    """
    table.autofit = False
    table.allow_autofit = False
    widths = [Mm(w) for w in widths_mm]

    for row in table.rows:
        for idx, w in enumerate(widths):
            if idx < len(row.cells):
                row.cells[idx].width = w

    tblGrid = table._tbl.find(qn("w:tblGrid"))
    if tblGrid is not None:
        grid_cols = tblGrid.findall(qn("w:gridCol"))
        for gc, w in zip(grid_cols, widths):
            gc.set(qn("w:w"), str(int(w.twips)))


def _shade_row(row, hex_color: str):
    """표 행 전체 셀에 배경색(음영) 적용."""
    for cell in row.cells:
        tcPr = cell._tc.get_or_add_tcPr()
        old = tcPr.find(qn("w:shd"))
        if old is not None:
            tcPr.remove(old)
        shd = OxmlElement("w:shd")
        shd.set(qn("w:val"), "clear")
        shd.set(qn("w:color"), "auto")
        shd.set(qn("w:fill"), hex_color)
        tcPr.append(shd)


def _thick_border(row, side: str = "top", size: int = 18, color: str = "3A3A3A"):
    """행의 지정 변(top/bottom)에 굵은 테두리 적용. size 단위: 1/8 pt."""
    for cell in row.cells:
        tcPr = cell._tc.get_or_add_tcPr()
        borders = tcPr.find(qn("w:tcBorders"))
        if borders is None:
            borders = OxmlElement("w:tcBorders")
            tcPr.append(borders)
        old = borders.find(qn(f"w:{side}"))
        if old is not None:
            borders.remove(old)
        el = OxmlElement(f"w:{side}")
        el.set(qn("w:val"), "single")
        el.set(qn("w:sz"), str(size))
        el.set(qn("w:space"), "0")
        el.set(qn("w:color"), color)
        borders.append(el)


def _thick_top_border(row, size: int = 18, color: str = "3A3A3A"):
    _thick_border(row, "top", size, color)


def _grid_table(doc: Document, headers: list[str]):
    """머리글 행이 있는 격자 표 생성 (좌측 정렬 — 여러 표의 좌측 여백을 일치시킴)."""
    table = doc.add_table(rows=1, cols=len(headers))
    table.style = "Table Grid"
    table.alignment = WD_TABLE_ALIGNMENT.LEFT
    for i, h in enumerate(headers):
        _set_cell(table.rows[0].cells[i], h, bold=True)
    return table


def _compact_table(table, row_h_mm: float = 5.0, exact: bool = True):
    """
    표를 조밀하게 만든다: 셀 상하 여백 0, 셀 안쪽 여백 최소, 행 높이 고정.
    Word 기본 행 높이가 커서 긴 표(월 31행 등)가 여러 페이지로 넘어가는 것을 막는다.
    """
    tblPr = table._tbl.tblPr
    # 셀 안쪽 여백(상/하 0, 좌/우 최소)
    old = tblPr.find(qn("w:tblCellMar"))
    if old is not None:
        tblPr.remove(old)
    mar = OxmlElement("w:tblCellMar")
    for side, val in (("top", 0), ("bottom", 0), ("left", 40), ("right", 40)):
        el = OxmlElement(f"w:{side}")
        el.set(qn("w:w"), str(val))
        el.set(qn("w:type"), "dxa")
        mar.append(el)
    tblPr.append(mar)

    rule = WD_ROW_HEIGHT_RULE.EXACTLY if exact else WD_ROW_HEIGHT_RULE.AT_LEAST
    for row in table.rows:
        row.height = Mm(row_h_mm)
        row.height_rule = rule


def _estimate_wrap_lines(text: str, col_mm: float = 76.0,
                         font_pt: float = 8.0, cell_pad_mm: float = 1.4) -> int:
    """
    Word는 렌더링 높이를 직접 잴 수 없어, 셀 폭과 글자 수로 줄바꿈 줄 수를 추정한다.
    (숫자·공백 위주 문자열 기준: 한 글자 폭 ≈ 0.5em)
    """
    import math
    if not text:
        return 1
    usable = max(1.0, col_mm - cell_pad_mm)          # 셀 좌우 안쪽 여백 제외
    char_w = font_pt * 0.5 / 72.0 * 25.4             # 0.5em 을 mm 로 환산
    per_line = max(1, int(usable / char_w))
    return max(1, math.ceil(len(text) / per_line))


def _small_gap(doc: Document, pt: float = 4):
    """표 사이 작은 간격 (빈 문단은 한 줄 높이를 차지해 페이지가 넘치므로 대체)."""
    p = doc.add_paragraph()
    p.paragraph_format.space_before = Pt(0)
    p.paragraph_format.space_after = Pt(0)
    p.paragraph_format.line_spacing = 1.0
    for run in p.runs:
        run.font.size = Pt(pt)
    # 빈 문단 자체의 폰트 크기를 줄여 높이 최소화
    p.add_run("").font.size = Pt(pt)
    return p


def _footer_note(doc: Document, text: str):
    p = doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.RIGHT
    run = p.add_run(text)
    run.font.size = Pt(8)
    run.font.color.rgb = RGBColor(0x88, 0x88, 0x88)


# ── F-04 : 소재별 월 리포트 ──────────────────────────────────────────────────

def generate_monthly_docx(item_name, year, month, days, advertiser, settings) -> str:
    company = (settings.get("company_name") or "광주문화방송").strip() or "광주문화방송"
    short = (settings.get("company_short") or "광주MBC").strip() or "광주MBC"
    doc = _new_doc()
    _set_page(doc, 12)   # PDF와 동일하게 상·하·좌·우 여백 12mm
    _title(doc, f"{short} 방송홍보 SB송출 현황", 18)

    last_day = calendar.monthrange(year, month)[1]
    wd_s = _DAY_OF_WEEK_KO[date_type(year, month, 1).weekday()]
    wd_e = _DAY_OF_WEEK_KO[date_type(year, month, last_day).weekday()]
    period = f"{year}.{month}.1({wd_s})~{year}.{month}.{last_day}({wd_e})"

    # 정보 표 (데이터 표와 동일하게 좌측 정렬 — 두 표의 좌측 여백을 맞춤)
    info = doc.add_table(rows=4, cols=4)
    info.style = "Table Grid"
    # 좌우 여백을 동일하게: 표를 가운데 정렬(표 폭 170mm < 본문 폭이라 좌우 균등 배분)
    info.alignment = WD_TABLE_ALIGNMENT.CENTER
    note = advertiser.get("note") or "송출시간은 방송사 상황에 따라 변동될 수 있음"
    rows = [
        ["회 사 명", company, "사업자등록번호", "410-81-06350"],
        ["송출 내용", item_name, "대 표 이 사", settings.get("ceo_name", "")],
        ["송출 매체", advertiser.get("broadcast_medium", "TV"), "업 태·업 종", "서비스·방송"],
        ["송출 기간", period, "비  고", note],
    ]
    for r, cells in enumerate(rows):
        for c, val in enumerate(cells):
            _set_cell(info.rows[r].cells[c], val, bold=(c in (0, 2)),
                      align="left" if c in (1, 3) else "center", size=8)
    # 비고 칸(마지막 열)에 여유를 더 주기 위해 라벨 열 폭을 조금씩 덜어 이동
    # (합계는 아래 데이터 표와 동일하게 170mm로 맞춰 두 표의 전체 폭을 일치시킴)
    _set_col_widths(info, [18, 55, 24, 73])
    _compact_table(info, row_h_mm=6.0, exact=False)   # 비고 줄바꿈 대비 AT_LEAST

    _small_gap(doc)

    # 데이터 표
    table = _grid_table(doc, ["일 시", "요일", "횟수", "T V", "RADIO-AM", "RADIO-FM"])
    table.alignment = WD_TABLE_ALIGNMENT.CENTER   # 정보표와 함께 가운데 정렬(좌우 여백 동일)
    days_map = {d["date"]: d for d in days}
    total = 0
    extra_lines = 0   # TV 시간 줄바꿈으로 늘어나는 총 추가 줄 수(행 높이 계산용)
    for day_num in range(1, last_day + 1):
        d = date_type(year, month, day_num)
        ds = d.strftime("%Y-%m-%d")
        wd = _DAY_OF_WEEK_KO[d.weekday()]
        info_d = days_map.get(ds)
        if info_d:
            cnt = info_d["count"]
            times = " ".join(_hhmm(t) for t in info_d["times"])
            total += cnt
        else:
            cnt, times = 0, ""
        extra_lines += _estimate_wrap_lines(times) - 1
        cells = table.add_row().cells
        vals = [f"{year % 100}. {month}. {day_num}", wd, str(cnt) if cnt else "", times, "-", "-"]
        for i, v in enumerate(vals):
            # PDF처럼 모든 칸 가운데 정렬 (TV 시간 포함) + 세로 가운데(여러 줄일 때 정렬)
            _set_cell(cells[i], v, align="center", size=8)
            cells[i].vertical_alignment = WD_ALIGN_VERTICAL.CENTER

    cells = table.add_row().cells
    for i, v in enumerate(["총 계", f"{last_day} 일", f"{total} 회", f"총 {total} 회", "-", "-"]):
        _set_cell(cells[i], v, bold=True, size=8)
    _set_col_widths(table, [24, 12, 14, 76, 22, 22])

    # ── 행 높이 자동 계산 (PDF처럼 위/아래 여백 균형 + 페이지 채우기) ──
    # 가용 세로 높이에서 제목·정보표·간격·푸터(추정 고정분)를 뺀 나머지를
    # 데이터 표의 각 행에 고르게 나눠, 내용이 적어도 표가 페이지를 채우게 한다.
    # 줄바꿈으로 늘어나는 행(extra_lines)만큼 높이를 먼저 확보해 넘침을 막는다.
    num_rows = last_day + 2                 # 머리글 + 일자(last_day) + 총계
    usable_h = 297.0 - 24.0                 # A4 높이 - 상하 여백(12+12)
    # 제목+정보표+간격+푸터의 실제 렌더 높이는 서버에서 정확히 잴 수 없어,
    # 행 높이 6.6mm가 2페이지로 넘친(=푸터 밀림) 실측을 근거로 오버헤드를 넉넉히
    # 잡아 한 페이지를 보장한다. (row_h ≈ 5.9mm 수준으로 수렴)
    overhead_mm = 76.0
    line_h_mm = 3.4                         # 8pt 한 줄 높이(추정)
    avail_table = usable_h - overhead_mm - extra_lines * line_h_mm
    row_h = avail_table / num_rows
    row_h = max(4.8, min(6.2, row_h))       # 최소=조밀, 최대=넘침 방지 상한
    # AT_LEAST: 계산 높이로 채우되, 줄바꿈 행은 잘리지 않고 더 늘어남
    _compact_table(table, row_h_mm=row_h, exact=False)

    _small_gap(doc)
    # 푸터: 확인 문구(좌, 10pt)와 회사명(우, 11pt)을 한 줄에 배치.
    # 테두리 없는 2칸 표로 좌·우 정렬을 한 줄에 맞춘다(폰트 크기는 각각 유지).
    ftbl = doc.add_table(rows=1, cols=2)
    ftbl.alignment = WD_TABLE_ALIGNMENT.CENTER
    lc, rc = ftbl.rows[0].cells
    _set_cell(lc, "위와 같이 방송 송출 완료하였음을 확인함", align="left", size=10)
    _set_cell(rc, f"{company}(주)", bold=True, align="right", size=11)
    lc.vertical_alignment = WD_ALIGN_VERTICAL.CENTER
    rc.vertical_alignment = WD_ALIGN_VERTICAL.CENTER
    _set_col_widths(ftbl, [100, 70])   # 합계 170mm (위 표들과 동일 폭)

    safe_item = str(item_name).replace("/", "_").replace("\\", "_")[:80]
    out = str(REPORT_MONTHLY_DIR / f"SB송출현황_{safe_item}_{year}{month:02d}.docx")
    doc.save(out)
    return out


def _hhmm(time_str: str) -> str:
    """'HH:MM:SS' → 4자리 방송 HHMM (00~04시는 +24h)."""
    p = time_str.split(":")
    if len(p) < 2:
        return time_str
    h, m = int(p[0]), int(p[1])
    if h < 5:
        h += 24
    return f"{h:02d}{m:02d}"


# ── F-06 : 방송 운행표 ───────────────────────────────────────────────────────

def generate_daily_docx(date, items, settings) -> str:
    doc = _new_doc()
    _set_page(doc, 15)
    _title(doc, f"방송 운행표  —  {date}", 14)

    if not items:
        doc.add_paragraph("해당 날짜의 SB 송출 내역이 없습니다.")
    else:
        _SKY   = "DCE6F1"   # 프로그램 행 음영
        _GREEN = "E2EFDA"   # 광고/광고그룹 행 음영

        def _is_end_notice(prog):
            return "방송 종료" in (prog or "") or "방송종료" in (prog or "")

        table = _grid_table(doc, ["방송시작시간", "프로그램명", "소재종류", "SB 소재 제목"])
        for i, r in enumerate(items):
            lbl = r.get("content_type_label", "")
            prog = r.get("program_block", "")
            is_ct = lbl == "이어서"   # '이어서' 행 굵게
            row = table.add_row()
            cells = row.cells
            _set_cell(cells[0], r.get("broadcast_time_display") or r["broadcast_time"], bold=is_ct)
            _set_cell(cells[1], prog, bold=is_ct)
            _set_cell(cells[2], lbl, bold=is_ct)
            _set_cell(cells[3], r.get("item_name_raw", ""), bold=is_ct, align="left")
            if is_ct:
                _thick_top_border(row)          # 프로그램 그룹 시작 → 위쪽 굵은 구분선
            elif lbl == "프로그램" and "방송순서" not in (prog or ""):
                # 첫부분 '방송순서 안내'는 프로그램이어도 하늘색 음영 제외
                _shade_row(row, _SKY)
            elif lbl in ("광고", "광고그룹"):
                _shade_row(row, _GREEN)
            # 방송종료 안내 시작 행 → 위쪽 굵은 구분선
            if not is_ct and _is_end_notice(prog) \
                    and not (i > 0 and _is_end_notice(items[i - 1].get("program_block", ""))):
                _thick_top_border(row)
        _set_col_widths(table, [28, 48, 22, 82])

        # 표 외곽선 굵게: 맨 윗줄(헤더 위) / 헤더(제목) 아래 / 맨 밑줄
        _thick_border(table.rows[0], "top")
        _thick_border(table.rows[0], "bottom")
        _thick_border(table.rows[-1], "bottom")

    _footer_note(doc, f"총 {len(items)}건 | 생성일시: {datetime.now().strftime('%Y-%m-%d %H:%M')}")

    out = str(REPORT_DAILY_DIR / f"방송운행표_{date.replace('-', '')}.docx")
    doc.save(out)
    return out


# ── 일일 운행표 / 일일 ID 운행표 ──────────────────────────────────────────────

def generate_daily_summary_docx(date, type_label, items) -> str:
    doc = _new_doc()
    _set_page(doc, 15)
    title = "일일 ID 운행표" if type_label == "ID" else "일일 운행표"
    _title(doc, f"{title}  —  {date}", 14)

    if not items:
        doc.add_paragraph("해당 날짜의 송출 내역이 없습니다.")
    else:
        table = _grid_table(doc, ["소재명", "총횟수", "SA", "A", "B", "C"])
        for r in items:
            cells = table.add_row().cells
            _set_cell(cells[0], r["item_name"], align="left")
            _set_cell(cells[1], f"{r['total_count']}회")
            _set_cell(cells[2], r.get("sa") or 0)
            _set_cell(cells[3], r.get("a") or 0)
            _set_cell(cells[4], r.get("b") or 0)
            _set_cell(cells[5], r.get("c") or 0)
        _set_col_widths(table, [70, 22, 22, 22, 22, 22])

    total = sum(r["total_count"] for r in items)
    _footer_note(doc, f"총 {total}회 | 생성일시: {datetime.now().strftime('%Y-%m-%d %H:%M')}")

    prefix = "일일ID운행표" if type_label == "ID" else "일일운행표"
    out = str(REPORT_SUMMARY_DIR / f"{prefix}_{date.replace('-', '')}.docx")
    doc.save(out)
    return out


# ── 흘림자막·공익·재난 송출내역 ────────────────────────────────────────────────

def _fmt_dur(sec) -> str:
    if not sec:
        return ""
    sec = int(sec)
    if sec < 60:
        return f'{sec}"'
    return f"{sec // 60}'{sec % 60:02d}\""


def _hhmm_ko(t: str) -> str:
    if not t:
        return ""
    p = t.split(":")
    try:
        return f"{int(p[0]):02d}시{int(p[1]):02d}분"
    except (ValueError, IndexError):
        return t


def generate_subtitle_campaign_docx(data) -> str:
    doc = _new_doc()
    _set_page(doc, 12)
    date = data["date"]
    _title(doc, "□ 흘림자막 및 공익광고/재난피해 사전예방 송출내역 □", 15)
    try:
        d = datetime.strptime(date, "%Y-%m-%d")
        wd = _DAY_OF_WEEK_KO[d.weekday()]
        _title(doc, f"{d.year}년 {d.month}월 {d.day}일 ({wd}) (00:00 ~ 24:00)", 12)
    except ValueError:
        _title(doc, f"{date} (00:00 ~ 24:00)", 12)

    def _section(name, headers, rows, widths_mm):
        doc.add_paragraph().add_run(f"□ {name}").bold = True
        t = _grid_table(doc, headers)
        for row in rows:
            cells = t.add_row().cells
            for i, v in enumerate(row):
                _set_cell(cells[i], v, align="left" if i == 1 else "center")
        _set_col_widths(t, widths_mm)
        doc.add_paragraph()

    # 1. UHD방송홍보 (영상/자막)
    uhd_v, uhd_s = data["uhd_video"], data["uhd_sub"]
    rows = []
    for i in range(max(len(uhd_v), len(uhd_s), 1)):
        v = uhd_v[i] if i < len(uhd_v) else {}
        s = uhd_s[i] if i < len(uhd_s) else {}
        rows.append([_hhmm_ko(v.get("time", "")), v.get("program", ""),
                     _hhmm_ko(s.get("time", "")), s.get("program", "")])
    _section("UHD방송홍보", ["송출시간(영상)", "프로그램", "송출시간(자막)", "프로그램"], rows,
              [30, 63, 30, 63])

    # 2. TV직접수신 (2쌍)
    tv = data["tv_direct"]
    rows = []
    for i in range(max((len(tv) + 1) // 2, 1)):
        a = tv[2 * i] if 2 * i < len(tv) else {}
        b = tv[2 * i + 1] if 2 * i + 1 < len(tv) else {}
        rows.append([_hhmm_ko(a.get("time", "")), a.get("program", ""),
                     _hhmm_ko(b.get("time", "")), b.get("program", "")])
    _section("TV직접수신", ["송출시간(자막)", "프로그램", "송출시간(자막)", "프로그램"], rows,
              [30, 63, 30, 63])

    # 3. 시청자의견
    vo = data["viewer_opinion"]
    rows = [[_hhmm_ko(r.get("time", "")), r.get("program", "")]
            for r in (vo or [{}])]
    _section("시청자의견 (주1회 목요일)", ["송출시간(자막)", "프로그램"], rows,
              [35, 151])

    # 4. 공익광고
    worker = data.get("campaign_worker", "")
    camp = data["campaign"]
    rows = [[r.get("time", ""), r.get("program", ""), _fmt_dur(r.get("duration")),
             r.get("grade", ""), worker] for r in camp]
    if not rows:
        rows = [["", "", "", "", ""]]
    _section("공익광고 송출내역 (본사 포함)",
             ["방송시간", "프로그램", "초수", "시급", "근무자"], rows,
              [28, 94, 22, 18, 24])

    # 5. 재난피해
    dis = data["disaster"]
    rows = [[r.get("time", ""), r.get("program", ""), _fmt_dur(r.get("duration")), worker]
            for r in dis]
    if not rows:
        rows = [["", "", "", ""]]
    _section("재난피해 사전예방 프로그램 송출내역 (본사 포함)",
             ["방송시간", "프로그램", "초수", "근무자"], rows,
              [28, 112, 22, 24])

    _footer_note(doc, f"생성일시: {datetime.now().strftime('%Y-%m-%d %H:%M')}")

    out = str(REPORT_SUBTITLE_DIR / f"흘림자막공익재난송출내역_{date.replace('-', '')}.docx")
    doc.save(out)
    return out
