"""
Settings router — manage app_settings stored in apst.db.
GET  /api/settings          → return all key-value pairs
PUT  /api/settings          → update one or more keys
"""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from database import get_apst_conn
from config import SETTINGS_KEYS

router = APIRouter(prefix="/api/settings", tags=["settings"])


class SettingsUpdate(BaseModel):
    apst_dir:        str | None = None
    apst_suffix:     str | None = None
    ddr1_dir:        str | None = None
    cml_path:        str | None = None
    logo_path:       str | None = None
    seal_path:       str | None = None
    ceo_name:        str | None = None
    company_name:    str | None = None
    company_short:   str | None = None
    worker_id:       str | None = None
    worker_password: str | None = None
    ftp_host:        str | None = None
    ftp_port:        str | None = None
    ftp_user:        str | None = None
    ftp_password:    str | None = None
    ftp_fetch_time:  str | None = None
    allowed_ip_ranges: str | None = None
    gongik_include_keywords: str | None = None
    jaenan_include_keywords: str | None = None
    gongik_jaenan_exclude_keywords: str | None = None


@router.get("")
def get_settings() -> dict:
    """현재 환경설정 전체 조회."""
    with get_apst_conn() as conn:
        rows = conn.execute("SELECT key, value FROM app_settings").fetchall()
    return {r["key"]: r["value"] for r in rows}


@router.put("")
def update_settings(body: SettingsUpdate) -> dict:
    """환경설정 저장. 전달된 키만 업데이트."""
    updates = {k: v for k, v in body.model_dump().items() if v is not None}
    if not updates:
        raise HTTPException(status_code=400, detail="변경할 설정값이 없습니다.")

    invalid = [k for k in updates if k not in SETTINGS_KEYS]
    if invalid:
        raise HTTPException(status_code=400, detail=f"알 수 없는 설정 키: {invalid}")

    with get_apst_conn() as conn:
        for key, value in updates.items():
            conn.execute(
                "INSERT OR REPLACE INTO app_settings (key, value) VALUES (?, ?)",
                (key, value),
            )
    return {"message": "설정이 저장되었습니다.", "updated": list(updates.keys())}
