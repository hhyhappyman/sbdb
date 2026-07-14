#!/usr/bin/env bash
#
# Ubuntu 설치 직후 초기 셋팅 + 필수 프로그램 설치 (sbdb 서비스용)
# - 시스템 업데이트, 원격접속(SSH), 방화벽, 그리고 sbdb 실행에 필요한
#   Git / Python / Node.js 를 설치한다.
# - Ubuntu Desktop/Server 22.04 이상 기준.
#
# 사용법:
#   bash init_ubuntu.sh
#
set -e

echo "==================================================="
echo "  Ubuntu 초기 셋팅 (sbdb 서비스용)"
echo "==================================================="

# ── 1. 시스템 업데이트 ────────────────────────────────
echo "[1/6] 시스템 업데이트..."
sudo apt update
sudo apt upgrade -y

# ── 2. 필수 도구 ──────────────────────────────────────
echo "[2/6] 필수 도구 설치 (git, curl, vim 등)..."
sudo apt install -y curl wget git vim net-tools build-essential

# ── 3. 원격 접속(SSH) ─────────────────────────────────
echo "[3/6] SSH 서버 설치 (다른 PC에서 원격 접속용)..."
sudo apt install -y openssh-server
sudo systemctl enable --now ssh

# ── 4. Python (백엔드) ────────────────────────────────
echo "[4/6] Python + venv 설치..."
sudo apt install -y python3 python3-venv python3-pip
echo "  Python: $(python3 --version)"

# ── 5. Node.js (프론트엔드 빌드) ──────────────────────
echo "[5/6] Node.js + npm 설치..."
sudo apt install -y nodejs npm
echo "  Node: $(node --version 2>/dev/null || echo '미설치')"

# ── 6. 방화벽 (SSH + 앱 8000 포트) ────────────────────
echo "[6/6] 방화벽(ufw) 설정..."
sudo apt install -y ufw
sudo ufw allow OpenSSH
sudo ufw allow 8000/tcp     # sbdb 웹 서비스 포트
sudo ufw --force enable
sudo ufw status

echo
echo "==================================================="
echo "  초기 셋팅 완료!"
echo "==================================================="
echo "이 PC의 IP 주소:"
ip -4 addr show 2>/dev/null | grep -oP '(?<=inet\s)\d+(\.\d+){3}' | grep -v '127.0.0.1'
echo
echo "다음 단계: bash setup_ubuntu.sh  (sbdb 소스 내려받고 빌드)"
