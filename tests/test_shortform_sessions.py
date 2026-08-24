"""숏폼 Agent 세션 API 테스트 (R06 재설계, 2026-08-26).

`docs/AI_연동_입출력.md` 5~12번 기준. AI_SERVER_URL이 없는 테스트 환경에서는
placeholder 경로(`app/services/ai_client.py`)가 동작한다 — 실제 대화 로직 대신,
turn을 보내면 곧바로 추천으로 넘어가는지와 accept가 프로젝트를 만드는지를 검증한다.
"""

from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.models.video_format import VideoFormat

STORE_BODY: dict[str, Any] = {
    "name": "행복분식",
    "category": "분식",
    "address": "서울 강남구 테헤란로 1길 10",
}


@pytest.fixture
def store_id(client: TestClient, auth_headers: dict[str, str]) -> int:
    return client.post("/stores", json=STORE_BODY, headers=auth_headers).json()["id"]


@pytest.fixture
def menu_id(client: TestClient, auth_headers: dict[str, str], store_id: int) -> int:
    response = client.post(
        f"/stores/{store_id}/menus",
        json={"name": "떡볶이", "price": 4000},
        headers=auth_headers,
    )
    return response.json()["id"]


@pytest.fixture
def session_id(client: TestClient, auth_headers: dict[str, str], store_id: int) -> int:
    response = client.post(f"/stores/{store_id}/shortform-sessions", headers=auth_headers)
    return response.json()["id"]


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


# ---------------------------------------------------------------- 세션 생성


def test_create_session_returns_greeting(
    client: TestClient, auth_headers: dict[str, str], store_id: int
) -> None:
    response = client.post(f"/stores/{store_id}/shortform-sessions", headers=auth_headers)

    assert response.status_code == 201, response.text
    body = response.json()
    assert set(body) == {"id", "status", "assistant_message", "options", "project_state"}
    assert body["status"] == "ACTIVE"
    assert body["project_state"]["ready_for_confirmation"] is False
    assert body["project_state"]["promotion_subject"] is None


def test_create_session_for_other_store_is_404(
    client: TestClient, other_headers: dict[str, str], store_id: int
) -> None:
    response = client.post(f"/stores/{store_id}/shortform-sessions", headers=other_headers)
    assert response.status_code == 404
    assert response.json()["error_code"] == "STORE_NOT_FOUND"


# ---------------------------------------------------------------- turns


