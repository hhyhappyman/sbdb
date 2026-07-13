#!/usr/bin/env bash
#
# EC2(Amazon Linux) 초기 셋업 스크립트 — SB 송출 관리
# - 패키지 설치 → 소스 clone/pull → 백엔드(venv+pip) → 프론트(npm build) 까지 한 번에.
#
# 사용법 (EC2 터미널):
#   저장소가 public 이므로 raw 파일을 받아 실행:
#     curl -fsSL https://raw.githubusercontent.com/hhyhappyman/sbdb/main/setup_ec2.sh -o setup_ec2.sh
#     bash setup_ec2.sh
#   (이미 clone 되어 있으면 그 폴더에서 그냥 bash setup_ec2.sh 실행해도 됨)
#
set -e

# ===== 설정 =====================================================
REPO_URL="https://github.com/hhyhappyman/sbdb.git"
APP_DIR="$HOME/sbdb"          # 소스가 받아질 위치
OPEN_ALL_IP="1"              # 1이면 최초 접근제한을 0.0.0.0(전체 허용)으로 설정
# ==============================================================

echo "==================================================="
echo "  EC2 셋업 — SB 송출 관리"
echo "==================================================="

# ── 1. 패키지 설치 ────────────────────────────────────────────
echo "[1/5] 패키지 설치 (git, python, node)..."
sudo dnf install -y git nodejs npm >/dev/null 2>&1 || sudo yum install -y git nodejs npm

# Python 3.12 우선, 없으면 python3 사용
if command -v python3.12 >/dev/null 2>&1; then
  PY=python3.12
  sudo dnf install -y python3.12-pip >/dev/null 2>&1 || true
else
  sudo dnf install -y python3 python3-pip >/dev/null 2>&1 || sudo yum install -y python3 python3-pip
  PY=python3
fi
echo "  Python: $($PY --version)"
echo "  Node:   $(node --version 2>/dev/null || echo '미설치')"

# ── 1-b. 한글 폰트(NanumGothic, TrueType) 설치 ────────────────
# PDF/Word 한글 렌더링용. reportlab은 TrueType만 지원하므로 CFF 방식인 Noto CJK가
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
echo "[2/5] 소스 내려받기..."
if [ -d "$APP_DIR/.git" ]; then
  echo "  기존 저장소 발견 → git pull"
  git -C "$APP_DIR" pull --ff-only
else
  git clone "$REPO_URL" "$APP_DIR"
fi
cd "$APP_DIR"

# ── 3. 백엔드 (Python venv + pip) ─────────────────────────────
echo "[3/5] 백엔드 의존성 설치..."
[ -d venv ] || $PY -m venv venv
# shellcheck disable=SC1091
source venv/bin/activate
pip install --upgrade pip >/dev/null
pip install -r requirements.txt

# ── 4. 프론트엔드 (npm build) ─────────────────────────────────
echo "[4/5] 프론트엔드 빌드..."
cd "$APP_DIR/client"
npm install
npm run build
cd "$APP_DIR"

# ── 5. 최초 접근제한 완화 (선택) ──────────────────────────────
echo "[5/5] 초기 DB/설정 준비..."
# 서버를 한 번 띄우면 init_db가 빈 DB를 생성하지만, 여기서는 접근제한만 미리 열어둔다.
if [ "$OPEN_ALL_IP" = "1" ]; then
  $PY - <<'PYEOF' || true
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

echo
echo "==================================================="
echo "  셋업 완료!"
echo "==================================================="
echo "서버 실행:"
echo "  cd $APP_DIR/server && source ../venv/bin/activate"
echo "  uvicorn main:app --host 0.0.0.0 --port 8000"
echo
echo "백그라운드 실행:"
echo "  nohup uvicorn main:app --host 0.0.0.0 --port 8000 > ~/sbdb/server.log 2>&1 &"
echo
echo "확인 사항:"
echo "  - EC2 보안 그룹 인바운드에서 8000 포트 열기"
echo "  - 환경설정 메뉴에서 apst_dir/ddr1_dir/cml_path/FTP 정보 입력"
echo "  - DB·데이터 파일은 별도 업로드 필요 (.gitignore로 제외됨)"
