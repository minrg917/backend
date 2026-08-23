"""성과분석 테스트 (API명세서 17.1 지표 조회 / 17.2 성과 비교)."""

from datetime import timedelta
from decimal import Decimal
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.models.mixins import utcnow
from app.models.shorts_project import ShortsProject
from app.models.sns import SnsPost, SnsPostMetric
from app.models.video_output import RenderStatus, VideoOutput

STORE_BODY: dict[str, Any] = {
    "name": "행복분식",
    "category": "분식",
    "address": "서울 강남구 테헤란로 1길 10",
}


@pytest.fixture
def store_id(client: TestClient, auth_headers: dict[str, str]) -> int:
    return client.post("/stores", json=STORE_BODY, headers=auth_headers).json()["id"]


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


def _make_post(
    db: Session,
    store_id: int,
    *,
    platform: str = "INSTAGRAM",
    goal: str = "메뉴소개",
    days_ago: int = 10,
) -> SnsPost:
    """게시물 하나를 프로젝트·산출물까지 갖춰 만든다."""
    project = ShortsProject(store_id=store_id, promotion_purpose=goal)
    db.add(project)
    db.flush()

    output = VideoOutput(shorts_project_id=project.id, render_status=RenderStatus.COMPLETED)
    db.add(output)
    db.flush()

    post = SnsPost(
        video_output_id=output.id,
        post_platform=platform,
        posted_at=utcnow() - timedelta(days=days_ago),
    )
    db.add(post)
    db.commit()
    db.refresh(post)
    return post


def _add_metric(
    db: Session, post: SnsPost, name: str, value: str, *, days_ago: int = 0
) -> SnsPostMetric:
    metric = SnsPostMetric(
        sns_post_id=post.id,
        metric_name=name,
        metric_value=Decimal(value),
        collected_at=utcnow() - timedelta(days=days_ago),
    )
    db.add(metric)
    db.commit()
    return metric


# ---------------------------------------------------------------- 17.1 지표 조회


def test_metrics_returns_spec_fields(
    client: TestClient, auth_headers: dict[str, str], db_session: Session, store_id: int
) -> None:
    post = _make_post(db_session, store_id)
    _add_metric(db_session, post, "views", "15230")

    response = client.get(f"/sns-posts/{post.id}/metrics", headers=auth_headers)

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["sns_post_id"] == post.id
    assert body["metrics"][0]["metric_name"] == "views"
    assert Decimal(str(body["metrics"][0]["metric_value"])) == Decimal("15230")
    assert body["metrics"][0]["collected_at"].endswith("Z")


def test_metrics_empty_before_collection(
    client: TestClient, auth_headers: dict[str, str], db_session: Session, store_id: int
) -> None:
    """R16 연동 전에는 수집이 없어 빈 배열이다. 0으로 채우지 않는다."""
    post = _make_post(db_session, store_id)

    body = client.get(f"/sns-posts/{post.id}/metrics", headers=auth_headers).json()

    assert body["metrics"] == []


def test_metrics_ordered_by_collected_at(
    client: TestClient, auth_headers: dict[str, str], db_session: Session, store_id: int
) -> None:
    """추이 그래프를 그리려면 시간순이어야 한다."""
    post = _make_post(db_session, store_id)
    _add_metric(db_session, post, "views", "300", days_ago=0)
    _add_metric(db_session, post, "views", "100", days_ago=2)
    _add_metric(db_session, post, "views", "200", days_ago=1)

    body = client.get(f"/sns-posts/{post.id}/metrics", headers=auth_headers).json()

    assert [m["metric_value"] for m in body["metrics"]] == [100, 200, 300]


def test_metrics_date_filter_includes_end_day(
    client: TestClient, auth_headers: dict[str, str], db_session: Session, store_id: int
) -> None:
    """`to`는 그날 하루를 포함한다 — 날짜로 고르는 값이라 그게 자연스럽다."""
    post = _make_post(db_session, store_id)
    today = _add_metric(db_session, post, "views", "300", days_ago=0)
    _add_metric(db_session, post, "views", "100", days_ago=5)

    day = today.collected_at.date().isoformat()
    body = client.get(
        f"/sns-posts/{post.id}/metrics?from={day}&to={day}", headers=auth_headers
    ).json()

    assert [m["metric_value"] for m in body["metrics"]] == [300]


def test_metrics_hidden_from_other_user(
    client: TestClient, other_headers: dict[str, str], db_session: Session, store_id: int
) -> None:
    post = _make_post(db_session, store_id)

    response = client.get(f"/sns-posts/{post.id}/metrics", headers=other_headers)

    assert response.status_code == 404
    assert response.json()["error_code"] == "SNS_POST_NOT_FOUND"


def test_metrics_requires_authentication(
    client: TestClient, db_session: Session, store_id: int
) -> None:
    post = _make_post(db_session, store_id)

    assert client.get(f"/sns-posts/{post.id}/metrics").status_code == 401


# ---------------------------------------------------------------- 17.2 성과 비교


def _three_posts(db_session: Session, store_id: int) -> list[SnsPost]:
    """표본 부족(<3) 조건에 걸리지 않도록 3개를 만든다."""
    return [_make_post(db_session, store_id, days_ago=40) for _ in range(3)]


