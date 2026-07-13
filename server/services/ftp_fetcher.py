"""
FTP file fetcher — 송출 파일(apst/ddr1_log/cml)을 FTP 서버에서 가져와 적재한다.
폴더 실시간 감시(watchdog)를 대체한다.

FTP 서버 홈 폴더 밑에 apst / ddr1_log / cml 폴더가 있고, 파일명에 날짜(YYYYMMDD)가
포함되어 있다고 가정한다. 해당 날짜의 파일을 종류별 로컬 폴더로 내려받은 뒤 적재한다.
"""

import re
import time
import ftplib
import threading
from datetime import datetime, date as date_cls, timedelta
from pathlib import Path

from database import get_apst_conn
from config import FTP_SUBDIRS, FTP_PORT_DEFAULT
from services.activity_log import log_event


# ── 설정 조회 ────────────────────────────────────────────────────────────────

_CONF_KEYS = [
    "ftp_host", "ftp_port", "ftp_user", "ftp_password", "ftp_fetch_time",
    "apst_dir", "ddr1_dir", "cml_path",
]


def _get_conf() -> dict:
    ph = ",".join("?" * len(_CONF_KEYS))
    with get_apst_conn() as conn:
        rows = conn.execute(
            f"SELECT key, value FROM app_settings WHERE key IN ({ph})", _CONF_KEYS
        ).fetchall()
    return {r["key"]: r["value"] for r in rows}


def _local_dir(conf: dict, kind: str) -> str:
    return {
        "apst": conf.get("apst_dir", ""),
        "ddr1": conf.get("ddr1_dir", ""),
        "cml":  conf.get("cml_path", ""),
    }.get(kind, "")


# ── FTP 다운로드 ──────────────────────────────────────────────────────────────

def _download_date(date: str) -> dict:
    """
    FTP 홈 폴더 밑 apst/ddr1_log/cml 에서 파일명에 date(YYYYMMDD)가 포함된 파일을
    종류별 로컬 폴더로 내려받는다.
    반환: {"apst": [파일명...], "ddr1": [...], "cml": [...]}
    """
    conf = _get_conf()
    host = (conf.get("ftp_host") or "").strip()
    if not host:
        raise RuntimeError("FTP 서버 주소(ftp_host)가 설정되지 않았습니다.")
    port = int((conf.get("ftp_port") or FTP_PORT_DEFAULT or "21"))
    user = conf.get("ftp_user") or ""
    pw = conf.get("ftp_password") or ""
    date_nodash = date.replace("-", "")

    downloaded = {"apst": [], "ddr1": [], "cml": []}

    ftp = ftplib.FTP()
    ftp.connect(host, port, timeout=30)
    ftp.login(user, pw)
    try:
        home = ftp.pwd()
        for kind, subdir in FTP_SUBDIRS.items():
            local = _local_dir(conf, kind)
            if not local:
                continue
            Path(local).mkdir(parents=True, exist_ok=True)
            try:
                ftp.cwd(home)
                ftp.cwd(subdir)
            except ftplib.error_perm:
                continue  # 해당 폴더 없음
            try:
                names = ftp.nlst()
            except ftplib.error_perm:
                names = []
            for name in names:
                base = name.rsplit("/", 1)[-1]
                if date_nodash in base:
                    dest = Path(local) / base
                    with open(dest, "wb") as fh:
                        ftp.retrbinary(f"RETR {name}", fh.write)
                    downloaded[kind].append(base)
    finally:
        try:
            ftp.quit()
        except Exception:
            ftp.close()

    return downloaded


# ── 상태 기록 (daily_fetch) ──────────────────────────────────────────────────

def _set_status(date: str, status: str, message: str):
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with get_apst_conn() as conn:
        conn.execute(
            """INSERT INTO daily_fetch (broadcast_date, status, message, updated_at)
               VALUES (?,?,?,?)
               ON CONFLICT(broadcast_date)
               DO UPDATE SET status=excluded.status, message=excluded.message, updated_at=excluded.updated_at""",
            (date, status, message, now),
        )


# ── 가져오기 + 적재 ───────────────────────────────────────────────────────────

