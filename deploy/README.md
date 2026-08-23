# 배포 가이드 (AWS 프리티어)

사릴스 백엔드를 AWS에 올리는 절차입니다. **팀원 프리티어 계정**을 쓰기로 했고(2026-08-24),
기존 프로젝트와 계정 자체가 분리되므로 서로 영향이 없습니다.

## 구성

```
   앱 ──HTTPS──▶ EC2 (nginx → FastAPI 컨테이너)
                   │
                   ├──▶ RDS MySQL 8   (가게·프로젝트 데이터)
                   └──▶ S3            (사진·촬영본·완성 영상)
```

| 리소스 | 사양 | 프리티어 |
|---|---|---|
| EC2 | t3.micro (2vCPU / 1GB) | 750시간/월 |
| RDS | db.t3.micro MySQL 8.0, 20GB | 750시간/월 |
| S3 | 버킷 1개 | 5GB |

> 프리티어 조건은 계정 생성 시점에 따라 다릅니다. **가입 화면에서 현재 조건을 확인**하고,
> Billing → Budgets에 **예산 알림($5 정도)** 을 먼저 걸어두세요. 초과 과금을 늦게 알아채는 게
> 가장 흔한 사고입니다.

---

## 1. RDS 만들기

- 엔진 **MySQL 8.0** (5.7은 마이그레이션에 손볼 게 생깁니다)
- 템플릿 **프리 티어**, 인스턴스 `db.t3.micro`, 스토리지 20GB
- **퍼블릭 액세스: 아니요** — EC2에서만 접근하게 둡니다
- 파라미터 그룹에서 문자셋을 `utf8mb4`로 (한글·이모지가 깨지지 않게)
- 보안 그룹: 인바운드 3306을 **EC2 보안 그룹에서만** 허용

생성 후 DB와 계정을 만듭니다.

```sql
CREATE DATABASE sarils CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
CREATE USER 'sarils'@'%' IDENTIFIED BY '충분히-긴-비밀번호';
GRANT ALL PRIVILEGES ON sarils.* TO 'sarils'@'%';
FLUSH PRIVILEGES;
```

## 2. S3 버킷 만들기

- 리전은 EC2와 같게 (`ap-northeast-2`). 다르면 전송 요금이 붙습니다.
- 이름은 전 세계에서 유일해야 합니다. 예: `sarils-media-prod`
- **CORS 설정** — 앱이 브라우저에서 파일을 읽습니다.

```json
[{
    "AllowedHeaders": ["*"],
    "AllowedMethods": ["GET", "HEAD"],
    "AllowedOrigins": ["*"],
    "ExposeHeaders": []
}]
```

### 공개 버킷 vs 서명 URL — 결정이 필요합니다

| | 설정 | 장점 | 단점 |
|---|---|---|---|
| **공개** | `S3_PRESIGN_EXPIRE_SECONDS=0` + 버킷 공개 읽기 | URL이 안 바뀌어 캐시됨. 간단 | **URL을 아는 사람은 누구나 봅니다** |
| **서명** | `S3_PRESIGN_EXPIRE_SECONDS=3600` + 버킷 비공개 | 버킷을 닫아둘 수 있음 | URL이 매번 바뀌어 캐시 안 됨 |

파일 키에 UUID가 들어가 주소를 추측할 수는 없지만, **사장님 촬영 원본과 가게 내부 사진**이
올라가는 버킷입니다. 시연·개발 중에는 공개로 두고, **실사용자를 받기 전에 서명 URL로 바꾸는 것**을
권합니다. 코드는 설정 한 줄로 전환되므로 나중에 바꿔도 됩니다.

## 3. EC2 만들기

- Ubuntu 22.04 / `t3.micro`
- 보안 그룹 인바운드: **22(내 IP만)**, **80**, **443**. 8000번은 열지 않습니다(nginx가 앞에 섭니다).
- **탄력적 IP를 붙이세요** — 재부팅 때마다 IP가 바뀌면 도메인·OAuth 리다이렉트가 전부 깨집니다.

### IAM 역할 붙이기 (액세스 키 대신)

EC2에 역할을 붙이면 **서버에 키를 두지 않아도** boto3가 알아서 인증합니다. 키 유출 사고가
근본적으로 없어집니다.

1. IAM → 역할 생성 → 신뢰 주체 **EC2**
2. 아래 정책을 인라인으로 붙이고 역할을 EC2에 연결

```json
{
    "Version": "2012-10-17",
    "Statement": [{
        "Effect": "Allow",
        "Action": ["s3:PutObject", "s3:GetObject", "s3:DeleteObject", "s3:ListBucket"],
        "Resource": ["arn:aws:s3:::버킷명", "arn:aws:s3:::버킷명/*"]
    }]
}
```

### 서버 준비

```bash
sudo apt update && sudo apt install -y docker.io docker-compose-v2 git mysql-client awscli
sudo usermod -aG docker ubuntu   # 재로그인 후 적용
git clone https://github.com/skt-flyai-9th/backend.git && cd backend
```

