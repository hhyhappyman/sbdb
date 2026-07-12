#!/bin/bash
#
# WSL -> EC2 rsync 전송 스크립트
# 대상: data 폴더(apst/ddr1_log/cml 등 하위 폴더 포함), db 폴더
# 목적지: EC2의 /home/ec2-user/sbdb 밑
# 특징: 중단되어도 재실행하면 이어서 전송됨 (rsync 증분 전송)
#

# ============================================
# ▼▼▼ 아래 값들을 환경에 맞게 입력하세요 ▼▼▼
# ============================================

# ----- WSL 로컬 소스 경로 -----
LOCAL_DATA_DIR="$HOME/data"      # 예: ~/data (밑에 apst, ddr1_log, cml 등 하위 폴더 포함)
LOCAL_DB_DIR="$HOME/code/proj1/db"          # 예: ~/db

# ----- EC2 접속 정보 -----
EC2_HOST="54.226.5.78"          # EC2 퍼블릭 IP
EC2_USER="ec2-user"  # 예: ec2-user, ubuntu
PEM_PATH="$HOME/code/proj1/gistedu-3-key-sbdb.pem"   # pem 키 경로

# ----- EC2 목적지 기준 경로 (하위에 data/, db/ 로 각각 생성됨) -----
EC2_BASE_DIR="/home/ec2-user/sbdb"

# ============================================
# ▲▲▲ 입력 끝 ▲▲▲ (아래는 수정 불필요)
# ============================================

LOG_DIR="$HOME/rsync_logs"
LOG_FILE="${LOG_DIR}/rsync_$(date +%Y%m%d_%H%M%S).log"
mkdir -p "$LOG_DIR"

log() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $1" | tee -a "$LOG_FILE"
}

# 필수값 체크
for VAR in EC2_HOST EC2_USER PEM_PATH EC2_BASE_DIR; do
    if [ -z "${!VAR}" ]; then
        log "오류: ${VAR} 값이 비어 있습니다. 스크립트 상단을 채워주세요."
        exit 1
    fi
done

# pem 키 존재 확인
if [ ! -f "$PEM_PATH" ]; then
    log "오류: pem 키 파일을 찾을 수 없습니다: ${PEM_PATH}"
    exit 1
fi

# 로컬 소스 폴더 존재 확인
if [ ! -d "$LOCAL_DATA_DIR" ]; then
    log "오류: data 폴더를 찾을 수 없습니다: ${LOCAL_DATA_DIR}"
    exit 1
fi
if [ ! -d "$LOCAL_DB_DIR" ]; then
    log "오류: db 폴더를 찾을 수 없습니다: ${LOCAL_DB_DIR}"
    exit 1
fi

log "===== WSL -> EC2 rsync 전송 시작 ====="
log "목적지: ${EC2_USER}@${EC2_HOST}:${EC2_BASE_DIR}"

ERROR_COUNT=0

# ----- EC2 목적지 폴더 미리 생성 -----
log "EC2 목적지 폴더 생성 확인 중..."
ssh -i "$PEM_PATH" "${EC2_USER}@${EC2_HOST}" "mkdir -p ${EC2_BASE_DIR}/data ${EC2_BASE_DIR}/db" >> "$LOG_FILE" 2>&1

if [ $? -ne 0 ]; then
    log "오류: EC2 접속 또는 폴더 생성 실패. pem 경로/IP/보안그룹을 확인하세요."
    exit 1
fi

# ----- data 폴더 전송 (하위 폴더 전부 포함) -----
log "data 폴더 전송 중: ${LOCAL_DATA_DIR}/ -> ${EC2_BASE_DIR}/data/"
rsync -avz --info=progress2 -e "ssh -i ${PEM_PATH}" \
    "${LOCAL_DATA_DIR}/" "${EC2_USER}@${EC2_HOST}:${EC2_BASE_DIR}/data/" \
    2>&1 | tee -a "$LOG_FILE"

if [ ${PIPESTATUS[0]} -eq 0 ]; then
    log "data 폴더 전송 완료"
else
    log "data 폴더 전송 중 오류 발생 (재실행하면 이어서 전송됨)"
    ERROR_COUNT=$((ERROR_COUNT + 1))
fi

# ----- db 폴더 전송 -----
log "db 폴더 전송 중: ${LOCAL_DB_DIR}/ -> ${EC2_BASE_DIR}/db/"
rsync -avz --info=progress2 -e "ssh -i ${PEM_PATH}" \
    "${LOCAL_DB_DIR}/" "${EC2_USER}@${EC2_HOST}:${EC2_BASE_DIR}/db/" \
    2>&1 | tee -a "$LOG_FILE"

if [ ${PIPESTATUS[0]} -eq 0 ]; then
    log "db 폴더 전송 완료"
else
    log "db 폴더 전송 중 오류 발생 (재실행하면 이어서 전송됨)"
    ERROR_COUNT=$((ERROR_COUNT + 1))
fi

# ----- 결과 -----
if [ $ERROR_COUNT -eq 0 ]; then
    log "===== 전체 전송 성공 ====="
else
    log "===== 전송 완료 (오류 ${ERROR_COUNT}건 발생, 같은 명령으로 재실행하면 이어서 전송됩니다) ====="
fi

exit $ERROR_COUNT
