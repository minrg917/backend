# 배포 가이드 (AWS · 네이티브 systemd)

AWS 인프라는 **2026-08-24에 구축 완료**됐습니다(EC2 / RDS / S3 / IAM). 이 문서는 그 위에
**애플리케이션을 올리는 절차**입니다. 인프라 상세는 팀 내부 문서 `docs/배포정보.md`에 있습니다.

서버에 Python·nginx가 네이티브로 설치돼 있어 **systemd로 돌립니다**(Docker 아님).
컨테이너 구성(`Dockerfile`·`docker-compose.prod.yml`)은 나중을 위해 남겨뒀습니다.

```
   앱 ──HTTPS──▶ EC2 (nginx :443 → uvicorn :8000)
                   │
                   ├──▶ RDS MySQL 8.4   sarils-db
                   └──▶ S3              sarils-s3
```

---

## 1. 코드 내려받기

```bash
ssh -i sarils-backend-key.pem ubuntu@<탄력적IP>

sudo apt update && sudo apt install -y python3-venv mysql-client
git clone https://github.com/skt-flyai-9th/backend.git
cd backend

python3 -m venv .venv
.venv/bin/pip install poetry
.venv/bin/poetry install --without dev
```

> `.venv` 경로는 systemd 유닛(`deploy/sarils-api.service`)에 하드코딩돼 있습니다.
> 다른 곳에 만들면 유닛 파일도 같이 고쳐야 합니다.

## 2. 환경변수

```bash
cp .env.example .env && nano .env
```

**반드시 바꿔야 하는 값**입니다.

```bash
DEBUG=false
LOG_LEVEL=INFO

# python -c "import secrets; print(secrets.token_urlsafe(32))"
JWT_SECRET_KEY=

# RDS 콘솔 → sarils-db → "연결 및 보안"
DB_HOST=sarils-db.xxxxx.ap-northeast-2.rds.amazonaws.com
DB_USER=admin
DB_PASSWORD=
DB_NAME=sarils

CORS_ORIGINS=https://sarils.p-e.kr

STORAGE_BACKEND=s3
S3_BUCKET=sarils-s3
S3_REGION=ap-northeast-2
MEDIA_BASE_URL=https://sarils.p-e.kr
SNS_REDIRECT_BASE_URL=https://sarils.p-e.kr

# **비워둡니다.** EC2에 IAM 역할(sarils-ec2-role)이 붙어 있어 boto3가 알아서 찾습니다.
AWS_ACCESS_KEY_ID=
AWS_SECRET_ACCESS_KEY=
```

> `JWT_SECRET_KEY`를 기본값으로 두면 **누구나 토큰을 위조할 수 있습니다.**
> `.env`는 커밋되지 않습니다(`.gitignore`) — 공개 레포라 특히 중요합니다.

## 3. 서비스 등록

```bash
sudo cp deploy/sarils-api.service /etc/systemd/system/
sudo cp deploy/sarils-trend-sync.service deploy/sarils-trend-sync.timer /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now sarils-api
sudo systemctl enable --now sarils-trend-sync.timer

systemctl status sarils-api
curl http://127.0.0.1:8000/health      # {"status":"ok","database":"ok"}
```

서비스가 뜰 때 `alembic upgrade head`가 먼저 돌아 테이블이 만들어집니다. **마이그레이션이
실패하면 서비스가 뜨지 않습니다** — 스키마가 어긋난 채 요청을 받는 것보다 낫습니다.

로그는 `journalctl -u sarils-api -f`로 봅니다.

트렌드 포맷은 AI 서버에서 하루 한 번 자동 동기화됩니다(`GET /api/v1/challenges`는 AI
내부 Trend Store를 읽기만 할 뿐 새로 갱신시키지 않으므로, 이 주기는 AI가 갱신한 결과를
우리가 얼마나 늦게 알아채느냐만 결정합니다 — 2026-08-26). 즉시 동기화하거나 최근 실행을
확인할 때는 아래 명령을 사용합니다.

```bash
sudo systemctl start sarils-trend-sync.service
systemctl list-timers sarils-trend-sync.timer
journalctl -u sarils-trend-sync.service -n 50
```

## 4. nginx + 도메인 + HTTPS

**SNS 연동(R16)이 HTTPS를 요구합니다.** 특히 **Meta는 `http://`를 아예 거부**합니다.

1. 도메인의 A 레코드를 EC2 **탄력적 IP**로 지정
2. `deploy/nginx.conf`의 `sarils.example.com`을 실제 도메인으로 교체
3. 설정 적용

