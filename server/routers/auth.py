"""
Auth router — 관리자 로그인/로그아웃
POST /api/auth/login   → 아이디+비밀번호 확인
POST /api/auth/logout  → (프론트엔드 상태 초기화용, 서버는 stateless)
PUT  /api/auth/password → 관리자 비밀번호 변경
"""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from database import get_apst_conn
from config import ADMIN_ID

router = APIRouter(prefix="/api/auth", tags=["auth"])


class LoginRequest(BaseModel):
    username: str
    password: str


class PasswordChange(BaseModel):
    current_password: str
    new_password: str


def _get_admin_password() -> str:
    """DB에서 현재 관리자 비밀번호 조회."""
    with get_apst_conn() as conn:
        row = conn.execute(
            "SELECT value FROM app_settings WHERE key = 'admin_password'"
        ).fetchone()
    return row["value"] if row else "admin"


@router.post("/login")
def login(body: LoginRequest) -> dict:
    """관리자 로그인. 아이디는 'admin' 고정."""
    if body.username != ADMIN_ID:
        raise HTTPException(status_code=401, detail="아이디 또는 비밀번호가 올바르지 않습니다.")

    admin_pw = _get_admin_password()
    if body.password != admin_pw:
        raise HTTPException(status_code=401, detail="아이디 또는 비밀번호가 올바르지 않습니다.")

    return {"success": True, "message": "관리자 로그인 성공"}


@router.post("/logout")
def logout() -> dict:
    """로그아웃 (서버는 stateless — 프론트엔드 상태만 초기화)."""
    return {"success": True, "message": "로그아웃 되었습니다."}


def _get_setting(key: str, default: str = "") -> str:
    """app_settings에서 값 조회."""
    with get_apst_conn() as conn:
        row = conn.execute(
            "SELECT value FROM app_settings WHERE key = ?", (key,)
        ).fetchone()
    return row["value"] if row and row["value"] else default


@router.post("/worker-login")
def worker_login(body: LoginRequest) -> dict:
    """근무자 로그인. 아이디/비밀번호는 환경설정(app_settings)에서 관리."""
    from config import WORKER_ID_DEFAULT, WORKER_PASSWORD_DEFAULT

    worker_id = _get_setting("worker_id", WORKER_ID_DEFAULT)
    worker_pw = _get_setting("worker_password", WORKER_PASSWORD_DEFAULT)

    if body.username != worker_id or body.password != worker_pw:
        raise HTTPException(status_code=401, detail="아이디 또는 비밀번호가 올바르지 않습니다.")

    return {"success": True, "message": "근무자 로그인 성공"}


@router.put("/password")
def change_password(body: PasswordChange) -> dict:
    """관리자 비밀번호 변경."""
    admin_pw = _get_admin_password()

    if body.current_password != admin_pw:
        raise HTTPException(status_code=401, detail="현재 비밀번호가 올바르지 않습니다.")

    if not body.new_password or len(body.new_password) < 4:
        raise HTTPException(status_code=400, detail="새 비밀번호는 4자 이상이어야 합니다.")

    with get_apst_conn() as conn:
        conn.execute(
            "UPDATE app_settings SET value = ? WHERE key = 'admin_password'",
            (body.new_password,)
        )

    return {"success": True, "message": "비밀번호가 변경되었습니다."}
