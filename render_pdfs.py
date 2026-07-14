"""저장 파일(PDF) 예시를 생성하고 첫 페이지를 PNG로 렌더링."""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "server"))
os.chdir(os.path.join(os.path.dirname(os.path.abspath(__file__)), "server"))
import fitz  # PyMuPDF
from routers.settings import get_settings
from routers.report import (_parse_all_for_date, _prepare_monthly_data,
                            _gather_subtitle_campaign)
from services.pdf_generator import (generate_daily_pdf, generate_monthly_pdf,
                                    generate_subtitle_campaign_pdf)

OUT = "/home/young/code/proj1/manual_shots"
DATE = "2026-07-02"
settings = get_settings()


def render(pdf_path, name, pages=1):
    doc = fitz.open(pdf_path)
    page = doc[0]
    pix = page.get_pixmap(matrix=fitz.Matrix(2, 2))  # 2배 해상도
    pix.save(f"{OUT}/{name}.png")
    doc.close()
    print("rendered", name)


# 1) 방송 운행표 PDF
items = _parse_all_for_date(DATE)
p = generate_daily_pdf(date=DATE, items=items, settings=settings)
render(p, "sav_daily_pdf")

# 2) 소재별 월 리포트 PDF (무등산(광주호))
try:
    days, adv, st, disp, fn = _prepare_monthly_data("무등산(광주호)", 2026, 7, None)
    p = generate_monthly_pdf(item_name=disp, year=2026, month=7, days=days,
                             advertiser=adv, settings=st)
    render(p, "sav_monthly_pdf")
except Exception as e:
    print("monthly pdf err:", e)

# 3) 흘림자막·공익·재난 PDF
try:
    data = _gather_subtitle_campaign(DATE)
    p = generate_subtitle_campaign_pdf(data)
    render(p, "sav_subtitle_pdf")
except Exception as e:
    print("subtitle pdf err:", e)

print("DONE")
