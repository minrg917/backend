"""SNS 연동·게시 테스트 (API명세서 16.1 연동 / 16.2 게시 / 16.3 연결확정)."""

from typing import Any
from urllib.parse import parse_qs, urlparse

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.core.security import create_oauth_state
from app.models.shorts_project import ShortsProject
from app.models.video_output import RenderStatus, VideoOutput
from app.services import sns_oauth

STORE_BODY: dict[str, Any] = {
    "name": "행복분식",
    "category": "분식",
    "address": "서울 강남구 테헤란로 1길 10",
}


@pytest.fixture(autouse=True)
def sns_keys(monkeypatch: pytest.MonkeyPatch) -> None:
    """연동 키가 채워진 상태로 둔다. 실제 `.env` 값에 테스트가 좌우되면 안 된다."""
    from app.core import config

    monkeypatch.setattr(config.settings, "INSTAGRAM_CLIENT_ID", "ig-id")
    monkeypatch.setattr(config.settings, "INSTAGRAM_CLIENT_SECRET", "ig-secret")
    monkeypatch.setattr(config.settings, "YOUTUBE_CLIENT_ID", "yt-id")
    monkeypatch.setattr(config.settings, "YOUTUBE_CLIENT_SECRET", "yt-secret")
    monkeypatch.setattr(config.settings, "SNS_REDIRECT_BASE_URL", "https://api.example.com")


@pytest.fixture
def store_id(client: TestClient, auth_headers: dict[str, str]) -> int:
    return client.post("/stores", json=STORE_BODY, headers=auth_headers).json()["id"]


@pytest.fixture
def output_id(db_session: Session, store_id: int) -> int:
    project = ShortsProject(store_id=store_id, promotion_purpose="메뉴소개")
    db_session.add(project)
    db_session.flush()
    output = VideoOutput(shorts_project_id=project.id, render_status=RenderStatus.COMPLETED)
    db_session.add(output)
    db_session.commit()
    db_session.refresh(output)
    return output.id


@pytest.fixture
def other_headers(client: TestClient) -> dict[str, str]:
    client.post(
        "/auth/signup",
        json={
            "email": "other@example.com",
            "password": "sarils1234!",
            "name": "다른사장",
            "terms_agreed": True,
        },
    )
    login = client.post(
        "/auth/login", json={"email": "other@example.com", "password": "sarils1234!"}
    )
    return {"Authorization": f"Bearer {login.json()['access_token']}"}


# ---------------------------------------------------------------- 16.1 연동 시작


def test_authorize_returns_platform_url(client: TestClient, auth_headers: dict[str, str]) -> None:
    response = client.get("/sns-connections/authorize?platform=INSTAGRAM", headers=auth_headers)

    assert response.status_code == 200, response.text
    url = response.json()["authorize_url"]
    assert url.startswith("https://www.instagram.com/oauth/authorize")

    params = parse_qs(urlparse(url).query)
    assert params["client_id"] == ["ig-id"]
    assert params["response_type"] == ["code"]
    assert params["redirect_uri"] == ["https://api.example.com/sns-connections/callback"]
    assert params["state"]


def test_authorize_never_leaks_client_secret(
    client: TestClient, auth_headers: dict[str, str]
) -> None:
    """App Secret이 앱으로 나가면 디컴파일로 꺼낼 수 있다 (2026-08-23 구조 변경 이유)."""
    body = client.get("/sns-connections/authorize?platform=INSTAGRAM", headers=auth_headers).text

    assert "ig-secret" not in body


def test_youtube_requests_refresh_token(client: TestClient, auth_headers: dict[str, str]) -> None:
    """구글은 access_type=offline이 없으면 refresh_token을 주지 않는다."""
    url = client.get("/sns-connections/authorize?platform=YOUTUBE", headers=auth_headers).json()[
        "authorize_url"
    ]

    params = parse_qs(urlparse(url).query)
    assert params["access_type"] == ["offline"]
    assert params["prompt"] == ["consent"]


