#!/bin/bash
#
# FTP -> WSL -> EC2 파일 전송 스크립트
# 대상 폴더: apst, ddr1_log, cml
# 흐름: FTP 서버에서 다운로드 -> WSL 임시 저장 -> EC2로 scp 전송
# 실행 위치: WSL
# 스케줄: 매일 06:00 (cron 또는 Windows 작업 스케줄러)
#

# ============================================
# ▼▼▼ 아래 값들을 환경에 맞게 입력하세요 ▼▼▼
# ============================================

# ----- FTP 서버 정보 -----
FTP_HOST=""          # 예: 192.168.0.10
FTP_USER=""          # FTP 계정
FTP_PASS=""          # FTP 비밀번호

# ----- EC2 접속 정보 -----
EC2_HOST=""          # EC2 퍼블릭 IP
EC2_USER=""          # 예: ubuntu, ec2-user
PEM_PATH=""          # 예: ~/.ssh/키페어.pem

# ----- EC2 목적지 폴더 경로 (각 파일 종류별로 다르게 지정 가능) -----
EC2_APST_DIR=""       # 예: /home/sbdb/data/apst
EC2_DDR1LOG_DIR=""    # 예: /home/sbdb/data/ddr1_log
EC2_CML_DIR=""        # 예: /home/sbdb/data/cml

# ----- WSL 로컬 임시 저장 경로 (수정 불필요, 원하면 변경 가능) -----
LOCAL_TMP="$HOME/ftp_tmp"

# ============================================
# ▲▲▲ 입력 끝 ▲▲▲ (아래는 수정 불필요)
# ============================================

LOG_DIR="$HOME/ftp_transfer_logs"
LOG_FILE="${LOG_DIR}/transfer_$(date +%Y%m%d).log"
mkdir -p "$LOG_DIR"

log() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $1" | tee -a "$LOG_FILE"
}

# 필수값 체크
for VAR in FTP_HOST FTP_USER FTP_PASS EC2_HOST EC2_USER PEM_PATH EC2_APST_DIR EC2_DDR1LOG_DIR EC2_CML_DIR; do
    if [ -z "${!VAR}" ]; then
        log "오류: ${VAR} 값이 비어 있습니다. 스크립트 상단을 채워주세요."
        exit 1
    fi
done

# lftp 설치 확인
if ! command -v lftp &> /dev/null; then
    log "오류: lftp가 설치되어 있지 않습니다. 'sudo apt install lftp'로 설치해주세요."
    exit 1
fi

log "===== FTP -> EC2 전송 시작 ====="

rm -rf "$LOCAL_TMP"
mkdir -p "$LOCAL_TMP/apst" "$LOCAL_TMP/ddr1_log" "$LOCAL_TMP/cml"

ERROR_COUNT=0

# ----- 1단계: FTP에서 3개 폴더 다운로드 -----
FTP_FOLDERS=("apst" "ddr1_log" "cml")

for FOLDER in "${FTP_FOLDERS[@]}"; do
    log "FTP 다운로드 중: /${FOLDER}"
    lftp -u "$FTP_USER","$FTP_PASS" "$FTP_HOST" -e "
        set ssl:verify-certificate no;
        mirror /${FOLDER} $LOCAL_TMP/${FOLDER};
        bye
    " >> "$LOG_FILE" 2>&1

    if [ $? -eq 0 ]; then
        log "FTP 다운로드 완료: ${FOLDER}"
    else
        log "FTP 다운로드 실패: ${FOLDER}"
        ERROR_COUNT=$((ERROR_COUNT + 1))
    fi
done

# ----- 2단계: EC2로 scp 전송 -----
declare -A EC2_TARGETS=(
    ["apst"]="$EC2_APST_DIR"
    ["ddr1_log"]="$EC2_DDR1LOG_DIR"
    ["cml"]="$EC2_CML_DIR"
)

for FOLDER in "${FTP_FOLDERS[@]}"; do
    SRC="$LOCAL_TMP/${FOLDER}"
    DEST="${EC2_TARGETS[$FOLDER]}"

    # 다운로드된 파일이 있는지 확인
    if [ -z "$(ls -A "$SRC" 2>/dev/null)" ]; then
        log "건너뜀: ${FOLDER} - 다운로드된 파일 없음"
        continue
    fi

    log "EC2 전송 중: ${FOLDER} -> ${EC2_USER}@${EC2_HOST}:${DEST}"
    scp -i "$PEM_PATH" -r "$SRC"/* "${EC2_USER}@${EC2_HOST}:${DEST}/" >> "$LOG_FILE" 2>&1

    if [ $? -eq 0 ]; then
        log "EC2 전송 완료: ${FOLDER}"
    else
        log "EC2 전송 실패: ${FOLDER}"
        ERROR_COUNT=$((ERROR_COUNT + 1))
    fi
done

# ----- 결과 -----
if [ $ERROR_COUNT -eq 0 ]; then
    log "===== 전체 작업 성공 ====="
else
    log "===== 작업 완료 (오류 ${ERROR_COUNT}건 발생, 로그 확인 필요) ====="
fi

# 임시 폴더 정리 (필요 없으면 이 줄 주석 처리)
rm -rf "$LOCAL_TMP"

# 30일 지난 로그 삭제
find "$LOG_DIR" -name "transfer_*.log" -mtime +30 -delete

exit $ERROR_COUNT