def test_turn_moves_straight_to_recommend(
    client: TestClient, auth_headers: dict[str, str], session_id: int
) -> None:
    """placeholder는 실제 대화를 못 하므로 첫 turn에 바로 추천으로 넘어간다."""
    response = client.post(
        f"/shortform-sessions/{session_id}/turns",
        json={"input": {"type": "TEXT", "text": "떡볶이 홍보하고 싶어요"}},
        headers=auth_headers,
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["action"] == "RECOMMEND"
    assert body["recommendation"] is not None
    assert set(body["recommendation"]) == {
        "recommendation_id",
        "project_title",
        "title",
        "concept",
        "editing_template_id",
        "editing_template_version",
    }
    assert body["project_state"]["ready_for_confirmation"] is True


def test_turn_uses_representative_menu_as_subject(
    client: TestClient, auth_headers: dict[str, str], session_id: int, menu_id: int
) -> None:
    response = client.post(
        f"/shortform-sessions/{session_id}/turns",
        json={"input": {"type": "TEXT", "text": "메뉴 홍보하고 싶어요"}},
        headers=auth_headers,
    )

    subject = response.json()["project_state"]["promotion_subject"]
    assert subject == {"type": "MENU", "name": "떡볶이", "menu_id": menu_id}


def test_turn_on_other_session_is_404(
    client: TestClient, other_headers: dict[str, str], session_id: int
) -> None:
    response = client.post(
        f"/shortform-sessions/{session_id}/turns",
        json={"input": {"type": "TEXT", "text": "hi"}},
        headers=other_headers,
    )
    assert response.status_code == 404
    assert response.json()["error_code"] == "SESSION_NOT_FOUND"


# ---------------------------------------------------------------- 다시 추천


def test_next_recommendation_accumulates_shown_ids(
    client: TestClient, auth_headers: dict[str, str], session_id: int
) -> None:
    first = client.post(
        f"/shortform-sessions/{session_id}/turns",
        json={"input": {"type": "TEXT", "text": "떡볶이 홍보하고 싶어요"}},
        headers=auth_headers,
    ).json()
    first_template_id = first["recommendation"]["editing_template_id"]

    response = client.post(
        f"/shortform-sessions/{session_id}/recommendations/next", headers=auth_headers
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert first_template_id in body["shown_template_ids"]
    assert body["recommendation"]["editing_template_id"] in body["shown_template_ids"]


# ---------------------------------------------------------------- accept


def test_accept_without_recommendation_is_409(
    client: TestClient, auth_headers: dict[str, str], session_id: int
) -> None:
    response = client.post(f"/shortform-sessions/{session_id}/accept", headers=auth_headers)
    assert response.status_code == 409
    assert response.json()["error_code"] == "RECOMMENDATION_NOT_READY"


def test_accept_creates_project_with_title_and_format(
    client: TestClient,
    auth_headers: dict[str, str],
    session_id: int,
    store_id: int,
    menu_id: int,
    db_session: Session,
) -> None:
    turn = client.post(
        f"/shortform-sessions/{session_id}/turns",
        json={"input": {"type": "TEXT", "text": "떡볶이 홍보하고 싶어요"}},
        headers=auth_headers,
    ).json()
    recommendation = turn["recommendation"]

    response = client.post(f"/shortform-sessions/{session_id}/accept", headers=auth_headers)

    assert response.status_code == 201, response.text
    body = response.json()
    assert body["store_id"] == store_id
    assert body["project_title"] == recommendation["project_title"]
    assert body["promotion_purpose"] == "메뉴소개"
    assert body["menu_id"] == menu_id
    assert body["shorts_status"] == "DRAFT"

    video_format = db_session.get(VideoFormat, body["video_format_id"])
    assert video_format is not None
    assert video_format.editing_template_id == recommendation["editing_template_id"]
    assert video_format.editing_template_version == recommendation["editing_template_version"]


def test_accept_populates_scenes_and_tasks(
    client: TestClient, auth_headers: dict[str, str], session_id: int
) -> None:
    """6.4(수락)가 7.1과 같은 로직을 재사용해 콘티·태스크까지 즉시 채운다."""
    client.post(
        f"/shortform-sessions/{session_id}/turns",
        json={"input": {"type": "TEXT", "text": "떡볶이 홍보하고 싶어요"}},
        headers=auth_headers,
    )
    project = client.post(f"/shortform-sessions/{session_id}/accept", headers=auth_headers).json()

    scenes = client.get(f"/shorts-projects/{project['id']}/scenes", headers=auth_headers).json()
    tasks = client.get(f"/shorts-projects/{project['id']}/tasks", headers=auth_headers).json()

    assert len(scenes["scenes"]) > 0
    assert len(tasks["tasks"]) > 0


def test_accept_twice_is_conflict(
    client: TestClient, auth_headers: dict[str, str], session_id: int
) -> None:
    client.post(
        f"/shortform-sessions/{session_id}/turns",
        json={"input": {"type": "TEXT", "text": "떡볶이 홍보하고 싶어요"}},
        headers=auth_headers,
    )
    first = client.post(f"/shortform-sessions/{session_id}/accept", headers=auth_headers)
    assert first.status_code == 201

    second = client.post(f"/shortform-sessions/{session_id}/accept", headers=auth_headers)
    assert second.status_code == 409
    assert second.json()["error_code"] == "SESSION_NOT_ACTIVE"


# ---------------------------------------------------------------- 종료(새로고침)


def test_discard_session_is_idempotent(
    client: TestClient, auth_headers: dict[str, str], session_id: int
) -> None:
    first = client.delete(f"/shortform-sessions/{session_id}", headers=auth_headers)
    second = client.delete(f"/shortform-sessions/{session_id}", headers=auth_headers)

    assert first.status_code == 200
    assert second.status_code == 200


def test_turn_after_discard_is_conflict(
    client: TestClient, auth_headers: dict[str, str], session_id: int
) -> None:
    client.delete(f"/shortform-sessions/{session_id}", headers=auth_headers)

    response = client.post(
        f"/shortform-sessions/{session_id}/turns",
        json={"input": {"type": "TEXT", "text": "hi"}},
        headers=auth_headers,
    )
    assert response.status_code == 409
    assert response.json()["error_code"] == "SESSION_NOT_ACTIVE"
