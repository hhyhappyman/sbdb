"""
Real-time folder watcher using watchdog.
Monitors apst_dir and ddr1_dir for new files and auto-ingests them.

Watched events:
  - New .apst file  → parse_apst → apst.db
  - New .Log/.log file → parse_ddr1 → ddr1.db  (date extracted from filename)
  - New .cml file   → parse_cml → clip_map in ddr1.db
"""

import re
import time
import threading
import logging
from pathlib import Path
from datetime import datetime

from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler, FileCreatedEvent, FileMovedEvent

from database import get_apst_conn, get_ddr1_conn
from config import APST_SUFFIX_DEFAULT
from parsers.utils import apst_name_matches, find_apst_files
from parsers.apst_parser import parse_apst, find_manual_segments
from parsers.cml_parser import parse_cml, build_clip_rows, resolve_cml_path_for_date
from parsers.ddr1_parser import parse_ddr1, extract_manual_segment_records
from services.aggregator import get_campaign_names
from services.activity_log import log_event

logger = logging.getLogger("file_watcher")

# ── 전역 감시 상태 ────────────────────────────────────────────────────────────
_observer: Observer | None = None
_lock = threading.Lock()

# 감시 로그 (최근 100건 메모리 보관)
_watch_log: list[dict] = []
_MAX_LOG = 100


def _add_log(level: str, message: str):
    entry = {
        "time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "level": level,
        "message": message,
    }
    _watch_log.append(entry)
    if len(_watch_log) > _MAX_LOG:
        _watch_log.pop(0)
    if level == "error":
        logger.error(message)
    else:
        logger.info(message)


def get_watch_log() -> list[dict]:
    return list(reversed(_watch_log))


# ── 날짜 추출 ──────────────────────────────────────────────────────────────────
def _date_from_filename(filename: str) -> str | None:
    m = re.search(r'(\d{4})(\d{2})(\d{2})', filename)
    if m:
        return f"{m.group(1)}-{m.group(2)}-{m.group(3)}"
    m = re.search(r'(\d{4}-\d{2}-\d{2})', filename)
    return m.group(1) if m else None


def _find_manual_windows_for_date(broadcast_date: str) -> list[tuple[str, str]]:
    """
    해당 날짜의 apst_dir 파일에서 수동 송출 구간(시작/종료 시간)을 찾는다.
    parse_ddr1()의 exclude_windows로 전달해, find_manual_segments() 기반 적재와
    겹치지 않도록 한다.
    """
    apst_dir, _ddr1_dir = _get_dirs()
    if not apst_dir:
        return []

    dir_path = Path(apst_dir)
    if not dir_path.exists() or not dir_path.is_dir():
        return []

    for fpath in find_apst_files(dir_path, _apst_suffix(), broadcast_date):
        try:
            segments = find_manual_segments(str(fpath))
        except Exception:
            continue
        return [(seg["start_time"], seg["end_time"]) for seg in segments]

    return []


# ── 적재 함수 ──────────────────────────────────────────────────────────────────
def _reconcile_date(date: str):
    """
    해당 날짜의 CML → APST → DDR1(수동송출)을 순서 보장하여 재적재한다.
    앱 내 가져오기와 동일한 ingest_date()를 사용하므로, 폴더 감시에서 파일이
    어떤 순서로 도착해도(예: DDR1이 APST보다 늦게 도착) 수동송출까지 정상 생성된다.
    (ingest_date는 중복검사가 있어 반복 호출해도 안전.) 이어서 달력 상태를 갱신한다.
    """
    from routers.ingest import ingest_date
    from services.ftp_fetcher import refresh_fetch_status
    try:
        res = ingest_date(date)
        _add_log("info",
                 f"[감시] {date} 재적재: APST {res['apst']}건 · 수동 {res['manual']}건 · CML {res['cml']}건")
    except Exception as e:
        _add_log("error", f"[감시] {date} 재적재 오류: {e}")
    try:
        refresh_fetch_status(date)
    except Exception:
        pass