def test_authorize_rejects_unsupported_platform(
    client: TestClient, auth_headers: dict[str, str]
) -> None:
    """연동은 인스타·유튜브만 (2026-08-24 확정)."""
    response = client.get("/sns-connections/authorize?platform=TIKTOK", headers=auth_headers)

    assert response.status_code == 422


def test_authorize_blocks_when_key_missing(
    client: TestClient, auth_headers: dict[str, str], monkeypatch: pytest.MonkeyPatch
) -> None:
    """키 없이 URL을 만들면 사장님이 플랫폼 화면까지 갔다가 실패한다 — 시작에서 막는다."""
    from app.core import config

    monkeypatch.setattr(config.settings, "INSTAGRAM_CLIENT_ID", "")

    response = client.get("/sns-connections/authorize?platform=INSTAGRAM", headers=auth_headers)

    assert response.status_code == 503
    assert response.json()["error_code"] == "SNS_NOT_CONFIGURED"


def test_authorize_requires_authentication(client: TestClient) -> None:
    assert client.get("/sns-connections/authorize?platform=INSTAGRAM").status_code == 401


# ---------------------------------------------------------------- 16.1 콜백


def _user_id(client: TestClient, headers: dict[str, str]) -> int:
    """콜백은 `state`에 담긴 사용자에게 연동을 붙인다 — 그 대상을 실제 계정에서 얻는다."""
    return client.get("/users/me", headers=headers).json()["id"]


def _fake_tokens(**kwargs: Any) -> sns_oauth.OAuthTokens:
    return sns_oauth.OAuthTokens(
        access_token=kwargs.get("access_token", "token-abc"),
        refresh_token=kwargs.get("refresh_token"),
        expires_in=kwargs.get("expires_in"),
        account_name=kwargs.get("account_name", "happy_bunsik"),
    )