## 4. 도메인과 HTTPS

**SNS OAuth(R16)가 HTTPS를 요구합니다.** 도메인 없이는 인스타그램·유튜브 연동을 붙일 수 없습니다.

1. 도메인의 A 레코드를 EC2 탄력적 IP로 지정
2. `deploy/nginx.conf`의 `sarils.example.com` **3곳**을 실제 도메인으로 교체
3. 인증서 발급 (최초 1회)

```bash
docker run --rm -p 80:80 \
    -v certbot-conf:/etc/letsencrypt -v certbot-www:/var/www/certbot \
    certbot/certbot certonly --standalone -d 실제도메인 --agree-tos -m 메일주소
```

이후 갱신은 `docker-compose.prod.yml`의 certbot 컨테이너가 12시간마다 자동으로 합니다.

## 5. 환경변수

```bash
cp .env.example .env && nano .env
```

배포에서 **반드시 바꿔야 하는 값**입니다.

```bash
DEBUG=false
JWT_SECRET_KEY=              # python -c "import secrets; print(secrets.token_urlsafe(32))"
DB_HOST=xxx.rds.amazonaws.com
DB_PASSWORD=
CORS_ORIGINS=https://실제도메인
STORAGE_BACKEND=s3
S3_BUCKET=sarils-media-prod
MEDIA_BASE_URL=https://실제도메인
```

> `JWT_SECRET_KEY`를 기본값으로 두면 **누구나 토큰을 위조할 수 있습니다.** 반드시 새로 만드세요.
> `.env`는 커밋되지 않습니다(`.gitignore`).

## 6. 띄우기

```bash
docker compose -f docker-compose.prod.yml up -d --build
curl https://실제도메인/health     # {"status":"ok","database":"ok"}
```

컨테이너가 뜰 때 `alembic upgrade head`가 먼저 돌아 테이블이 만들어집니다.

포맷 데이터가 없으면 홈 피드가 비어 보입니다.

```bash
docker compose -f docker-compose.prod.yml exec api python -m scripts.seed_video_formats
```

## 7. 백업

RDS 자동 백업(7일)과 별개로, 하루 한 번 덤프를 S3에 올립니다. 실수로 테이블을 지웠을 때
스냅샷 복원(인스턴스 통째로)보다 훨씬 빠릅니다.

```bash
crontab -e
# 매일 04:00 UTC
0 4 * * * /home/ubuntu/backend/scripts/backup_db.sh >> /var/log/sarils-backup.log 2>&1
```

## 8. 배포 이후

```bash
git pull && docker compose -f docker-compose.prod.yml up -d --build
docker compose -f docker-compose.prod.yml logs -f api      # 로그
```

## 9. 자동 배포 (배포가 안정된 뒤에)

수동 배포가 몇 번 성공하고 나서 붙이는 게 좋습니다. 서버 경로·사용자명이 확정돼야
스크립트가 정확해집니다.

### GitHub Secrets 등록

`Settings → Secrets and variables → Actions`

| Secret | 값 |
|---|---|
| `EC2_HOST` | 서버 IP 또는 도메인 |
| `EC2_USER` | `ubuntu` |
| `EC2_SSH_KEY` | `.pem` 파일 **내용 전체** |

**이 레포는 공개이지만 Secrets는 안전합니다** — 로그에도 `***`로 마스킹됩니다.

### `.github/workflows/deploy.yml`

```yaml
name: deploy

on:
  push:
    branches: [develop]

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
            git pull
            docker compose -f docker-compose.prod.yml up -d --build
```

`develop`에 머지하면 자동으로 배포됩니다.

- **`.env`는 서버에만 둡니다.** Actions가 건드리지 않습니다.
- 빌드가 실패해도 **기존 컨테이너는 그대로 살아 있습니다.** 새 컨테이너만 안 뜹니다.
- 현재 CI는 `pull_request`에만 걸려 있어 **머지 후에는 테스트 없이 배포됩니다.** 배포 전에
  한 번 더 돌리려면 `ci.yml`의 트리거에 `push: branches: [develop]`을 추가하세요.

---

## 프론트에 알려야 할 것

- **API Base URL**: `https://실제도메인` (지금까지 명세서에 없던 값입니다)
- 파일 URL이 `localhost:8000`에서 **S3 주소**로 바뀝니다. 응답의 URL을 그대로 쓰면 됩니다.

## 주의할 점

- **t3.micro는 메모리 1GB입니다.** uvicorn 워커 2개면 충분하지만, 더 늘리면 OOM으로 죽습니다.
- **S3 전송 요금**은 GB당 약 $0.09입니다. 영상 서비스라 사용자가 늘면 여기가 가장 먼저 증가합니다.
- **예산 알림을 먼저 걸어두세요.** 프리티어를 넘겨도 AWS는 막지 않고 그냥 청구합니다.
