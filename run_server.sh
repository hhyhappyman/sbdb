#!/usr/bin/env bash
#
# 서버 실행 스크립트 (EC2 / 로컬 공통)
# - setup_ec2.sh 로 셋업을 마친 뒤 사용한다.
# - 인자로 실행 모드를 준다:
#     bash run_server.sh          # 포그라운드 실행 (Ctrl+C로 종료)
#     bash run_server.sh bg       # 백그라운드 실행 (nohup, 로그는 server.log)
#     bash run_server.sh stop     # 백그라운드 서버 종료
#
set -e
cd "$(dirname "$0")"
APP_DIR="$(pwd)"

HOST="0.0.0.0"
PORT="8000"
LOG="$APP_DIR/server.log"
PIDFILE="$APP_DIR/server.pid"

MODE="${1:-fg}"

# ── 종료 ──────────────────────────────────────────────────────
if [ "$MODE" = "stop" ]; then
  if [ -f "$PIDFILE" ] && kill -0 "$(cat "$PIDFILE")" 2>/dev/null; then
    kill "$(cat "$PIDFILE")"
    rm -f "$PIDFILE"
    echo "서버를 종료했습니다."
  else
    echo "실행 중인 서버(PID 파일)를 찾지 못했습니다."
  fi
  exit 0
fi

# ── venv 확인 ─────────────────────────────────────────────────
if [ ! -d "$APP_DIR/venv" ]; then
  echo "[오류] venv가 없습니다. 먼저 setup_ec2.sh 로 셋업하세요."
  exit 1
fi
# shellcheck disable=SC1091
source "$APP_DIR/venv/bin/activate"
cd "$APP_DIR/server"

# ── 백그라운드 실행 ───────────────────────────────────────────
if [ "$MODE" = "bg" ]; then
  nohup uvicorn main:app --host "$HOST" --port "$PORT" > "$LOG" 2>&1 &
  echo $! > "$PIDFILE"
  echo "백그라운드 실행 시작 (PID $(cat "$PIDFILE"))"
  echo "  로그:  tail -f $LOG"
  echo "  종료:  bash run_server.sh stop"
  exit 0
fi

# ── 포그라운드 실행 (기본) ────────────────────────────────────
echo "서버 실행 (http://$HOST:$PORT) — 종료하려면 Ctrl+C"
exec uvicorn main:app --host "$HOST" --port "$PORT"