def test_callback_saves_connection(
    client: TestClient, auth_headers: dict[str, str], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(sns_oauth, "exchange_code", lambda *a, **k: _fake_tokens(expires_in=3600))
    state = create_oauth_state(_user_id(client, auth_headers), "INSTAGRAM")
    response = client.get(f"/sns-connections/callback?code=abc&state={state}")

    assert response.status_code == 200
    assert "연결됐습니다" in response.text

    body = client.get("/sns-connections", headers=auth_headers).json()
    assert body["connections"][0]["sns_platform"] == "INSTAGRAM"
    assert body["connections"][0]["sns_account_name"] == "happy_bunsik"
    assert body["connections"][0]["token_expires_at"].endswith("Z")


def test_callback_reconnect_updates_instead_of_duplicating(
    client: TestClient,
    auth_headers: dict[str, str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """재연동은 토큰 만료·권한 철회 후 흔하다. 행이 쌓이면 어느 토큰을 쓸지 알 수 없다."""
    monkeypatch.setattr(sns_oauth, "exchange_code", lambda *a, **k: _fake_tokens())
    state = create_oauth_state(_user_id(client, auth_headers), "INSTAGRAM")

    client.get(f"/sns-connections/callback?code=abc&state={state}")
    client.get(f"/sns-connections/callback?code=def&state={state}")

    body = client.get("/sns-connections", headers=auth_headers).json()
    assert len(body["connections"]) == 1


def test_callback_shows_page_on_denial(client: TestClient) -> None:
    """동의를 거부해도 빈 화면이 아니라 안내를 보여준다 (FE 합의, 2026-08-23)."""
    response = client.get("/sns-connections/callback?error=access_denied")

    assert response.status_code == 400
    assert "실패" in response.text
    assert "다시 시도" in response.text


def test_callback_rejects_forged_state(client: TestClient) -> None:
    """state는 CSRF 방지 값이다 — 위조되면 남의 계정에 내 SNS가 붙을 수 있다."""
    response = client.get("/sns-connections/callback?code=abc&state=forged")

    assert response.status_code == 400
    assert "실패" in response.text


def test_callback_needs_no_authentication(client: TestClient) -> None:
    """플랫폼이 리다이렉트하는 요청이라 우리 액세스 토큰이 실려 오지 않는다."""
    response = client.get("/sns-connections/callback?error=denied")

    assert response.status_code != 401


# ---------------------------------------------------------------- 16.1 목록 / 해제


def test_connection_list_is_empty_at_first(
    client: TestClient, auth_headers: dict[str, str]
) -> None:
    assert client.get("/sns-connections", headers=auth_headers).json()["connections"] == []


def test_disconnect_removes_connection(
    client: TestClient,
    auth_headers: dict[str, str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(sns_oauth, "exchange_code", lambda *a, **k: _fake_tokens())
    state = create_oauth_state(_user_id(client, auth_headers), "INSTAGRAM")
    client.get(f"/sns-connections/callback?code=abc&state={state}")
    connection_id = client.get("/sns-connections", headers=auth_headers).json()["connections"][0][
        "id"
    ]

    response = client.delete(f"/sns-connections/{connection_id}", headers=auth_headers)

    assert response.status_code == 200
    assert client.get("/sns-connections", headers=auth_headers).json()["connections"] == []


def test_disconnect_keeps_publish_history(
    client: TestClient,
    auth_headers: dict[str, str],
    db_session: Session,
    monkeypatch: pytest.MonkeyPatch,
    output_id: int,
) -> None:
    """연동을 끊었다고 "이 영상을 올렸다"는 사실이 사라지지는 않는다."""
    monkeypatch.setattr(sns_oauth, "exchange_code", lambda *a, **k: _fake_tokens())
    state = create_oauth_state(_user_id(client, auth_headers), "INSTAGRAM")
    client.get(f"/sns-connections/callback?code=abc&state={state}")
    connection_id = client.get("/sns-connections", headers=auth_headers).json()["connections"][0][
        "id"
    ]
    post_id = client.post(
        f"/video-outputs/{output_id}/publish",
        json={"platform": "INSTAGRAM", "sns_connection_id": connection_id},
        headers=auth_headers,
    ).json()["sns_post_id"]

    client.delete(f"/sns-connections/{connection_id}", headers=auth_headers)

    assert client.get(f"/sns-posts/{post_id}", headers=auth_headers).status_code == 200


def test_connection_hidden_from_other_user(
    client: TestClient,
    auth_headers: dict[str, str],
    other_headers: dict[str, str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(sns_oauth, "exchange_code", lambda *a, **k: _fake_tokens())
    state = create_oauth_state(_user_id(client, auth_headers), "INSTAGRAM")
    client.get(f"/sns-connections/callback?code=abc&state={state}")
    connection_id = client.get("/sns-connections", headers=auth_headers).json()["connections"][0][
        "id"
    ]

    response = client.delete(f"/sns-connections/{connection_id}", headers=other_headers)

    assert response.status_code == 404
    assert response.json()["error_code"] == "SNS_CONNECTION_NOT_FOUND"


# ---------------------------------------------------------------- 16.2 게시


def test_publish_records_pending_link(
    client: TestClient, auth_headers: dict[str, str], output_id: int
) -> None:
    """서버는 실제로 올렸는지 확인할 수 없다 — 항상 연결 대기로 시작한다."""
    response = client.post(
        f"/video-outputs/{output_id}/publish",
        json={
            "platform": "INSTAGRAM",
            "publish_mode": "HANDOFF",
            "post_caption": "오늘만 특별 공개!",
            "post_hashtags": "#강남맛집",
        },
        headers=auth_headers,
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["post_platform"] == "INSTAGRAM"
    assert body["post_status"] == "PENDING_LINK"
    assert body["created_at"].endswith("Z")


def test_publish_allows_platforms_without_connection_support(
    client: TestClient, auth_headers: dict[str, str], output_id: int
) -> None:
    """게시는 4개 플랫폼, 연동은 2개 (2026-08-24 확정)."""
    response = client.post(
        f"/video-outputs/{output_id}/publish",
        json={"platform": "NAVER_CLIP"},
        headers=auth_headers,
    )

    assert response.status_code == 200
    assert response.json()["post_platform"] == "NAVER_CLIP"


def test_direct_publish_blocked(
    client: TestClient, auth_headers: dict[str, str], output_id: int
) -> None:
    """검수 전에 열어두면 사장님은 올라간 줄 알지만 아무 일도 안 일어난다."""
    response = client.post(
        f"/video-outputs/{output_id}/publish",
        json={"platform": "INSTAGRAM", "publish_mode": "DIRECT"},
        headers=auth_headers,
    )

    assert response.status_code == 400
    assert response.json()["error_code"] == "DIRECT_PUBLISH_UNAVAILABLE"


def test_publish_hidden_from_other_user(
    client: TestClient, other_headers: dict[str, str], output_id: int
) -> None:
    response = client.post(
        f"/video-outputs/{output_id}/publish",
        json={"platform": "INSTAGRAM"},
        headers=other_headers,
    )

    assert response.status_code == 404
    assert response.json()["error_code"] == "OUTPUT_NOT_FOUND"


# ---------------------------------------------------------------- 16.3 연결확정


def _publish(client: TestClient, headers: dict[str, str], output_id: int) -> int:
    return client.post(
        f"/video-outputs/{output_id}/publish",
        json={"platform": "INSTAGRAM"},
        headers=headers,
    ).json()["sns_post_id"]


def test_link_post_sets_linked(
    client: TestClient, auth_headers: dict[str, str], output_id: int
) -> None:
    post_id = _publish(client, auth_headers, output_id)

    response = client.patch(
        f"/sns-posts/{post_id}",
        json={"external_post_id": "17998877665544332", "posted_at": "2026-08-19T11:05:00Z"},
        headers=auth_headers,
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["post_status"] == "LINKED"
    assert body["external_post_id"] == "17998877665544332"
    assert body["posted_at"] == "2026-08-19T11:05:00Z"


def test_link_post_defaults_posted_at(
    client: TestClient, auth_headers: dict[str, str], output_id: int
) -> None:
    """생략하면 연결 시각으로 둔다 — 비워두면 17.2 신뢰도가 실제보다 낮게 잡힌다."""
    post_id = _publish(client, auth_headers, output_id)

    body = client.patch(
        f"/sns-posts/{post_id}",
        json={"external_post_id": "17998877665544332"},
        headers=auth_headers,
    ).json()

    assert body["posted_at"] is not None


def test_get_post_returns_status(
    client: TestClient, auth_headers: dict[str, str], output_id: int
) -> None:
    post_id = _publish(client, auth_headers, output_id)

    body = client.get(f"/sns-posts/{post_id}", headers=auth_headers).json()

    assert body["id"] == post_id
    assert body["post_status"] == "PENDING_LINK"


def test_post_hidden_from_other_user(
    client: TestClient,
    auth_headers: dict[str, str],
    other_headers: dict[str, str],
    output_id: int,
) -> None:
    post_id = _publish(client, auth_headers, output_id)

    response = client.get(f"/sns-posts/{post_id}", headers=other_headers)

    assert response.status_code == 404
    assert response.json()["error_code"] == "SNS_POST_NOT_FOUND"


def test_linked_post_feeds_performance(
    client: TestClient, auth_headers: dict[str, str], store_id: int, output_id: int
) -> None:
    """16.3 연결이 17.2 비교의 출발점이다."""
    post_id = _publish(client, auth_headers, output_id)
    client.patch(
        f"/sns-posts/{post_id}",
        json={"external_post_id": "179988"},
        headers=auth_headers,
    )

    body = client.get(
        f"/sns-posts/compare?store_id={store_id}&platform=INSTAGRAM", headers=auth_headers
    ).json()

    assert [i["sns_post_id"] for i in body["comparison"]] == [post_id]


def test_sns_post_routes_not_shadowed(
    client: TestClient, auth_headers: dict[str, str], store_id: int
) -> None:
    """`/compare`가 `/{postId}`보다 먼저 선언돼야 한다."""
    assert (
        client.get(f"/sns-posts/compare?store_id={store_id}", headers=auth_headers).status_code
        == 200
    )