def _ingest_apst(file_path: str):
    """APST 파일 적재. 접미사 규칙 불일치·이미 처리된 파일은 건너뜀."""
    fname = Path(file_path).name

    # 환경설정 접미사 규칙에 맞는 APST 파일만 적재 (대소문자 무시)
    if not apst_name_matches(fname, _apst_suffix()):
        return

    with get_apst_conn() as conn:
        exists = conn.execute(
            "SELECT 1 FROM broadcasts WHERE source_file = ? LIMIT 1", (fname,)
        ).fetchone()
    if exists:
        _add_log("info", f"[APST] 이미 처리됨, 건너뜀: {fname}")
        return

    try:
        # 파일 쓰기가 완전히 끝날 때까지 잠시 대기
        time.sleep(1.5)
        records = parse_apst(file_path, source_file=fname)
        with get_apst_conn() as conn:
            conn.executemany(
                """INSERT INTO broadcasts
                   (broadcast_date, broadcast_time, broadcast_hour,
                    clip_id, item_name_raw, item_name, duration_sec,
                    program_block, content_type, content_type_label, grade,
                    main_equipment, internal_id, source_file)
                   VALUES
                   (:broadcast_date, :broadcast_time, :broadcast_hour,
                    :clip_id, :item_name_raw, :item_name, :duration_sec,
                    :program_block, :content_type, :content_type_label, :grade,
                    :main_equipment, :internal_id, :source_file)""",
                records,
            )
        _add_log("info", f"[APST] 자동 적재 완료: {fname} ({len(records)}건)")
        log_event("info", "db_insert", f"APST 자동 적재: {fname} ({len(records)}건)")

        # CML/APST/DDR1 순서 보장 재적재(수동송출 포함) + 달력 상태(daily_fetch) 갱신
        bdate = _date_from_filename(fname)
        if bdate:
            _reconcile_date(bdate)
    except Exception as e:
        _add_log("error", f"[APST] 오류: {fname} — {e}")


def _ingest_manual_segments(segments: list[dict]) -> int:
    """
    주장비명이 DDR1인 수동 송출 구간(segments)에 대해 해당 날짜의 DDR1 로그 파일을
    찾아 실제 송출된 소재를 추출하고 ddr1.db에 적재한다.
    ddr1_dir 미설정, clip_map 비어있음, 해당 날짜 로그 없음 등의 경우 조용히 0건 반환.
    """
    if not segments:
        return 0

    apst_dir, ddr1_dir = _get_dirs()
    if not ddr1_dir:
        return 0

    dir_path = Path(ddr1_dir)
    if not dir_path.exists() or not dir_path.is_dir():
        return 0

    log_files_by_date: dict[str, str] = {}
    for fpath in list(dir_path.glob("*.Log")) + list(dir_path.glob("*.log")):
        d = _date_from_filename(fpath.name)
        if d and d not in log_files_by_date:
            log_files_by_date[d] = str(fpath)

    for seg in segments:
        if seg["broadcast_date"] not in log_files_by_date:
            log_event(
                "warning", "file_missing",
                f"DDR1 로그 파일을 찾을 수 없습니다 (날짜: {seg['broadcast_date']}, ddr1_dir: '{ddr1_dir}')"
            )

    cml_setting = _get_setting_value("cml_path")
    cml_map_by_date: dict[str, dict] = {}
    for seg in segments:
        date = seg["broadcast_date"]
        if date in cml_map_by_date:
            continue
        cml_file = resolve_cml_path_for_date(cml_setting, date)
        if cml_file:
            cml_map_by_date[date] = parse_cml(cml_file)
        else:
            cml_map_by_date[date] = {}
            log_event(
                "warning", "file_missing",
                f"CML 파일을 찾을 수 없습니다 (날짜: {date}, cml_path 설정: '{cml_setting}')"
            )

    campaign_names = get_campaign_names()

    records = extract_manual_segment_records(segments, log_files_by_date, cml_map_by_date, campaign_names)
    if not records:
        return 0

    source_files = {r["source_file"] for r in records}
    with get_ddr1_conn() as conn:
        placeholders = ",".join("?" * len(source_files))
        done = {
            row["source_file"]
            for row in conn.execute(
                f"SELECT DISTINCT source_file FROM broadcasts WHERE source_file IN ({placeholders})",
                list(source_files),
            ).fetchall()
        }
    records = [r for r in records if r["source_file"] not in done]
    if not records:
        return 0

    with get_ddr1_conn() as conn:
        conn.executemany(
            """INSERT INTO broadcasts
               (broadcast_date, broadcast_time, broadcast_hour,
                clip_id, item_name_raw, item_name,
                content_type_label, grade, duration_sec, source_file)
               VALUES
               (:broadcast_date, :broadcast_time, :broadcast_hour,
                :clip_id, :item_name_raw, :item_name,
                :content_type_label, :grade, :duration_sec, :source_file)""",
            records,
        )
    log_event("info", "db_insert", f"수동 송출 구간 자동 적재 {len(records)}건 (ddr1.db)")
    return len(records)