def test_compare_calculates_rates(
    client: TestClient, auth_headers: dict[str, str], db_session: Session, store_id: int
) -> None:
    """누적 조회수가 아니라 비율로 비교한다."""
    posts = _three_posts(db_session, store_id)
    _add_metric(db_session, posts[0], "reach", "36000")
    _add_metric(db_session, posts[0], "views", "15120")
    _add_metric(db_session, posts[0], "saves", "120")

    body = client.get(f"/sns-posts/compare?store_id={store_id}", headers=auth_headers).json()

    top = body["comparison"][0]
    assert top["sns_post_id"] == posts[0].id
    assert Decimal(str(top["view_rate"])) == Decimal("0.42")
    assert Decimal(str(top["save_rate"])) == Decimal("0.0079")


def test_compare_returns_null_rate_without_denominator(
    client: TestClient, auth_headers: dict[str, str], db_session: Session, store_id: int
) -> None:
    """분모(reach)가 없으면 계산할 수 없다 — 0이 아니라 null이다."""
    posts = _three_posts(db_session, store_id)
    _add_metric(db_session, posts[0], "views", "15120")

    body = client.get(f"/sns-posts/compare?store_id={store_id}", headers=auth_headers).json()

    item = next(i for i in body["comparison"] if i["sns_post_id"] == posts[0].id)
    assert item["view_rate"] is None


def test_compare_uses_latest_snapshot(
    client: TestClient, auth_headers: dict[str, str], db_session: Session, store_id: int
) -> None:
    """스냅샷이 쌓여도 비교에는 마지막 값을 쓴다."""
    posts = _three_posts(db_session, store_id)
    _add_metric(db_session, posts[0], "reach", "1000")
    _add_metric(db_session, posts[0], "views", "100", days_ago=3)
    _add_metric(db_session, posts[0], "views", "500", days_ago=0)

    body = client.get(f"/sns-posts/compare?store_id={store_id}", headers=auth_headers).json()

    item = next(i for i in body["comparison"] if i["sns_post_id"] == posts[0].id)
    assert Decimal(str(item["view_rate"])) == Decimal("0.5")


def test_compare_small_sample_is_low_confidence(
    client: TestClient, auth_headers: dict[str, str], db_session: Session, store_id: int
) -> None:
    """게시물이 3개 미만이면 무엇과 비교해도 의미가 없다 (S17.3.1)."""
    _make_post(db_session, store_id, days_ago=100)
    _make_post(db_session, store_id, days_ago=100)

    body = client.get(f"/sns-posts/compare?store_id={store_id}", headers=auth_headers).json()

    assert len(body["comparison"]) == 2
    assert {i["confidence"] for i in body["comparison"]} == {"낮음"}


def test_compare_confidence_by_days(
    client: TestClient, auth_headers: dict[str, str], db_session: Session, store_id: int
) -> None:
    """게시 직후에는 지표가 아직 오르는 중이라 확정된 값이 아니다."""
    _make_post(db_session, store_id, days_ago=3)
    _make_post(db_session, store_id, days_ago=14)
    _make_post(db_session, store_id, days_ago=60)

    body = client.get(f"/sns-posts/compare?store_id={store_id}", headers=auth_headers).json()

    by_days = {i["days_since_posted"]: i["confidence"] for i in body["comparison"]}
    assert by_days == {3: "낮음", 14: "보통", 60: "높음"}


def test_compare_filters_by_platform(
    client: TestClient, auth_headers: dict[str, str], db_session: Session, store_id: int
) -> None:
    """플랫폼마다 조회수 집계 기준이 달라 한 표에 섞지 않는다 (S17.3.1)."""
    _make_post(db_session, store_id, platform="INSTAGRAM")
    _make_post(db_session, store_id, platform="YOUTUBE")

    body = client.get(
        f"/sns-posts/compare?store_id={store_id}&platform=INSTAGRAM", headers=auth_headers
    ).json()

    assert len(body["comparison"]) == 1


def test_compare_filters_by_goal(
    client: TestClient, auth_headers: dict[str, str], db_session: Session, store_id: int
) -> None:
    _make_post(db_session, store_id, goal="메뉴소개")
    _make_post(db_session, store_id, goal="이벤트알리기")

    body = client.get(
        f"/sns-posts/compare?store_id={store_id}&goal=메뉴소개", headers=auth_headers
    ).json()

    assert len(body["comparison"]) == 1


def test_compare_empty_when_nothing_posted(
    client: TestClient, auth_headers: dict[str, str], store_id: int
) -> None:
    body = client.get(f"/sns-posts/compare?store_id={store_id}", headers=auth_headers).json()

    assert body["comparison"] == []


def test_compare_hidden_from_other_user(
    client: TestClient, other_headers: dict[str, str], store_id: int
) -> None:
    response = client.get(f"/sns-posts/compare?store_id={store_id}", headers=other_headers)

    assert response.status_code == 404
    assert response.json()["error_code"] == "STORE_NOT_FOUND"


def test_compare_route_not_shadowed_by_post_id(
    client: TestClient, auth_headers: dict[str, str], store_id: int
) -> None:
    """`/compare`가 `/{postId}/metrics`보다 먼저 선언돼야 한다."""
    response = client.get(f"/sns-posts/compare?store_id={store_id}", headers=auth_headers)

    assert response.status_code == 200
