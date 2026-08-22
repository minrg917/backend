# 사릴스(SARILS) — Backend

FLY AI 열정 2조. 소상공인이 AI의 도움을 받아 숏폼(릴스/쇼츠) 영상을 **기획 → 촬영 → 편집 → 게시**까지 혼자 끝낼 수 있게 해주는 서비스의 백엔드 레포지토리입니다.

## 기술 스택

| 구분 | 사용 기술 |
| --- | --- |
| 언어 | Python 3.12 |
| 프레임워크 | FastAPI |
| DB | MySQL 8 (로컬은 Docker) |


## 로컬 실행

**필요한 것**: Python 3.12, [Poetry](https://python-poetry.org/docs/#installation), Docker

```bash
# 1) 환경변수 파일 준비
cp .env.example .env
# 로컬 3306 포트가 이미 사용 중이면 .env 의 DB_PORT 를 3307 등으로 바꾼다.

# 2) 의존성 설치
poetry install

# 3) MySQL 컨테이너 기동
docker compose up -d

# 4) DB 스키마 반영
poetry run alembic upgrade head

# 5) 서버 실행
poetry run uvicorn app.main:app --reload
```

| 주소 | 설명 |
| --- | --- |
| http://localhost:8000/health | 헬스체크 (서버 + DB 연결 상태) |
| http://localhost:8000/docs | Swagger UI |
| http://localhost:8000/redoc | ReDoc |

**코드 검사**

```bash
poetry run ruff check .      # 린트
poetry run ruff format .     # 포맷
poetry run pytest            # 테스트
```

## 프로젝트 구조

```
app/
├── main.py              FastAPI 진입점 (CORS, 라우터 등록)
├── core/config.py       환경변수 기반 설정
├── db/session.py        DB 엔진·세션·Base
├── api/
│   ├── router.py        전체 라우터 집합
│   └── routers/         도메인별 라우터
├── models/              SQLAlchemy 모델
└── schemas/             Pydantic 요청·응답 스키마
migrations/              Alembic 마이그레이션
tests/                   pytest
```


## 기여 방법

브랜치 전략·커밋 규칙·이슈/PR 흐름은 [.github/CONTRIBUTING.md](.github/CONTRIBUTING.md)를 따릅니다.

```
이슈 등록 → feature/{이슈번호}-{작업내용} 브랜치 → 작업 → develop으로 PR → 리뷰 1명 승인 → Squash merge
```

`main`과 `develop`은 직접 push가 금지되어 있습니다.
