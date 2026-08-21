"""공통 에러 응답 포맷과 인증 의존성 테스트.

R01 이후 라우터가 붙기 전이라, 테스트 전용 미니 앱에 엔드포인트를 만들어 검증한다.
"""

from collections.abc import Generator

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.api.deps import CurrentUser
from app.core.error_handlers import register_error_handlers
from app.core.exceptions import ConflictError
from app.core.security import create_access_token, create_refresh_token
from app.db.session import get_db
from app.models.user import User
from app.schemas.common import BaseSchema


class _SignupBody(BaseSchema):
    email: str
    password: str


def _build_app() -> FastAPI:
    app = FastAPI()
    register_error_handlers(app)

    @app.get("/_test/protected")
    def protected(user: CurrentUser) -> dict[str, int]:
        return {"user_id": user.id}

    @app.get("/_test/conflict")
    def conflict() -> None:
        raise ConflictError("이미 가입된 이메일입니다.", error_code="EMAIL_ALREADY_EXISTS")

    @app.post("/_test/validate")
    def validate(body: _SignupBody) -> dict[str, str]:
        return {"email": body.email}

    @app.get("/_test/boom")
    def boom() -> None:
        raise RuntimeError("내부 구현 디테일이 노출되면 안 된다")

    return app


@pytest.fixture
def client(db_session: Session) -> Generator[TestClient, None, None]:
    app = _build_app()
    app.dependency_overrides[get_db] = lambda: db_session
    # raise_server_exceptions=False: 처리되지 않은 예외도 실제 서버처럼 500 응답으로 받는다.
    with TestClient(app, raise_server_exceptions=False) as test_client:
        yield test_client


@pytest.fixture
def active_user(db_session: Session) -> User:
    user = User(email="boss01@example.com", name="김사장", terms_agreed=True)
    db_session.add(user)
    db_session.commit()
    return user


def test_app_error_uses_common_format(client: TestClient) -> None:
    response = client.get("/_test/conflict")

    assert response.status_code == 409
    assert response.json() == {
        "error_code": "EMAIL_ALREADY_EXISTS",
        "message": "이미 가입된 이메일입니다.",
    }


def test_unknown_path_uses_common_format(client: TestClient) -> None:
    response = client.get("/_test/does-not-exist")

    assert response.status_code == 404
    assert response.json() == {
        "error_code": "NOT_FOUND",
        "message": "요청한 경로를 찾을 수 없습니다.",
    }


def test_validation_error_uses_common_format(client: TestClient) -> None:
    response = client.post("/_test/validate", json={"email": "boss01@example.com"})

    body = response.json()
    assert response.status_code == 422
    assert body["error_code"] == "VALIDATION_ERROR"
    assert "password" in body["message"]


def test_unexpected_error_does_not_leak_internals(client: TestClient) -> None:
    response = client.get("/_test/boom")

    assert response.status_code == 500
    assert response.json() == {
        "error_code": "INTERNAL_ERROR",
        "message": "서버 오류가 발생했습니다.",
    }


def test_protected_endpoint_requires_authorization_header(client: TestClient) -> None:
    response = client.get("/_test/protected")

    assert response.status_code == 401
    assert response.json()["error_code"] == "AUTHENTICATION_REQUIRED"


def test_protected_endpoint_rejects_refresh_token(client: TestClient, active_user: User) -> None:
    token = create_refresh_token(active_user.id).token

    response = client.get("/_test/protected", headers={"Authorization": f"Bearer {token}"})

    assert response.status_code == 401
    assert response.json()["error_code"] == "INVALID_TOKEN"


def test_protected_endpoint_rejects_inactive_user(
    client: TestClient, active_user: User, db_session: Session
) -> None:
    active_user.is_active = False
    db_session.commit()
    token = create_access_token(active_user.id).token

    response = client.get("/_test/protected", headers={"Authorization": f"Bearer {token}"})

    assert response.status_code == 401
    assert response.json()["error_code"] == "INACTIVE_USER"


def test_protected_endpoint_accepts_valid_access_token(
    client: TestClient, active_user: User
) -> None:
    token = create_access_token(active_user.id).token

    response = client.get("/_test/protected", headers={"Authorization": f"Bearer {token}"})

    assert response.status_code == 200
    assert response.json() == {"user_id": active_user.id}
