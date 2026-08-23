#!/usr/bin/env bash
# RDS를 덤프해 S3에 올린다. cron으로 하루 한 번 돌린다.
#
#   0 4 * * * /home/ubuntu/backend/scripts/backup_db.sh >> /var/log/sarils-backup.log 2>&1
#
# RDS 자동 백업(기본 7일 보관)이 있어도 이걸 두는 이유는, 실수로 테이블을 지웠을 때
# 스냅샷 복원(인스턴스 통째로)보다 덤프 파일 하나를 되돌리는 게 훨씬 빠르기 때문이다.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "${SCRIPT_DIR}/.."

# shellcheck disable=SC1091
set -a && source .env && set +a

: "${S3_BUCKET:?S3_BUCKET이 .env에 없습니다}"

STAMP="$(date -u +%Y%m%d-%H%M%S)"
FILE="/tmp/sarils-${STAMP}.sql.gz"

echo "[$(date -u)] 덤프 시작: ${DB_NAME}@${DB_HOST}"
# 비밀번호를 --password= 로 넘기지 않는다 — 명령줄 인자는 같은 서버의 다른 사용자에게
# `ps` 로 그대로 보인다. MYSQL_PWD 환경변수는 프로세스 목록에 노출되지 않는다.
MYSQL_PWD="${DB_PASSWORD}" mysqldump \
    --host="${DB_HOST}" --port="${DB_PORT}" \
    --user="${DB_USER}" \
    --single-transaction --quick --routines --triggers \
    --default-character-set=utf8mb4 \
    "${DB_NAME}" | gzip > "${FILE}"

echo "[$(date -u)] 업로드: s3://${S3_BUCKET}/backups/"
aws s3 cp "${FILE}" "s3://${S3_BUCKET}/backups/$(basename "${FILE}")"
rm -f "${FILE}"

echo "[$(date -u)] 완료"