```bash
sudo cp deploy/nginx.conf /etc/nginx/sites-available/sarils
sudo ln -sf /etc/nginx/sites-available/sarils /etc/nginx/sites-enabled/sarils
sudo rm -f /etc/nginx/sites-enabled/default
sudo nginx -t && sudo systemctl reload nginx
```

4. 인증서 발급 — **certbot이 nginx 설정을 자동으로 고쳐줍니다**

```bash
sudo apt install -y certbot python3-certbot-nginx
sudo certbot --nginx -d sarils.p-e.kr
```

갱신은 certbot이 설치한 타이머가 알아서 합니다(`systemctl list-timers | grep certbot`).

5. **보안 그룹에서 8000 포트 규칙을 제거**합니다. nginx가 앞에 섰으니 직접 열어둘 이유가 없습니다.

## 4.5. (선택) 가게 자동 메뉴 수집용 Chrome 설치

가게 등록 시 카카오맵에서 대표 메뉴 몇 개를 자동으로 가져오는 기능이 있다(2026-08-24
추가). **안 해도 API는 정상 동작한다** — 이 단계를 건너뛰면 메뉴 자동 수집만 조용히
꺼진 채로 돌고, 사장님은 3.2로 직접 입력하면 된다.

```bash
sudo apt install -y chromium-browser
.venv/bin/poetry install --without dev --with crawler
```

`--with crawler`가 `selenium`·`webdriver-manager`를 이 프로젝트의 `.venv`에 설치한다.
API 프로세스가 백그라운드 작업에서 이 인터프리터(`sys.executable`)로 크롤링 스크립트를
서브프로세스로 띄우기 때문에, **같은 가상환경에 설치돼 있어야** 인식한다.

자세한 설계는 `docs/IMPLEMENTATION.md`의 2026-08-24 항목 참고.

## 5. 초기 데이터

포맷이 없으면 홈 피드가 비어 보입니다.

```bash
.venv/bin/python -m scripts.seed_video_formats
```

## 6. SNS 콘솔에 콜백 주소 추가

`.env`의 `SNS_REDIRECT_BASE_URL`과 **정확히 같은 값**을 등록해야 합니다. 슬래시 하나만
달라도 플랫폼이 리다이렉트를 거부합니다.

```
https://sarils.p-e.kr/sns-connections/callback
```

- **Google Cloud Console** → 사용자 인증 정보 → OAuth 클라이언트 → 승인된 리디렉션 URI에 **추가**
  (기존 `http://localhost:8000/...`은 지우지 말고 두면 로컬 개발도 계속 됩니다)
- **Meta 앱 대시보드** → 유효한 OAuth 리디렉션 URI

## 7. 백업

RDS 자동 백업(1일)과 별개로 하루 한 번 덤프를 S3에 올립니다. 실수로 테이블을 지웠을 때
스냅샷 복원(인스턴스 통째로)보다 훨씬 빠릅니다.

```bash
crontab -e
# 매일 04:00 UTC
0 4 * * * /home/ubuntu/backend/scripts/backup_db.sh >> /var/log/sarils-backup.log 2>&1
```

## 8. 배포 이후

```bash
cd ~/backend
git fetch origin main && git checkout main && git reset --hard origin/main
.venv/bin/poetry install --without dev      # 의존성이 바뀐 경우만
sudo systemctl restart sarils-api           # 마이그레이션은 자동으로 돈다
```

이 레포의 GitHub 기본 브랜치가 `develop`이라, 서버를 처음 `git clone`하면 로컬 체크아웃이
`develop`을 보게 된다. 배포는 항상 `main` 기준이므로 브랜치를 명시적으로 지정해야 한다 — 그냥
`git pull`을 쓰면 체크아웃된 브랜치(develop)를 당겨서 실제 배포 코드가 어긋날 수 있다
(2026-08-26 첫 자동배포 로그에서 발견).

## 9. 자동 배포 (수동 배포가 몇 번 성공한 뒤에)

### GitHub Secrets

`Settings → Secrets and variables → Actions`

| Secret | 값 |
|---|---|
| `EC2_HOST` | 탄력적 IP 또는 도메인 |
| `EC2_USER` | `ubuntu` |
| `EC2_SSH_KEY` | `sarils-backend-key.pem` **내용 전체** |

**이 레포는 공개이지만 Secrets는 안전합니다** — 로그에도 `***`로 마스킹됩니다.

### `.github/workflows/deploy.yml`

