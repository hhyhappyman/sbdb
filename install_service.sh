#!/usr/bin/env bash
#
# systemd 서비스 등록 스크립트 (EC2 / Amazon Linux)
# - 서버를 부팅 시 자동 시작하고, 크래시/재부팅 시 자동 복구되도록 등록한다.
# - setup_ec2.sh 로 셋업(venv/빌드)을 마친 뒤 1회 실행한다.
#
# 사용법:
#   bash install_service.sh            # 서비스 등록 + 시작 + 부팅 자동시작 설정
#   bash install_service.sh uninstall  # 서비스 중지 + 등록 해제
#
set -e
cd "$(dirname "$0")"
APP_DIR="$(pwd)"

SERVICE_NAME="sbdb"
UNIT_PATH="/etc/systemd/system/${SERVICE_NAME}.service"
RUN_USER="$(whoami)"
HOST="0.0.0.0"
PORT="8000"

# ── 등록 해제 ─────────────────────────────────────────────────
if [ "${1:-}" = "uninstall" ]; then
  sudo systemctl stop "$SERVICE_NAME" 2>/dev/null || true
  sudo systemctl disable "$SERVICE_NAME" 2>/dev/null || true
  sudo rm -f "$UNIT_PATH"
  sudo systemctl daemon-reload
  echo "서비스($SERVICE_NAME)를 등록 해제했습니다."
  exit 0
fi

# ── venv 확인 ─────────────────────────────────────────────────
if [ ! -x "$APP_DIR/venv/bin/uvicorn" ]; then
  echo "[오류] venv/uvicorn 이 없습니다. 먼저 setup_ec2.sh 로 셋업하세요."
  exit 1
fi

echo "[정보] 서비스 유닛 파일 생성: $UNIT_PATH"
echo "  실행 사용자 : $RUN_USER"
echo "  작업 폴더   : $APP_DIR/server"
echo "  주소        : $HOST:$PORT"

# ── 유닛 파일 작성 (sudo tee) ─────────────────────────────────
sudo tee "$UNIT_PATH" > /dev/null <<EOF
[Unit]
Description=SB 송출 관리 서버 (FastAPI/uvicorn)
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=$RUN_USER
WorkingDirectory=$APP_DIR/server
ExecStart=$APP_DIR/venv/bin/uvicorn main:app --host $HOST --port $PORT
Restart=always
RestartSec=5
StandardOutput=append:$APP_DIR/server.log
StandardError=append:$APP_DIR/server.log

[Install]
WantedBy=multi-user.target
EOF

# ── 적용 ─────────────────────────────────────────────────────
sudo systemctl daemon-reload
sudo systemctl enable "$SERVICE_NAME"     # 부팅 시 자동 시작
sudo systemctl restart "$SERVICE_NAME"    # 지금 바로 시작(재시작)

echo
echo "==================================================="
echo "  서비스 등록 완료! (부팅 시 자동 시작)"
echo "==================================================="
echo "상태 확인 :  sudo systemctl status $SERVICE_NAME"
echo "로그 보기 :  journalctl -u $SERVICE_NAME -f   (또는 tail -f $APP_DIR/server.log)"
echo "재시작    :  sudo systemctl restart $SERVICE_NAME"
echo "중지      :  sudo systemctl stop $SERVICE_NAME"
echo "등록 해제 :  bash install_service.sh uninstall"
