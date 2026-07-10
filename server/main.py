"""
FastAPI application entry point.
Run: uvicorn main:app --reload --port 8000
"""

import ipaddress
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from config import CORS_ORIGINS
from database import init_db
from services.file_watcher import stop_watching
from services.ftp_fetcher import start_scheduler, stop_scheduler
from routers import (
    auth,
    settings,
    advertisers,
    ingest,
    items,
    dashboard,
    calendar,
    period,
    report,
    logs,
    manual,
    ftp,
    export,
)

# ── IP Whitelist ─────────────────────────────────────────────────────────────
# 허용 IP 대역은 환경설정(app_settings.allowed_ip_ranges)에서 관리한다.
# - 콤마 또는 줄바꿈으로 여러 대역 입력: "218.237.3.0/24, 192.168.0.0/24"
# - 단일 IP도 가능: "192.168.0.10" (자동으로 /32 처리)
# - "0.0.0.0" 또는 "0.0.0.0/0"이 포함되면 모든 IP 허용
# localhost(127.0.0.1, ::1)는 서버 자체 동작을 위해 항상 허용.

from database import get_apst_conn as _get_apst_conn
from config import ALLOWED_IP_RANGES_DEFAULT

_ALLOWED_HOSTS = {"127.0.0.1", "::1"}  # localhost는 항상 허용


def _load_allowed_networks() -> tuple[list, bool]:
    """
    환경설정에서 허용 대역을 읽어 (네트워크 목록, 전체허용여부) 반환.
    파싱 실패한 항목은 건너뛴다.
    """
    try:
        with _get_apst_conn() as conn:
            row = conn.execute(
                "SELECT value FROM app_settings WHERE key = 'allowed_ip_ranges'"
            ).fetchone()
        raw = (row["value"] if row and row["value"] else ALLOWED_IP_RANGES_DEFAULT)
    except Exception:
        raw = ALLOWED_IP_RANGES_DEFAULT

    nets = []
    for token in raw.replace("\n", ",").split(","):
        t = token.strip()
        if not t:
            continue
        if t in ("0.0.0.0", "0.0.0.0/0", "::/0"):
            return [], True   # 전체 허용
        try:
            nets.append(ipaddress.ip_network(t, strict=False))
        except ValueError:
            continue
    return nets, False


def _is_allowed(ip: str) -> bool:
    if ip in _ALLOWED_HOSTS:
        return True
    nets, allow_all = _load_allowed_networks()
    if allow_all:
        return True
    try:
        addr = ipaddress.ip_address(ip)
        return any(addr in net for net in nets)
    except ValueError:
        return False


# ── App ─────────────────────────────────────────────────────────────────────

app = FastAPI(
    title="SB 송출 대시보드 API",
    description="광주MBC SB 송출 내역 관리 시스템",
    version="1.0.0",
)

# CORS (React dev server)
app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# IP 화이트리스트 미들웨어 — CORS 미들웨어보다 먼저 등록해야 함
@app.middleware("http")
async def ip_whitelist(request: Request, call_next):
    client_ip = request.client.host
    if not _is_allowed(client_ip):
        return JSONResponse(status_code=403, content={"detail": f"접근 불가: {client_ip}"})
    return await call_next(request)


# ── Startup / Shutdown ────────────────────────────────────────────────────────

@app.on_event("startup")
def on_startup():
    init_db()
    print("[Server] DB initialized. Ready.")
    # FTP 자동 가져오기 스케줄러 시작 (폴더 실시간 감시를 대체)
    start_scheduler()


@app.on_event("shutdown")
def on_shutdown():
    stop_watching()
    stop_scheduler()
    print("[Server] Watcher/FTP scheduler stopped.")


# ── Routers ──────────────────────────────────────────────────────────────────

app.include_router(auth.router)
app.include_router(settings.router)
app.include_router(items.router)
app.include_router(advertisers.router)
app.include_router(ingest.router)
app.include_router(dashboard.router)
app.include_router(calendar.router)
app.include_router(period.router)
app.include_router(report.router)
app.include_router(logs.router)
app.include_router(manual.router)
app.include_router(ftp.router)
app.include_router(export.router)


# ── Health check ─────────────────────────────────────────────────────────────

@app.get("/api/health")
def health():
    return {"status": "ok"}