def _ingest_cml(file_path: str, reconcile: bool = True):
    """
    CML 파일 적재 (clip_map 갱신).
    reconcile=True : 실시간 이벤트 — CML이 APST보다 늦게 도착한 경우 해당 날짜 재적재.
    reconcile=False: 초기 스캔 — clip_map만 갱신(무거운 재적재 연쇄를 하지 않음).
    """
    fname = Path(file_path).name
    try:
        time.sleep(1.5)
        clip_map = parse_cml(file_path)
        rows = build_clip_rows(clip_map)
        with get_ddr1_conn() as conn:
            conn.execute("DELETE FROM clip_map")
            conn.executemany(
                """INSERT INTO clip_map (clip_id, item_type, full_name, advertiser, duration_sec)
                   VALUES (:clip_id, :item_type, :full_name, :advertiser, :duration_sec)""",
                rows,
            )
        _add_log("info", f"[CML] 자동 갱신 완료: {fname} ({len(rows)}건)")
        # 초기 스캔(reconcile=False)에서는 활동 로그(DB)에 남기지 않아 로그 폭주를 막는다.
        if reconcile:
            log_event("info", "db_update", f"CML 매핑 자동 갱신: {fname} ({len(rows)}건)")

        # CML이 (APST보다 늦게) 실시간 도착한 경우에만 해당 날짜 수동송출을 재생성.
        # 초기 스캔(reconcile=False)에서는 clip_map만 갱신하고 재적재 연쇄를 하지 않는다.
        if reconcile:
            bdate = _date_from_filename(fname)
            if bdate:
                _reconcile_date(bdate)
    except Exception as e:
        _add_log("error", f"[CML] 오류: {fname} — {e}")


def _ingest_ddr1(file_path: str):
    """
    DDR1 로그 파일 감지 → 해당 날짜 전체를 재적재한다.
    수동송출은 APST 기준으로 추출되므로, DDR1 로그가 (APST보다 늦게) 도착하면
    여기서 ingest_date를 호출해 수동송출을 생성한다. (도착 순서 무관 보장)
    """
    fname = Path(file_path).name
    broadcast_date = _date_from_filename(fname)
    if not broadcast_date:
        _add_log("error", f"[DDR1] 파일명에서 날짜 추출 불가, 건너뜀: {fname}")
        return
    time.sleep(1.5)   # 파일 쓰기 완료 대기
    _reconcile_date(broadcast_date)


# ── 이벤트 핸들러 ─────────────────────────────────────────────────────────────
class _ApstHandler(FileSystemEventHandler):
    """APST 폴더 이벤트 핸들러."""

    def _handle(self, path: str):
        p = Path(path)
        suffix = p.suffix.lower()
        if suffix == ".apst":
            threading.Thread(target=_ingest_apst, args=(path,), daemon=True).start()
        elif suffix == ".cml":
            threading.Thread(target=_ingest_cml, args=(path,), daemon=True).start()

    def on_created(self, event):
        if not event.is_directory:
            self._handle(event.src_path)

    def on_moved(self, event):
        # FTP는 임시 파일로 받은 뒤 rename하는 경우가 많음
        if not event.is_directory:
            self._handle(event.dest_path)


class _Ddr1Handler(FileSystemEventHandler):
    """DDR1 폴더 이벤트 핸들러."""

    def _handle(self, path: str):
        p = Path(path)
        suffix = p.suffix.lower()
        if suffix in (".log",):
            threading.Thread(target=_ingest_ddr1, args=(path,), daemon=True).start()

    def on_created(self, event):
        if not event.is_directory:
            self._handle(event.src_path)

    def on_moved(self, event):
        if not event.is_directory:
            self._handle(event.dest_path)


