"""매뉴얼 보강 캡처 — 리포트 서브탭, 소재 목록 모달, 수동입력 종류."""
import os
from playwright.sync_api import sync_playwright

OUT = "/home/young/code/proj1/manual_shots"
BASE = "http://localhost:5173"
DATE = "2026-07-02"
os.makedirs(OUT, exist_ok=True)
WORKER_ID, WORKER_PW = "user", "user2450"


def shot(page, name, wait=1500):
    page.wait_for_timeout(wait)
    page.screenshot(path=f"{OUT}/{name}.png")
    print("saved", name)


def click_tab(page, label):
    page.locator(f".ant-tabs-tab:has-text('{label}')").first.click()
    page.wait_for_timeout(1200)


def set_date_in_active(page, value):
    """활성 탭의 첫 DatePicker에 날짜 입력."""
    inp = page.locator(".ant-tabs-tabpane-active .ant-picker input").first
    inp.click()
    inp.fill(value)
    page.keyboard.press("Enter")
    page.wait_for_timeout(400)


with sync_playwright() as p:
    b = p.chromium.launch(headless=True, args=["--no-sandbox", "--disable-gpu"])
    page = b.new_page(viewport={"width": 1440, "height": 900})

    # ── 송출내역 출력: 각 서브탭 ──
    page.goto(BASE + "/report", wait_until="networkidle", timeout=30000)
    page.wait_for_timeout(1500)

    # 방송 운행표
    try:
        click_tab(page, "방송 운행표")
        set_date_in_active(page, DATE)
        page.locator(".ant-tabs-tabpane-active button:has-text('방송 운행표')").first.click()
        shot(page, "12_report_daily", wait=2500)
    except Exception as e:
        print("daily err", e); shot(page, "12_report_daily")

    # 일일 운행표
    try:
        click_tab(page, "일일 운행표")
        set_date_in_active(page, DATE)
        page.locator(".ant-tabs-tabpane-active button:has-text('조회')").first.click()
        shot(page, "13_report_daily_summary", wait=2200)
    except Exception as e:
        print("daily-summary err", e); shot(page, "13_report_daily_summary")

    # 일일 ID 운행표
    try:
        click_tab(page, "일일 ID 운행표")
        set_date_in_active(page, DATE)
        page.locator(".ant-tabs-tabpane-active button:has-text('조회')").first.click()
        shot(page, "14_report_daily_id", wait=2200)
    except Exception as e:
        print("daily-id err", e); shot(page, "14_report_daily_id")

    # 흘림자막,공익,재난 송출내역
    try:
        click_tab(page, "흘림자막")
        set_date_in_active(page, DATE)
        page.locator(".ant-tabs-tabpane-active button:has-text('조회')").first.click()
        shot(page, "15_report_subtitle", wait=2200)
    except Exception as e:
        print("subtitle err", e); shot(page, "15_report_subtitle")

    # 공익,재난 월별 송출내역
    try:
        click_tab(page, "공익,재난 월별")
        page.locator(".ant-tabs-tabpane-active button:has-text('조회')").first.click()
        shot(page, "16_report_gj_monthly", wait=2200)
    except Exception as e:
        print("gj-monthly err", e); shot(page, "16_report_gj_monthly")

    # ── 소재 목록 모달 (소재별 월 리포트 탭에서 부분검색) ──
    try:
        click_tab(page, "소재별 월 리포트")
        inp = page.locator(".ant-tabs-tabpane-active input[placeholder*='소재명']").first
        inp.fill("무등산")
        page.locator(".ant-tabs-tabpane-active button:has-text('조회')").first.click()
        page.wait_for_timeout(1500)
        shot(page, "17_item_modal", wait=800)
    except Exception as e:
        print("modal err", e); shot(page, "17_item_modal")

    # ── 근무자 로그인 → 수동입력 소재종류 드롭다운 ──
    try:
        page.goto(BASE, wait_until="networkidle", timeout=30000)
        page.wait_for_timeout(1000)
        page.locator(".ant-layout-sider button:has-text('근무자')").first.click()
        page.wait_for_timeout(700)
        page.locator(".ant-modal input").nth(0).fill(WORKER_ID)
        page.locator(".ant-modal input[type='password']").fill(WORKER_PW)
        page.locator(".ant-modal button:has-text('로그인')").click()
        page.wait_for_timeout(1800)
        page.locator(".ant-menu a:has-text('송출 수동입력')").click()
        page.wait_for_timeout(1200)
        # 소재종류 Select 열기
        page.locator(".ant-select-selector").first.click()
        page.wait_for_timeout(600)
        shot(page, "18_worker_type", wait=400)
    except Exception as e:
        print("worker type err", e)

    print("DONE2")
    b.close()
