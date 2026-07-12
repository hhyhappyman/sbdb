#!/usr/bin/env bash
#
# 코드 업데이트 스크립트 (EC2)
# - GitHub 최신 코드를 받아 프론트 재빌드 + 백엔드 의존성 갱신 후 서비스 재시작.
# - install_service.sh 로 systemd 서비스(sbdb)를 등록한 상태에서 사용한다.
#
# 사용법:
#   cd ~/sbdb && bash update.sh
#
set -e
cd "$(dirname "$0")"
APP_DIR="$(pwd)"
SERVICE_NAME="sbdb"

echo "==================================================="
echo "  코드 업데이트 — $APP_DIR"
echo "==================================================="

# ── 1. 최신 소스 받기 ─────────────────────────────────────────
echo "[1/4] git pull..."
git pull --ff-only

# ── 2. 백엔드 의존성 갱신 ─────────────────────────────────────
echo "[2/4] 백엔드 의존성 갱신..."
# shellcheck disable=SC1091
source "$APP_DIR/venv/bin/activate"
pip install -r requirements.txt >/dev/null

# ── 3. 프론트엔드 재빌드 ──────────────────────────────────────
echo "[3/4] 프론트엔드 빌드..."
cd "$APP_DIR/client"
npm install >/dev/null
npm run build
cd "$APP_DIR"

# ── 4. 서비스 재시작 ──────────────────────────────────────────
echo "[4/4] 서비스 재시작..."
if systemctl list-unit-files 2>/dev/null | grep -q "^${SERVICE_NAME}.service"; then
  sudo systemctl restart "$SERVICE_NAME"
  echo "  → systemd 서비스($SERVICE_NAME) 재시작 완료"
else
  echo "  ⚠️ systemd 서비스가 없습니다. install_service.sh 로 먼저 등록하거나,"
  echo "     run_server.sh 로 수동 실행하세요."
fi

echo
echo "==================================================="
echo "  업데이트 완료!"
echo "==================================================="
echo "상태 확인 :  sudo systemctl status $SERVICE_NAME"
echo "로그 보기 :  journalctl -u $SERVICE_NAME -f"
echo "(브라우저는 Ctrl+F5 로 강력 새로고침)"