def fetch_and_ingest(date: str) -> dict:
    """FTP에서 해당 날짜 파일을 받아 적재하고 daily_fetch 상태를 기록한다."""
    from routers.ingest import ingest_date

    try:
        dl = _download_date(date)
    except Exception as e:
        _set_status(date, "error", f"FTP 오류: {e}")
        log_event("error", "ftp", f"FTP 가져오기 오류 ({date}): {e}")
        return {"date": date, "ok": False, "error": str(e)}

    # 받은 APST가 있으면 적재
    ing = ingest_date(date) if dl["apst"] else None

    # 세 파일(APST/DDR1/CML) 존재 여부로 상태 판정 — 하나라도 없으면 missing(붉은색)
    status = refresh_fetch_status(date)
    if status["ok"]:
        log_event(
            "info", "ftp",
            f"FTP 가져오기 완료 ({date}): APST {ing['apst'] if ing else 0}건, "
            f"수동 {ing['manual'] if ing else 0}건, CML {ing['cml'] if ing else 0}건",
        )
        return {"date": date, "ok": True, "downloaded": dl, "ingested": ing}

    log_event(
        "warning", "ftp",
        f"FTP 파일 일부 없음 ({date}): 없는 파일 {', '.join(status['missing_kinds'])}",
    )
    return {"date": date, "ok": False, "missing": True,
            "downloaded": dl, "missing_kinds": status["missing_kinds"]}


def fetch_yesterday() -> dict:
    """전날 파일 가져오기 (스케줄러/수동 실행용)."""
    y = (date_cls.today() - timedelta(days=1)).isoformat()
    return fetch_and_ingest(y)


# ── 폴더 감시 모드 연동 ────────────────────────────────────────────────────────

def _is_watcher_enabled() -> bool:
    """폴더 실시간 감시가 켜져 있는지 여부."""
    with get_apst_conn() as conn:
        row = conn.execute(
            "SELECT value FROM app_settings WHERE key = 'watcher_enabled'"
        ).fetchone()
    return bool(row and row["value"] == "1")


def _present_files_for_date(date: str) -> dict:
    """
    로컬 폴더(apst_dir/ddr1_dir/cml_path)에 해당 날짜의 APST/DDR1/CML 파일이
    존재하는지 검사한다. 반환: {"apst": bool, "ddr1": bool, "cml": bool}
    """
    conf = _get_conf()
    dnodash = date.replace("-", "")
    dirs = {
        "apst": (conf.get("apst_dir", ""), ".apst"),
        "ddr1": (conf.get("ddr1_dir", ""), ".log"),
        "cml":  (conf.get("cml_path", ""), ".cml"),
    }
    present = {}
    for kind, (d, ext) in dirs.items():
        found = False
        if d and Path(d).is_dir():
            for f in Path(d).iterdir():
                if f.is_file() and dnodash in f.name and f.name.lower().endswith(ext):
                    found = True
                    break
        present[kind] = found
    return present


def refresh_fetch_status(date: str) -> dict:
    """
    해당 날짜의 APST/DDR1/CML 세 파일이 모두 있으면 daily_fetch='ok',
    하나라도 없으면 'missing'(어떤 파일이 없는지 메시지에 표시)으로 기록한다.
    (미완이면 달력에 붉은색으로 표시됨) — FTP·폴더감시 공용.
    """
    present = _present_files_for_date(date)
    missing = [k.upper() for k in ("apst", "ddr1", "cml") if not present[k]]
    if not missing:
        _set_status(date, "ok", "APST·DDR1·CML 파일 모두 존재")
        return {"date": date, "ok": True}
    _set_status(date, "missing", f"없는 파일: {', '.join(missing)}")
    return {"date": date, "ok": False, "missing": True, "missing_kinds": missing}


# ── 스케줄러 (매일 지정 시각에 전날 파일 자동 가져오기) ────────────────────────

_sched_thread: threading.Thread | None = None
_sched_stop = threading.Event()
_last_run_date: str | None = None   # 정상 완료(성공/파일없음)한 날짜
_retry_date: str | None = None      # 재시도 진행 중인 날짜
_retry_count: int = 0
_next_retry_ts: float = 0.0

# 네트워크 오류 등으로 실패 시 재시도 설정
_RETRY_INTERVAL_SEC = 120   # 재시도 간격 (2분)
_MAX_RETRIES = 5            # 하루 최대 시도 횟수


