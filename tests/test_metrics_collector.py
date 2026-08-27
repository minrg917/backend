"""SNS 성과 지표 수집 배치 테스트 (API명세서 17.1, 2026-08-27 R17 성과 수집기)."""

from datetime import timedelta
from typing import Any

import httpx
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.mixins import utcnow
from app.models.shorts_project import ShortsProject
from app.models.sns import PostStatus, SnsConnection, SnsPost, SnsPostMetric
from app.models.video_output import RenderStatus, VideoOutput
from app.services import metrics_collector, sns_oauth


@pytest.fixture
def user_id(client: TestClient, auth_headers: dict[str, str]) -> int:
    return client.get("/users/me", headers=auth_headers).json()["id"]


@pytest.fixture
def store_id(client: TestClient, auth_headers: dict[str, str]) -> int:
    return client.post(
        "/stores",
        json={"name": "행복분식", "category": "분식", "address": "서울 강남구 테헤란로 1길 10"},
        headers=auth_headers,
    ).json()["id"]


def _make_linked_post(
    db: Session,
    user_id: int,
    store_id: int,
    platform: str,
    external_post_id: str = "ext-1",
    token_expires_at: Any = "future",
) -> SnsPost:
    connection = SnsConnection(
        user_id=user_id,
        sns_platform=platform,
        access_token="current-token",
        refresh_token="refresh-token",
        token_expires_at=(
            utcnow() + timedelta(days=30) if token_expires_at == "future" else token_expires_at
        ),
    )
    db.add(connection)
    db.flush()

    project = ShortsProject(store_id=store_id, promotion_purpose="메뉴소개")
    db.add(project)
    db.flush()
    output = VideoOutput(shorts_project_id=project.id, render_status=RenderStatus.COMPLETED)
    db.add(output)
    db.flush()

    post = SnsPost(
        video_output_id=output.id,
        sns_connection_id=connection.id,
        post_platform=platform,
        post_status=PostStatus.LINKED,
        external_post_id=external_post_id,
    )
    db.add(post)
    db.commit()
    db.refresh(post)
    return post


def _fake_insights_get(url: str, params: dict[str, Any], timeout: float) -> httpx.Response:
    return httpx.Response(
        200,
        json={"data": [{"name": "views", "values": [{"value": 1000}]}]},
        request=httpx.Request("GET", url),
    )


def test_collect_all_stores_snapshot_for_linked_post(
    db_session: Session, user_id: int, store_id: int, monkeypatch: pytest.MonkeyPatch
) -> None:
    post = _make_linked_post(db_session, user_id, store_id, "INSTAGRAM")
    monkeypatch.setattr(httpx, "get", _fake_insights_get)

    checked, collected = metrics_collector.collect_all(db_session)

    assert (checked, collected) == (1, 1)
    metrics = list(
        db_session.scalars(select(SnsPostMetric).where(SnsPostMetric.sns_post_id == post.id))
    )
    assert len(metrics) == 1
    assert metrics[0].metric_name == "views"
    assert metrics[0].metric_value == 1000


def test_collect_all_ignores_posts_not_linked(
    db_session: Session, user_id: int, store_id: int, monkeypatch: pytest.MonkeyPatch
) -> None:
    post = _make_linked_post(db_session, user_id, store_id, "INSTAGRAM")
    post.post_status = PostStatus.PENDING_LINK
    db_session.commit()
    monkeypatch.setattr(httpx, "get", _fake_insights_get)

    checked, collected = metrics_collector.collect_all(db_session)

    assert (checked, collected) == (0, 0)


def test_collect_all_refreshes_token_before_fetching(
    db_session: Session, user_id: int, store_id: int, monkeypatch: pytest.MonkeyPatch
) -> None:
    """만료가 임박한 토큰은 조회 전에 갱신하고, 갱신된 토큰으로 호출해야 한다."""
    post = _make_linked_post(db_session, user_id, store_id, "INSTAGRAM", token_expires_at=utcnow())
    captured: dict[str, Any] = {}

    def fake_get(url: str, params: dict[str, Any], timeout: float) -> httpx.Response:
        captured["access_token"] = params["access_token"]
        return httpx.Response(200, json={"data": []}, request=httpx.Request("GET", url))

    monkeypatch.setattr(httpx, "get", fake_get)
    monkeypatch.setattr(
        sns_oauth,
        "refresh_access_token",
        lambda platform, connection: sns_oauth.OAuthTokens(access_token="refreshed-token"),
    )
    monkeypatch.setattr(
        sns_oauth,
        "get_platform",
        lambda platform: sns_oauth.PlatformOAuth(
            platform=platform,
            authorize_url="",
            token_url="",
            scopes=(),
            client_id="x",
            client_secret="y",
        ),
    )

    metrics_collector.collect_all(db_session)

    assert captured["access_token"] == "refreshed-token"
    connection = db_session.get(SnsConnection, post.sns_connection_id)
    assert connection is not None
    assert connection.access_token == "refreshed-token"


def test_collect_all_skips_connection_when_refresh_fails(
    db_session: Session, user_id: int, store_id: int, monkeypatch: pytest.MonkeyPatch
) -> None:
    """한 사장님의 토큰 갱신 실패가 전체 배치를 멈추면 안 된다."""
    _make_linked_post(db_session, user_id, store_id, "INSTAGRAM", token_expires_at=utcnow())

    def fail_refresh(platform: Any, connection: Any) -> sns_oauth.OAuthTokens:
        raise sns_oauth.SnsAuthFailed

    monkeypatch.setattr(sns_oauth, "refresh_access_token", fail_refresh)
    monkeypatch.setattr(
        sns_oauth,
        "get_platform",
        lambda platform: sns_oauth.PlatformOAuth(
            platform=platform,
            authorize_url="",
            token_url="",
            scopes=(),
            client_id="x",
            client_secret="y",
        ),
    )

    checked, collected = metrics_collector.collect_all(db_session)

    assert (checked, collected) == (1, 0)


def test_collect_all_appends_new_snapshot_without_deleting_old(
    db_session: Session, user_id: int, store_id: int, monkeypatch: pytest.MonkeyPatch
) -> None:
    """추이 그래프를 그리려고 스냅샷을 쌓는 설계라, 두 번째 수집도 기존 값을 지우면 안 된다."""
    post = _make_linked_post(db_session, user_id, store_id, "INSTAGRAM")
    monkeypatch.setattr(httpx, "get", _fake_insights_get)

    metrics_collector.collect_all(db_session)
    metrics_collector.collect_all(db_session)

    metrics = list(
        db_session.scalars(select(SnsPostMetric).where(SnsPostMetric.sns_post_id == post.id))
    )
    assert len(metrics) == 2
