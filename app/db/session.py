"""데이터베이스 세션 관리.

SQLAlchemy 2.0 동기(sync) 방식을 사용한다. 비동기 세션은 lazy loading과
트랜잭션 경계에서 함정이 많아, 이 프로젝트 규모에서는 이점보다 비용이 크다고 판단했다.
"""

from collections.abc import Generator

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.core.config import settings

engine = create_engine(
    settings.database_url,
    pool_pre_ping=True,  # 끊긴 커넥션을 미리 걸러낸다
    pool_recycle=3600,  # MySQL 기본 wait_timeout(8h)보다 짧게 재활용
    echo=settings.DEBUG,
)

SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


class Base(DeclarativeBase):
    """모든 ORM 모델의 부모 클래스."""


def get_db() -> Generator[Session, None, None]:
    """FastAPI 의존성. 요청 하나당 세션 하나를 열고 끝나면 닫는다."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
