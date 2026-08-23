"""공통 테스트 픽스처.

테스트는 MySQL 없이 돌아가야 하므로(CI에도 DB 컨테이너가 없다) 인메모리 SQLite를
쓰고, `get_db` 의존성을 그 세션으로 갈아끼운다. 모델을 SQLite 호환으로 유지하는
장치는 `app/models/types.py` 참고.
"""

from collections.abc import Generator

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.db.session import Base, get_db
from app.main import app as fastapi_app

# 모델을 임포트해야 Base.metadata에 테이블이 등록된다.
from app.models import User  # noqa: F401


@pytest.fixture
def db_session() -> Generator[Session, None, None]:
    """테스트 하나당 비어있는 인메모리 DB 세션 하나."""
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,  # 인메모리 DB를 커넥션 간에 공유하려면 필요하다
    )
    Base.metadata.create_all(engine)
    session_factory = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    session = session_factory()
    try:
        yield session
    finally:
        session.close()
        engine.dispose()


@pytest.fixture
def client(db_session: Session) -> Generator[TestClient, None, None]:
    """`get_db`가 테스트 세션을 쓰도록 갈아끼운 앱 클라이언트."""
    yield from _client_for(fastapi_app, db_session)


def _client_for(app: FastAPI, db_session: Session) -> Generator[TestClient, None, None]:
    app.dependency_overrides[get_db] = lambda: db_session
    try:
        with TestClient(app) as test_client:
            yield test_client
    finally:
        app.dependency_overrides.pop(get_db, None)