class _CmlHandler(FileSystemEventHandler):
    """CML 폴더 이벤트 핸들러. 늦게 도착한 CML도 감지해 해당 날짜 상태를 재판정한다."""

    def _handle(self, path: str):
        if Path(path).suffix.lower() == ".cml":
            threading.Thread(target=_ingest_cml, args=(path,), daemon=True).start()

    def on_created(self, event):
        if not event.is_directory:
            self._handle(event.src_path)

    def on_moved(self, event):
        if not event.is_directory:
            self._handle(event.dest_path)


# ── 감시 시작/중지 ─────────────────────────────────────────────────────────────
def _get_dirs() -> tuple[str, str]:
    """app_settings에서 감시 대상 디렉터리 조회."""
    with get_apst_conn() as conn:
        rows = conn.execute(
            "SELECT key, value FROM app_settings WHERE key IN ('apst_dir','ddr1_dir')"
        ).fetchall()
    settings = {r["key"]: r["value"] for r in rows}
    return settings.get("apst_dir", ""), settings.get("ddr1_dir", "")


def _get_setting_value(key: str) -> str:
    """app_settings에서 단일 키 값 조회."""
    with get_apst_conn() as conn:
        row = conn.execute("SELECT value FROM app_settings WHERE key = ?", (key,)).fetchone()
    return row["value"] if row else ""


def _apst_suffix() -> str:
    """APST 파일명 접미사 설정값 (미설정 시 기본값)."""
    return _get_setting_value("apst_suffix") or APST_SUFFIX_DEFAULT


def _resolve(path: str) -> str:
    """경로 비교용 정규화(중복 감시 폴더 판별)."""
    try:
        return str(Path(path).resolve())
    except Exception:
        return path


def _cml_watch_dir() -> str:
    """
    감시할 CML 폴더를 반환한다.
    cml_path 설정이 폴더면 그대로, 파일이면 그 상위 폴더를 감시 대상으로 한다.
    유효한 폴더가 없으면 빈 문자열.
    """
    cml_setting = _get_setting_value("cml_path")
    if not cml_setting:
        return ""
    p = Path(cml_setting)
    d = p if p.is_dir() else p.parent
    return str(d) if d.is_dir() else ""


_scan_running = False


def _initial_scan():
    """
    감시 시작 시, 폴더에 이미 존재하는 미적재 파일을 일괄 적재한다.
    (감시기는 '시작 이후 새로 들어오는' 파일만 감지하므로, 먼저 업로드된 파일도
     처리되도록 CML → APST → DDR1 순서로 스캔한다. 이미 처리된 파일은 자동 건너뜀.)
    중복 실행 방지: 이미 스캔 중이면 건너뛴다.
    """
    global _scan_running
    if _scan_running:
        _add_log("info", "[감시] 초기 스캔이 이미 진행 중 — 중복 실행 건너뜀")
        return
    _scan_running = True

    apst_dir, ddr1_dir = _get_dirs()
    cml_dir = _get_setting_value("cml_path")
    try:
        # CML은 clip_map만 갱신(재적재 연쇄 없음). 실제 재적재는 아래 APST 단계에서 수행.
        if cml_dir and Path(cml_dir).is_dir():
            for f in sorted(Path(cml_dir).glob("*.cml")):
                _ingest_cml(str(f), reconcile=False)
        if apst_dir and Path(apst_dir).is_dir():
            for f in find_apst_files(apst_dir, _apst_suffix()):
                _ingest_apst(str(f))
        if ddr1_dir and Path(ddr1_dir).is_dir():
            for f in sorted(Path(ddr1_dir).glob("*.[lL][oO][gG]")):
                _ingest_ddr1(str(f))
        _add_log("info", "[감시] 기존 파일 초기 스캔 완료")
    except Exception as e:
        _add_log("error", f"[감시] 초기 스캔 오류: {e}")
    finally:
        _scan_running = False


