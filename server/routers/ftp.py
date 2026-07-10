"""
FTP router — 송출 파일(apst/ddr1_log/cml)을 FTP 서버에서 가져와 적재.
POST /api/ftp/fetch?date=YYYY-MM-DD  → 지정 날짜 파일 가져오기 + 적재
POST /api/ftp/fetch-yesterday        → 전날 파일 가져오기 (즉시 실행)
GET  /api/ftp/test                   → FTP 접속 테스트
"""

from fastapi import APIRouter, Query, HTTPException

from services.ftp_fetcher import fetch_and_ingest, fetch_yesterday, _download_date, _get_conf

router = APIRouter(prefix="/api/ftp", tags=["ftp"])


@router.get("/test")
def ftp_test() -> dict:
    """FTP 접속 및 홈 폴더 하위 폴더 확인."""
    import ftplib
    from config import FTP_PORT_DEFAULT, FTP_SUBDIRS
    conf = _get_conf()
    host = (conf.get("ftp_host") or "").strip()
    if not host:
        raise HTTPException(status_code=400, detail="환경설정에서 FTP 서버 주소를 먼저 입력하세요.")
    try:
        ftp = ftplib.FTP()
        ftp.connect(host, int(conf.get("ftp_port") or FTP_PORT_DEFAULT or "21"), timeout=15)
        ftp.login(conf.get("ftp_user") or "", conf.get("ftp_password") or "")
        home = ftp.pwd()
        dirs = ftp.nlst()
        ftp.quit()
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"FTP 접속 실패: {e}")
    found = [s for s in FTP_SUBDIRS.values() if s in [d.rsplit('/', 1)[-1] for d in dirs]]
    return {"message": "FTP 접속 성공", "home": home, "folders_found": found}


@router.post("/fetch")
def ftp_fetch(date: str = Query(..., description="YYYY-MM-DD")) -> dict:
    """지정한 날짜의 파일을 FTP에서 가져와 적재."""
    return fetch_and_ingest(date)


@router.post("/fetch-yesterday")
def ftp_fetch_yesterday() -> dict:
    """전날 파일을 지금 즉시 가져와 적재."""
    return fetch_yesterday()
