#!/usr/bin/env bash
#
# sbdb 앱 셋업 스크립트 (Ubuntu 용 — setup_ec2.sh 의 apt 버전)
# - 패키지 확인 → 한글 폰트 → 소스 clone/pull → 백엔드(venv+pip) → 프론트(npm build)
#   → 접근제한 IP 초기화 까지 한 번에.
# - 먼저 init_ubuntu.sh 로 기본 셋팅(Git/Python/Node/방화벽)을 마친 뒤 실행 권장.
#
# 사용법:
#   bash setup_ubuntu.sh
#
set -e

# ===== 설정 =====================================================
REPO_URL="https://github.com/hhyhappyman/sbdb.git"
APP_DIR="$HOME/sbdb"          # 소스가 받아질 위치
OPEN_ALL_IP="1"              # 1이면 최초 접근제한을 0.0.0.0(전체 허용)으로 설정
# ==============================================================

echo "==================================================="
echo "  sbdb 셋업 (Ubuntu) — $APP_DIR"
echo "==================================================="

# ── 1. 필요한 패키지 확인/설치 ────────────────────────────────
echo "[1/6] 패키지 확인 (git, python3, venv, node)..."
sudo apt update -y >/dev/null 2>&1 || true
sudo apt install -y git python3 python3-venv python3-pip nodejs npm >/dev/null
echo "  Python: $(python3 --version) | Node: $(node --version 2>/dev/null || echo '미설치')"

# ── 1-b. 한글 폰트(NanumGothic, TrueType) 설치 ────────────────
# PDF/Word 한글 렌더링용. reportlab은 TrueType만 지원하므로 CFF 방식 Noto CJK가
# 아니라 TrueType인 NanumGothic을 ~/.fonts 에 받는다. (앱 코드가 ~/.fonts 를 검색)
echo "[1-b] 한글 폰트(NanumGothic) 설치..."
FONT_DIR="$HOME/.fonts"
mkdir -p "$FONT_DIR"
_NG_BASE="https://raw.githubusercontent.com/google/fonts/main/ofl/nanumgothic"
for _f in NanumGothic-Regular.ttf NanumGothic-Bold.ttf; do
  if [ ! -s "$FONT_DIR/$_f" ]; then
    curl -fsSL "$_NG_BASE/$_f" -o "$FONT_DIR/$_f" || echo "  ⚠️ $_f 다운로드 실패 (수동 설치 필요)"
  fi
done
command -v fc-cache >/dev/null 2>&1 && fc-cache -f "$FONT_DIR" >/dev/null 2>&1 || true
echo "  설치된 한글 폰트: $(ls "$FONT_DIR"/NanumGothic-*.ttf 2>/dev/null | wc -l)개"

# ── 2. 소스 clone / pull ──────────────────────────────────────
echo "[2/6] 소스 내려받기..."
if [ -d "$APP_DIR/.git" ]; then
  echo "  기존 저장소 발견 → git pull"
  git -C "$APP_DIR" pull --ff-only
else
  git clone "$REPO_URL" "$APP_DIR"
fi
cd "$APP_DIR"

# ── 3. 백엔드 (Python venv + pip) ─────────────────────────────
echo "[3/6] 백엔드 의존성 설치..."
[ -d venv ] || python3 -m venv venv
# shellcheck disable=SC1091
source venv/bin/activate
pip install --upgrade pip >/dev/null
pip install -r requirements.txt

# ── 4. 프론트엔드 (npm build) ─────────────────────────────────
echo "[4/6] 프론트엔드 빌드..."
cd "$APP_DIR/client"
npm install
npm run build
cd "$APP_DIR"

# ── 5. 최초 접근제한 완화 (선택) ──────────────────────────────
echo "[5/6] 초기 DB/설정 준비..."
if [ "$OPEN_ALL_IP" = "1" ]; then
  python3 - <<'PYEOF' || true
import os, sqlite3
db = os.path.join(os.path.expanduser("~"), "sbdb", "db", "apst.db")
os.makedirs(os.path.dirname(db), exist_ok=True)
conn = sqlite3.connect(db)
conn.execute("CREATE TABLE IF NOT EXISTS app_settings (key TEXT PRIMARY KEY, value TEXT)")
conn.execute("INSERT OR REPLACE INTO app_settings (key, value) VALUES ('allowed_ip_ranges','0.0.0.0')")
conn.commit(); conn.close()
print("  접근 허용 IP = 0.0.0.0 (전체 허용) 로 설정")
PYEOF
fi

echo "[6/6] 완료 준비..."
echo
echo "==================================================="
echo "  셋업 완료!"
echo "==================================================="
echo "서버 실행:"
echo "  cd $APP_DIR/server && source ../venv/bin/activate"
echo "  uvicorn main:app --host 0.0.0.0 --port 8000"
echo
echo "부팅 자동 시작 등록(권장):"
echo "  cd $APP_DIR && bash install_service.sh"
echo
echo "확인 사항:"
echo "  - 방화벽에서 8000 포트 열림 (init_ubuntu.sh가 처리)"
echo "  - 환경설정 메뉴에서 apst_dir/ddr1_dir/cml_path/FTP 정보 입력"
echo "  - DB·데이터 파일은 별도 복사 필요 (.gitignore로 GitHub 제외)"
