"""편집 완료 푸시 알림용 디바이스 토큰 등록 테스트."""

from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.push_token import PushToken


def test_register_push_token_creates_row(
    client: TestClient, auth_headers: dict[str, str], db_session: Session
) -> None:
    response = client.post(
        "/users/me/push-tokens",
        json={"push_token": "ExponentPushToken[abc123]", "platform": "ANDROID"},
        headers=auth_headers,
    )

    assert response.status_code == 200, response.text
    saved = db_session.scalar(select(PushToken))
    assert saved is not None
    assert saved.push_token == "ExponentPushToken[abc123]"
    assert saved.platform == "ANDROID"


def test_register_push_token_upserts_by_user(
    client: TestClient, auth_headers: dict[str, str], db_session: Session
) -> None:
    """재설치·재로그인으로 토큰이 바뀌어도 사용자당 한 행만 남는다."""
    client.post(
        "/users/me/push-tokens",
        json={"push_token": "ExponentPushToken[old]", "platform": "ANDROID"},
        headers=auth_headers,
    )
    client.post(
        "/users/me/push-tokens",
        json={"push_token": "ExponentPushToken[new]", "platform": "IOS"},
        headers=auth_headers,
    )

    rows = list(db_session.scalars(select(PushToken)))
    assert len(rows) == 1
    assert rows[0].push_token == "ExponentPushToken[new]"
    assert rows[0].platform == "IOS"


def test_register_push_token_rejects_unknown_platform(
    client: TestClient, auth_headers: dict[str, str]
) -> None:
    response = client.post(
        "/users/me/push-tokens",
        json={"push_token": "ExponentPushToken[abc123]", "platform": "WINDOWS_PHONE"},
        headers=auth_headers,
    )

    assert response.status_code == 422


def test_register_push_token_requires_authentication(client: TestClient) -> None:
    response = client.post(
        "/users/me/push-tokens",
        json={"push_token": "ExponentPushToken[abc123]", "platform": "ANDROID"},
    )

    assert response.status_code == 401
