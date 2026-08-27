# 빌드 단계 — 의존성만 설치한다. 런타임 이미지에 Poetry·빌드 도구를 남기지 않기 위함이다.
FROM python:3.12-slim AS builder

ENV PIP_NO_CACHE_DIR=1 \
    POETRY_VERSION=2.1.1 \
    POETRY_VIRTUALENVS_IN_PROJECT=true \
    POETRY_NO_INTERACTION=1

WORKDIR /app

RUN pip install "poetry==${POETRY_VERSION}"

# 의존성 파일만 먼저 복사한다 — 소스가 바뀌어도 이 레이어는 캐시가 살아 있어 빌드가 빠르다.
COPY pyproject.toml poetry.lock ./
RUN poetry install --without dev --no-root


# 런타임 단계
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH="/app/.venv/bin:$PATH"

WORKDIR /app

# curl은 헬스체크, ffmpeg는 최종 영상 커버 프레임 추출에 쓴다.
RUN apt-get update \
    && apt-get install -y --no-install-recommends curl ffmpeg \
    && rm -rf /var/lib/apt/lists/*

COPY --from=builder /app/.venv /app/.venv
COPY alembic.ini ./
COPY migrations ./migrations
COPY app ./app

# root로 돌리지 않는다 — 컨테이너가 뚫려도 할 수 있는 일이 줄어든다.
RUN useradd --create-home --uid 1000 sarils && chown -R sarils:sarils /app
USER sarils

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD curl -fsS http://localhost:8000/health || exit 1

# 워커 수는 EC2 코어 수에 맞춘다. 프리티어 t3.micro(2vCPU/1GB)에서는 2가 상한이다 —
# 워커마다 앱이 통째로 메모리에 올라가므로 더 늘리면 OOM으로 죽는다.
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "2"]
