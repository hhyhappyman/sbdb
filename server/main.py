"""
FastAPI application entry point.
Run: uvicorn main:app --reload --port 8000
"""

import ipaddress
from pathlib import Path
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, FileResponse
from fastapi.staticfiles import StaticFiles

from config import CORS_ORIGINS
from database import init_db
from services.file_watcher import stop_watching, auto_start_if_enabled
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
    # FTP 자동 가져오기 스케줄러 시작
    start_scheduler()
    # 환경설정에서 폴더 감시가 켜져 있던 경우(watcher_enabled='1') 재시작 시 자동 재개
    auto_start_if_enabled()


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


# ── 프론트엔드(React 빌드) 서빙 ───────────────────────────────────────────────
# 배포 환경에서는 Vite 개발서버 없이 uvicorn 하나로 화면+API를 함께 제공한다.
# client/dist 가 있으면 정적 파일로 마운트하고, SPA 라우팅을 위해 알 수 없는
# 경로(파일이 아닌)는 index.html로 폴백한다. (반드시 /api 라우터 등록 이후에 둘 것)
_DIST_DIR = Path(__file__).parent.parent / "client" / "dist"
if _DIST_DIR.is_dir():
    _INDEX = _DIST_DIR / "index.html"

    # 정적 에셋(js/css/img 등)
    app.mount("/assets", StaticFiles(directory=str(_DIST_DIR / "assets")), name="assets")

    @app.get("/{full_path:path}")
    def spa_fallback(full_path: str):
        # /api 경로는 여기서 처리하지 않음 (정상 404가 나도록)
        if full_path.startswith("api/"):
            return JSONResponse({"detail": "Not Found"}, status_code=404)
        # 실제 파일이 있으면 그 파일을, 없으면 SPA 진입점(index.html)을 반환
        candidate = _DIST_DIR / full_path
        if full_path and candidate.is_file():
            return FileResponse(str(candidate))
        return FileResponse(str(_INDEX))