```yaml
name: deploy

on:
  push:
    branches: [main]

jobs:
  deploy:
    runs-on: ubuntu-latest
    steps:
      - uses: appleboy/ssh-action@v1
        with:
          host: ${{ secrets.EC2_HOST }}
          username: ${{ secrets.EC2_USER }}
          key: ${{ secrets.EC2_SSH_KEY }}
          script: |
            cd ~/backend
            git fetch origin main
            git checkout main
            git reset --hard origin/main
            .venv/bin/poetry install --without dev
            sudo install -m 0644 deploy/sarils-trend-sync.service /etc/systemd/system/
            sudo install -m 0644 deploy/sarils-trend-sync.timer /etc/systemd/system/
            sudo systemctl daemon-reload
            sudo systemctl restart sarils-api
            sudo systemctl enable sarils-trend-sync.timer
            sudo systemctl restart sarils-trend-sync.timer
```

`sarils-api`를 먼저 재시작해 마이그레이션을 끝낸 뒤 트렌드 동기화 타이머를 켠다 —
순서가 반대면 여기서 트리거하는 첫 실행이 아직 없는 컬럼을 찾다가 실패한다
(2026-08-25 PR #70 첫 배포에서 발견).

`enable --now` 대신 `enable` + `restart`로 나눈 이유(2026-08-26): `enable --now`는
이미 떠 있는 타이머엔 아무 효과가 없어서, 주기(`OnUnitActiveSec`)를 바꿔도 재배포만으로는
새 스케줄이 반영되지 않았다. `restart`로 확실히 새 스케줄을 반영한다.

`main`에 push될 때만 배포한다 — `develop`이 아니다. feature/fix는 `develop`으로 계속
쌓이고, `develop → main` PR을 머지하는 "배포 시점"에만 실서버가 갱신된다. `git pull` 대신
브랜치를 명시하는 이유는 위 "8. 배포 이후" 참고.

`sudo systemctl restart`가 비밀번호 없이 되도록 sudoers에 한 줄이 필요합니다.

```bash
sudo tee /etc/sudoers.d/sarils-deploy > /dev/null <<'EOF'
ubuntu ALL=(ALL) NOPASSWD: /bin/systemctl restart sarils-api
ubuntu ALL=(ALL) NOPASSWD: /usr/bin/install -m 0644 deploy/sarils-trend-sync.service /etc/systemd/system/
ubuntu ALL=(ALL) NOPASSWD: /usr/bin/install -m 0644 deploy/sarils-trend-sync.timer /etc/systemd/system/
ubuntu ALL=(ALL) NOPASSWD: /bin/systemctl daemon-reload
ubuntu ALL=(ALL) NOPASSWD: /bin/systemctl enable sarils-trend-sync.timer
ubuntu ALL=(ALL) NOPASSWD: /bin/systemctl restart sarils-trend-sync.timer
EOF
sudo chmod 0440 /etc/sudoers.d/sarils-deploy
sudo visudo -c
```

배포 스크립트가 새 `sudo` 명령을 쓸 때마다 여기에 한 줄씩 추가해야 한다 — 화이트리스트에
없는 명령은 비밀번호를 요구하다 자동배포가 그대로 실패한다(2026-08-25 PR #69 배포 때
발견). `sudoers.d` 파일은 **권한이 정확히 `0440`이어야** `visudo`가 읽는다 — `cp`로 덮어쓰면
기본 권한(`0644`)이 돼서 통째로 무시된다.

- **`.env`는 서버에만 둡니다.** Actions가 건드리지 않습니다.
- 현재 CI는 `pull_request`에만 걸려 있어 **머지 후에는 테스트 없이 배포됩니다.**
  배포 전에 한 번 더 돌리려면 `ci.yml` 트리거에 `push: branches: [develop]`을 추가하세요.

---

## 프론트에 알려야 할 것

- **API Base URL**: `https://sarils.p-e.kr` — 지금까지 명세서에 없던 값입니다
- 파일 URL이 **S3 주소**로 바뀝니다. 응답의 URL을 그대로 쓰면 됩니다

## 주의할 점

- **t3.small은 메모리 2GB입니다.** uvicorn 워커 2개면 충분하지만 더 늘리면 OOM으로 죽습니다.
- **S3 전송 요금**은 GB당 약 $0.09입니다. 영상 서비스라 사용자가 늘면 여기가 가장 먼저 증가합니다.
- **S3 버킷이 퍼블릭 읽기**입니다(`sarils-s3`). 키에 UUID가 들어가 주소를 추측할 수는 없지만,
  사장님 촬영 원본과 가게 내부 사진이 올라갑니다. **실사용자를 받기 전에**
  `S3_PRESIGN_EXPIRE_SECONDS=3600`으로 바꾸고 버킷을 비공개로 돌리는 것을 권합니다.
- **Billing → Budgets에 예산 알림**을 걸어두세요. 프리티어를 넘겨도 AWS는 막지 않고 청구합니다.