def _scheduler_loop():
    global _last_run_date, _retry_date, _retry_count, _next_retry_ts
    while not _sched_stop.is_set():
        try:
            t = (_get_conf().get("ftp_fetch_time") or "").strip()
            if re.match(r"^\d{1,2}:\d{2}$", t):
                now = datetime.now()
                today = now.date().isoformat()
                hh, mm = t.split(":")

                # 예약 시각 도달 → 오늘 첫 시도 준비
                if now.hour == int(hh) and now.minute == int(mm) \
                        and _last_run_date != today and _retry_date != today:
                    _retry_date = today
                    _retry_count = 0
                    _next_retry_ts = 0.0

                # 오늘 시도가 시작됐고 아직 완료되지 않았으면 시도/재시도
                if _retry_date == today and _last_run_date != today \
                        and _retry_count < _MAX_RETRIES and time.time() >= _next_retry_ts:
                    # ── 상호 배타: 폴더 감시가 켜져 있으면 FTP 가져오기는 건너뛴다 ──
                    # 대신 전날 파일이 폴더 감시로 적재됐는지 점검해, 미적재면 달력에
                    # 붉은색(누락)으로 표시한다.
                    if _is_watcher_enabled():
                        # 폴더 감시 모드에서는 FTP 가져오기를 하지 않는다(로그도 남기지 않음).
                        # 전날 파일이 폴더 감시로 적재됐는지만 조용히 점검한다.
                        y = (date_cls.today() - timedelta(days=1)).isoformat()
                        refresh_fetch_status(y)
                        _last_run_date = today
                        _sched_stop.wait(30)
                        continue

                    _retry_count += 1
                    attempt = _retry_count
                    label = "시작" if attempt == 1 else f"재시도({attempt}/{_MAX_RETRIES})"
                    log_event("info", "ftp", f"FTP 자동 가져오기 {label} (예약 {t}, 전날 파일)")
                    try:
                        res = fetch_yesterday()
                    except Exception as e:
                        res = {"ok": False, "error": str(e)}
                    if res.get("ok") or res.get("missing"):
                        # 연결 성공(적재 완료 또는 파일 없음 확정) → 오늘 종료
                        _last_run_date = today
                        if attempt > 1:
                            log_event("info", "ftp",
                                      f"FTP 자동 가져오기 재시도 성공 ({attempt}회차)")
                    else:
                        # 네트워크 등 오류 → 다음 재시도 예약
                        _next_retry_ts = time.time() + _RETRY_INTERVAL_SEC
                        if attempt >= _MAX_RETRIES:
                            _last_run_date = today   # 재시도 소진 → 무한루프 방지
                            log_event("error", "ftp",
                                      f"FTP 자동 가져오기 최종 실패 (재시도 {attempt}회 소진). "
                                      f"네트워크 연결 후 수동으로 가져오세요.")
        except Exception:
            pass
        _sched_stop.wait(30)


def start_scheduler():
    global _sched_thread
    if _sched_thread and _sched_thread.is_alive():
        return
    _sched_stop.clear()
    _sched_thread = threading.Thread(target=_scheduler_loop, daemon=True)
    _sched_thread.start()
    # 서버 재시작(--reload)마다 로그가 쌓이지 않도록 활동 로그(DB)에는 남기지 않고
    # 콘솔에만 출력한다.
    print("[FTP] 자동 가져오기 스케줄러 시작")


def stop_scheduler():
    _sched_stop.set()


def get_missing_dates(year: int, month: int) -> list[str]:
    """
    해당 월의 미수집 날짜 목록 (MISSING_MARK_START 이후만).
    - 'missing': 연결됐으나 APST 파일 없음
    - 'error'  : 네트워크 오류 등으로 가져오지 못함
    둘 다 달력에 붉은색으로 표시한다.
    """
    from config import MISSING_MARK_START
    ym = f"{year:04d}-{month:02d}"
    with get_apst_conn() as conn:
        rows = conn.execute(
            """SELECT broadcast_date FROM daily_fetch
               WHERE status IN ('missing', 'error')
                 AND broadcast_date LIKE ? AND broadcast_date >= ?""",
            (f"{ym}-%", MISSING_MARK_START),
        ).fetchall()
    return [r["broadcast_date"] for r in rows]