def start_watching() -> dict:
    global _observer

    with _lock:
        if _observer and _observer.is_alive():
            return {"status": "already_running", "message": "이미 감시 중입니다."}

        apst_dir, ddr1_dir = _get_dirs()
        watched = []
        errors  = []

        observer = Observer()

        if apst_dir and Path(apst_dir).is_dir():
            observer.schedule(_ApstHandler(), apst_dir, recursive=False)
            watched.append(apst_dir)
        elif apst_dir:
            errors.append(f"APST 디렉터리 없음: {apst_dir}")

        if ddr1_dir and Path(ddr1_dir).is_dir():
            observer.schedule(_Ddr1Handler(), ddr1_dir, recursive=False)
            watched.append(ddr1_dir)
        elif ddr1_dir:
            errors.append(f"DDR1 디렉터리 없음: {ddr1_dir}")

        # CML 폴더 감시: 늦게 도착한 CML도 상태 재판정(refresh)을 트리거하도록 한다.
        # cml_path가 파일이면 그 상위 폴더를, 폴더면 그대로 감시한다.
        # 이미 감시 중인 폴더(APST/DDR1와 동일)면 중복 등록하지 않는다.
        cml_dir = _cml_watch_dir()
        if cml_dir and _resolve(cml_dir) not in {_resolve(w) for w in watched}:
            observer.schedule(_CmlHandler(), cml_dir, recursive=False)
            watched.append(cml_dir)

        if not watched:
            return {
                "status": "error",
                "message": "감시할 디렉터리가 없습니다. 환경설정을 확인하세요.",
                "errors": errors,
            }

        observer.start()
        _observer = observer

        # 감시 시작 전 이미 폴더에 있던 미적재 파일을 백그라운드로 일괄 스캔
        threading.Thread(target=_initial_scan, daemon=True).start()

        # DB에 감시 상태 저장 (재시작 시 자동 재개용)
        with get_apst_conn() as conn:
            conn.execute(
                "INSERT OR REPLACE INTO app_settings (key, value) VALUES ('watcher_enabled','1')"
            )

        msg = f"폴더 감시 시작: {', '.join(watched)}"
        _add_log("info", msg)
        return {
            "status": "started",
            "message": msg,
            "watching": watched,
            "errors": errors,
        }


def stop_watching(persist: bool = True) -> dict:
    """
    폴더 감시 중지.
    persist=True  : 사용자가 직접 끈 경우 → watcher_enabled='0' 저장(재시작 후에도 꺼짐 유지)
    persist=False : 서버 종료(shutdown) 시 → 설정값은 그대로 두어, 다음 시작 때 자동 재개되게 함
    """
    global _observer

    with _lock:
        if not _observer or not _observer.is_alive():
            return {"status": "not_running", "message": "감시 중이 아닙니다."}

        _observer.stop()
        _observer.join(timeout=3)
        _observer = None

        if persist:
            with get_apst_conn() as conn:
                conn.execute(
                    "INSERT OR REPLACE INTO app_settings (key, value) VALUES ('watcher_enabled','0')"
                )

        _add_log("info", "폴더 감시 중지")
        return {"status": "stopped", "message": "폴더 감시를 중지했습니다."}


def get_watcher_status() -> dict:
    global _observer
    running = bool(_observer and _observer.is_alive())

    apst_dir, ddr1_dir = _get_dirs()
    watching = []
    if running:
        if apst_dir and Path(apst_dir).is_dir():
            watching.append(apst_dir)
        if ddr1_dir and Path(ddr1_dir).is_dir():
            watching.append(ddr1_dir)
        cml_dir = _cml_watch_dir()
        if cml_dir and _resolve(cml_dir) not in {_resolve(w) for w in watching}:
            watching.append(cml_dir)

    return {
        "running": running,
        "watching": watching,
        "log": get_watch_log()[:20],   # 최근 20건만
    }


def auto_start_if_enabled():
    """서버 시작 시 이전에 감시 중이었으면 자동 재개."""
    try:
        with get_apst_conn() as conn:
            row = conn.execute(
                "SELECT value FROM app_settings WHERE key = 'watcher_enabled'"
            ).fetchone()
        if row and row["value"] == "1":
            result = start_watching()
            logger.info(f"[Watcher] 자동 재개: {result['message']}")
    except Exception as e:
        logger.warning(f"[Watcher] 자동 재개 실패: {e}")
