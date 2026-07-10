#!/usr/bin/env bash
#
# GitHub 업로드 스크립트 (WSL Ubuntu 용)
# - 프로젝트 소스를 GitHub 저장소에 커밋·푸시한다.
# - GitHub 아이디 / 저장소 이름 / 브랜치 / 커밋 메시지를 실행 시 직접 입력한다.
#
# 사용 전 준비:
#   1) GitHub 웹에서 빈 저장소를 먼저 만들어 둔다 (README 없이 생성 권장).
#   2) 푸시 인증은 GitHub 비밀번호가 아니라 Personal Access Token(PAT)이 필요하다.
#      (GitHub → Settings → Developer settings → Personal access tokens 에서 발급)
#
# 실행:
#   cd /home/young/code/proj1
#   bash upload_to_github.sh
#
set -e

# 스크립트가 있는 폴더로 이동 (어디서 실행해도 프로젝트 루트 기준 동작)
cd "$(dirname "$0")"
PROJECT_DIR="$(pwd)"

echo "==================================================="
echo "  GitHub 업로드 — $PROJECT_DIR"
echo "==================================================="

# ── git 설치 확인 ────────────────────────────────────
if ! command -v git >/dev/null 2>&1; then
  echo "[오류] git이 설치되어 있지 않습니다.  sudo apt install git 후 다시 실행하세요."
  exit 1
fi

# ── 입력값 받기 ──────────────────────────────────────
read -rp "GitHub 아이디(사용자명): " GH_USER
read -rp "저장소 이름 (예: sb-broadcast): " GH_REPO
read -rp "브랜치 이름 [main]: " GH_BRANCH
GH_BRANCH="${GH_BRANCH:-main}"
read -rp "커밋 메시지 [Update source]: " GH_MSG
GH_MSG="${GH_MSG:-Update source}"

if [ -z "$GH_USER" ] || [ -z "$GH_REPO" ]; then
  echo "[오류] GitHub 아이디와 저장소 이름은 반드시 입력해야 합니다."
  exit 1
fi

REMOTE_URL="https://github.com/${GH_USER}/${GH_REPO}.git"

echo
echo "  원격 저장소 : $REMOTE_URL"
echo "  브랜치      : $GH_BRANCH"
echo "  커밋 메시지 : $GH_MSG"
echo
read -rp "위 내용으로 진행할까요? (y/N): " CONFIRM
if [ "$CONFIRM" != "y" ] && [ "$CONFIRM" != "Y" ]; then
  echo "취소했습니다."
  exit 0
fi

# ── git 사용자 정보 확인 (없으면 설정) ────────────────
if ! git config user.name >/dev/null 2>&1; then
  read -rp "git 사용자 이름(user.name)이 없습니다. 입력: " GIT_NAME
  git config --global user.name "$GIT_NAME"
fi
if ! git config user.email >/dev/null 2>&1; then
  read -rp "git 이메일(user.email)이 없습니다. 입력: " GIT_EMAIL
  git config --global user.email "$GIT_EMAIL"
fi

# ── 저장소 초기화 ────────────────────────────────────
if [ ! -d .git ]; then
  echo "[정보] git 저장소를 초기화합니다."
  git init
fi

# 기본 브랜치 이름 설정
git checkout -B "$GH_BRANCH"

# ── 원격(remote) 설정 ────────────────────────────────
if git remote get-url origin >/dev/null 2>&1; then
  git remote set-url origin "$REMOTE_URL"
else
  git remote add origin "$REMOTE_URL"
fi

# ── 커밋 ─────────────────────────────────────────────
git add -A
if git diff --cached --quiet; then
  echo "[정보] 커밋할 변경 사항이 없습니다. 푸시만 시도합니다."
else
  git commit -m "$GH_MSG"
fi

# ── 푸시 ─────────────────────────────────────────────
echo
echo "[정보] GitHub로 푸시합니다. 사용자명/비밀번호를 물으면"
echo "       비밀번호 자리에 Personal Access Token(PAT)을 입력하세요."
echo
git push -u origin "$GH_BRANCH"

echo
echo "==================================================="
echo "  완료!  https://github.com/${GH_USER}/${GH_REPO}"
echo "==================================================="
