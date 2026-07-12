# SB 송출 관리 (광주MBC)

방송 SB(스테이션 브레이크) 송출 내역을 적재·조회·집계하고 각종 운행표/리포트를
생성하는 웹 애플리케이션.

- **백엔드**: FastAPI + SQLite (`server/`)
- **프론트엔드**: React + Vite + Ant Design (`client/`)
- **데이터 소스**: APST(자동송출) · DDR1 로그(수동송출) · CML(클립ID→소재명 매핑)

자세한 사양은 [`requirements.md`](requirements.md) · [`design.md`](design.md) · [`tasks.md`](tasks.md),
파일 포맷은 [`spec_01_apst_format.md`](spec_01_apst_format.md) 등을 참고.

---

## 주요 기능
- 대시보드 / 달력 / 상세조회 / 송출내역 출력(방송운행표·월 리포트·일일 운행표 등)
- 공익/재난 소재 분류 및 월별·흘림자막 송출내역(엑셀·PDF·Word)
- FTP 자동 파일 수집(예약 시각) 또는 폴더 실시간 감시(둘 중 하나)
- 근무자 수동입력 / 공익·재난 키워드 편집
- 접근 IP 대역 제한, 관리자·근무자 로그인

---

## 로컬 개발 (WSL/Ubuntu)

```bash
# 백엔드
cd server
python3 -m venv ../venv && source ../venv/bin/activate
pip install -r ../requirements.txt
uvicorn main:app --reload --host 0.0.0.0 --port 8000

# 프론트엔드 (다른 터미널)
cd client
npm install
npm run dev        # 개발 서버 (http://localhost:5173, /api → :8000 프록시)
```

---

## EC2(Amazon Linux) 배포

배포용 스크립트 3개가 있습니다. 저장소가 public이므로 raw로 받아 실행합니다.

### 1) 최초 셋업 — `setup_ec2.sh`
패키지 설치 → 소스 clone/pull → 백엔드(venv+pip) → 프론트(npm build) → 접근제한 IP 초기화.
```bash
curl -fsSL https://raw.githubusercontent.com/hhyhappyman/sbdb/main/setup_ec2.sh -o setup_ec2.sh
bash setup_ec2.sh
```

### 2) 부팅 자동 시작 — `install_service.sh` (권장)
systemd 서비스로 등록해 부팅 시 자동 시작 + 크래시 자동 복구.
```bash
cd ~/sbdb
bash install_service.sh            # 등록 + 시작 + 부팅 자동시작
bash install_service.sh uninstall  # 등록 해제
```
| 작업 | 명령 |
|------|------|
| 상태 | `sudo systemctl status sbdb` |
| 로그 | `journalctl -u sbdb -f` |
| 재시작 | `sudo systemctl restart sbdb` |
| 중지 | `sudo systemctl stop sbdb` |

### 2-대안) 수동 실행 — `run_server.sh`
systemd 없이 직접 띄울 때.
```bash
cd ~/sbdb
bash run_server.sh        # 포그라운드 (Ctrl+C 종료)
bash run_server.sh bg     # 백그라운드 (로그: server.log)
bash run_server.sh stop   # 백그라운드 종료
```

### 코드 업데이트 후
```bash
cd ~/sbdb && git pull
cd client && npm run build && cd ..
sudo systemctl restart sbdb      # (run_server.sh 사용 시: bash run_server.sh stop && bash run_server.sh bg)
```

---

## GitHub 업로드 (로컬 → 원격)

`upload_to_github.sh` 상단에 GitHub 아이디/저장소/토큰을 넣고 실행하면 커밋+푸시.
```bash
bash upload_to_github.sh
```
> 이 스크립트는 토큰을 포함하므로 `.gitignore`로 제외되어 GitHub에 올라가지 않습니다.

---

## 배포 시 확인 사항
1. **보안 그룹**: EC2 인바운드에서 서비스 포트(기본 `8000`) 열기
2. **접근 제한 IP**: 새 DB는 기본값이 사내망(`218.237.3.0/24`)이라 외부 접속이 막힐 수 있음.
   `setup_ec2.sh`가 최초 `0.0.0.0`(전체 허용)으로 열어두며, 이후 환경설정에서 좁힐 것
3. **환경설정 재입력**: `apst_dir` / `ddr1_dir` / `cml_path` / FTP 정보 등을 EC2 기준 경로로 입력
4. **데이터 파일**: DB·APST/DDR1/CML 원본은 GitHub에 없음(`.gitignore` 제외) → 별도 업로드 필요

---

## .gitignore 로 제외되는 것 (업로드 안 됨)
- `venv/`, `client/node_modules/`, `client/dist/`
- `db/`, `*.db` (방송 데이터·설정·비밀번호 포함)
- `data/`, `reports/`
- `upload_to_github.sh` (토큰 포함)
