"""AI 자동편집 테스트 (API명세서 14.1 편집시작 / 14.2 결과조회 / 14.3 수정요청)."""

import io
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.models.shooting_task import ShootingTask
from app.models.video_format import VideoFormat

MP4_BYTES = b"\x00\x00\x00\x18ftypmp42" + b"\x00" * 32

STORE_BODY: dict[str, Any] = {
    "name": "행복분식",
    "category": "분식",
    "address": "서울 강남구 테헤란로 1길 10",
}


@pytest.fixture
def video_format(db_session: Session) -> VideoFormat:
    item = VideoFormat(
        format_title="가격 공개 반전 챌린지",
        format_type="밈",
        reference_url="https://youtu.be/1",
        source_platform="YOUTUBE",
        expected_duration_sec=24,
        shooting_difficulty="하",
        face_exposure_level="낮음",
    )
    db_session.add(item)
    db_session.commit()
    db_session.refresh(item)
    return item


@pytest.fixture
def project_id(client: TestClient, auth_headers: dict[str, str], video_format: VideoFormat) -> int:
    """기획까지 끝나 태스크가 만들어진 프로젝트."""
    store_id = client.post("/stores", json=STORE_BODY, headers=auth_headers).json()["id"]
    project_id = client.post(
        "/shorts-projects",
        json={"store_id": store_id, "promotion_purpose": "메뉴소개"},
        headers=auth_headers,
    ).json()["id"]
    client.post(
        f"/shorts-projects/{project_id}/plan",
        json={"video_format_id": video_format.id},
        headers=auth_headers,
    )
    return project_id


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


def _upload_all(client: TestClient, headers: dict[str, str], project_id: int) -> None:
    """모든 태스크에 촬영본을 올린다."""
    tasks = client.get(f"/shorts-projects/{project_id}/tasks", headers=headers).json()["tasks"]
    for task in tasks:
        client.post(
            f"/tasks/{task['id']}/footage",
            files={"file": ("take.mp4", io.BytesIO(MP4_BYTES), "video/mp4")},
            data={"footage_type": "VIDEO"},
            headers=headers,
        )


def _start_edit(client: TestClient, headers: dict[str, str], project_id: int) -> Any:
    return client.post(
        f"/shorts-projects/{project_id}/edit",
        json={"target_platform": "INSTAGRAM"},
        headers=headers,
    )


# ---------------------------------------------------------------- 14.1 편집 시작


def test_edit_blocked_when_tasks_incomplete(
    client: TestClient, auth_headers: dict[str, str], project_id: int
) -> None:
    """모든 태스크에 촬영본이 있어야 시작할 수 있다 (2026-08-21 확정)."""
    response = _start_edit(client, auth_headers, project_id)

    assert response.status_code == 400
    body = response.json()
    assert body["error_code"] == "TASKS_INCOMPLETE"
    # 어떤 태스크가 남았는지 알려줘야 프론트가 보드로 안내할 수 있다
    assert len(body["incomplete_tasks"]) == 4
    assert set(body["incomplete_tasks"][0]) == {"id", "task_title"}


def test_edit_blocked_when_one_task_missing(
    client: TestClient, auth_headers: dict[str, str], project_id: int, db_session: Session
) -> None:
    """하나만 비어도 막힌다. 그 하나만 응답에 담긴다."""
    _upload_all(client, auth_headers, project_id)

    task = db_session.scalars(
        db_session.query(ShootingTask)
        .filter(ShootingTask.shorts_project_id == project_id)
        .statement
    ).first()
    assert task is not None
    task.footage_url = None
    db_session.commit()

    body = _start_edit(client, auth_headers, project_id).json()

    assert body["error_code"] == "TASKS_INCOMPLETE"
    assert [item["id"] for item in body["incomplete_tasks"]] == [task.id]


def test_edit_checks_footage_not_task_status(
    client: TestClient, auth_headers: dict[str, str], project_id: int
) -> None:
    """검증 기준은 task_status가 아니라 footage_url이다.

    8.2로 상태만 DONE으로 바꿔도 촬영본이 없으면 편집할 재료가 없다.
    """
    tasks = client.get(f"/shorts-projects/{project_id}/tasks", headers=auth_headers).json()["tasks"]
    for task in tasks:
        client.patch(f"/tasks/{task['id']}", json={"task_status": "DONE"}, headers=auth_headers)

    response = _start_edit(client, auth_headers, project_id)

    assert response.status_code == 400
    assert response.json()["error_code"] == "TASKS_INCOMPLETE"


def test_edit_starts_when_all_footage_uploaded(
    client: TestClient, auth_headers: dict[str, str], project_id: int
) -> None:
    _upload_all(client, auth_headers, project_id)

    response = _start_edit(client, auth_headers, project_id)

    assert response.status_code == 200, response.text
    body = response.json()
    assert set(body) == {"video_output_id", "render_status"}
    assert body["render_status"] == "PENDING"


def test_edit_blocked_without_plan(client: TestClient, auth_headers: dict[str, str]) -> None:
    """7.1을 호출한 적 없으면 태스크 자체가 없다 — 편집할 재료가 없다."""
    store_id = client.post("/stores", json=STORE_BODY, headers=auth_headers).json()["id"]
    project_id = client.post(
        "/shorts-projects",
        json={"store_id": store_id, "promotion_purpose": "메뉴소개"},
        headers=auth_headers,
    ).json()["id"]

    body = _start_edit(client, auth_headers, project_id).json()

    assert body["error_code"] == "TASKS_INCOMPLETE"
    assert body["incomplete_tasks"] == []


def test_edit_hidden_from_other_user(
    client: TestClient, project_id: int, other_headers: dict[str, str]
) -> None:
    assert _start_edit(client, other_headers, project_id).status_code == 404


def test_edit_requires_authentication(client: TestClient, project_id: int) -> None:
    response = client.post(
        f"/shorts-projects/{project_id}/edit", json={"target_platform": "INSTAGRAM"}
    )

    assert response.status_code == 401


# ---------------------------------------------------------------- 14.2 결과 조회


def test_edit_result_returns_spec_fields(
    client: TestClient, auth_headers: dict[str, str], project_id: int
) -> None:
    _upload_all(client, auth_headers, project_id)
    _start_edit(client, auth_headers, project_id)

    response = client.get(f"/shorts-projects/{project_id}/edit/result", headers=auth_headers)

    assert response.status_code == 200
    body = response.json()
    assert set(body) == {
        "video_output_id",
        "render_status",
        "progress_percent",
        "preview_video_url",
        "timeline_summary",
        "missing_scene_roles",
        "available_options",
    }
    assert body["progress_percent"] == 0  # PENDING
    assert body["missing_scene_roles"] is None  # SOURCE_GAP 전용, 평소엔 null
    assert body["available_options"] is None
    assert set(body["timeline_summary"][0]) == {"scene_order", "duration_sec", "effect"}


def test_timeline_comes_from_storyboard(
    client: TestClient, auth_headers: dict[str, str], project_id: int
) -> None:
    """타임라인은 콘티에서 파생한다. effect는 AI 몫이라 연동 전까지 null이다."""
    _upload_all(client, auth_headers, project_id)
    _start_edit(client, auth_headers, project_id)

    scenes = client.get(f"/shorts-projects/{project_id}/scenes", headers=auth_headers).json()[
        "scenes"
    ]
    timeline = client.get(
        f"/shorts-projects/{project_id}/edit/result", headers=auth_headers
    ).json()["timeline_summary"]

    assert [item["scene_order"] for item in timeline] == [s["scene_order"] for s in scenes]
    assert all(item["effect"] is None for item in timeline)


def test_edit_result_404_before_edit(
    client: TestClient, auth_headers: dict[str, str], project_id: int
) -> None:
    response = client.get(f"/shorts-projects/{project_id}/edit/result", headers=auth_headers)

    assert response.status_code == 404
    assert response.json()["error_code"] == "OUTPUT_NOT_FOUND"


# ---------------------------------------------------------------- 14.3 수정 요청


def test_revise_creates_new_version(
    client: TestClient, auth_headers: dict[str, str], project_id: int
) -> None:
    """기존 산출물을 고치지 않고 새 행을 만든다 (ERD 코멘트: 버전 이력)."""
    _upload_all(client, auth_headers, project_id)
    first_id = _start_edit(client, auth_headers, project_id).json()["video_output_id"]

    response = client.post(
        f"/video-outputs/{first_id}/revise",
        json={"request_type": "quick_button", "action": "자막 크게"},
        headers=auth_headers,
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert set(body) == {"video_output_id", "render_status", "revision_id"}
    assert body["video_output_id"] != first_id  # 새 행이다
    assert body["render_status"] == "PROCESSING"
    assert body["revision_id"] == 2  # 첫 산출물이 1


def test_revision_id_increases(
    client: TestClient, auth_headers: dict[str, str], project_id: int
) -> None:
    _upload_all(client, auth_headers, project_id)
    output_id = _start_edit(client, auth_headers, project_id).json()["video_output_id"]

    for expected in (2, 3, 4):
        body = client.post(
            f"/video-outputs/{output_id}/revise",
            json={"request_type": "natural_language", "action": "더 빠르게"},
            headers=auth_headers,
        ).json()
        assert body["revision_id"] == expected
        output_id = body["video_output_id"]


def test_result_returns_latest_version(
    client: TestClient, auth_headers: dict[str, str], project_id: int
) -> None:
    """산출물이 쌓이면 14.2는 가장 최근 것을 준다."""
    _upload_all(client, auth_headers, project_id)
    first_id = _start_edit(client, auth_headers, project_id).json()["video_output_id"]
    revised_id = client.post(
        f"/video-outputs/{first_id}/revise",
        json={"request_type": "quick_button", "action": "자막 크게"},
        headers=auth_headers,
    ).json()["video_output_id"]

    result = client.get(f"/shorts-projects/{project_id}/edit/result", headers=auth_headers).json()

    assert result["video_output_id"] == revised_id
    assert result["progress_percent"] == 50  # PROCESSING


def test_revise_rejects_unknown_request_type(
    client: TestClient, auth_headers: dict[str, str], project_id: int
) -> None:
    _upload_all(client, auth_headers, project_id)
    output_id = _start_edit(client, auth_headers, project_id).json()["video_output_id"]

    response = client.post(
        f"/video-outputs/{output_id}/revise",
        json={"request_type": "없는타입", "action": "x"},
        headers=auth_headers,
    )

    assert response.status_code == 422


def test_revise_hidden_from_other_user(
    client: TestClient,
    auth_headers: dict[str, str],
    project_id: int,
    other_headers: dict[str, str],
) -> None:
    """산출물에는 사용자 정보가 없다 — 프로젝트·가게를 거슬러 확인해야 한다."""
    _upload_all(client, auth_headers, project_id)
    output_id = _start_edit(client, auth_headers, project_id).json()["video_output_id"]

    response = client.post(
        f"/video-outputs/{output_id}/revise",
        json={"request_type": "quick_button", "action": "자막 크게"},
        headers=other_headers,
    )

    assert response.status_code == 404
    assert response.json()["error_code"] == "OUTPUT_NOT_FOUND"


def test_revise_unknown_output_returns_404(
    client: TestClient, auth_headers: dict[str, str]
) -> None:
    response = client.post(
        "/video-outputs/999999/revise",
        json={"request_type": "quick_button", "action": "자막 크게"},
        headers=auth_headers,
    )

    assert response.status_code == 404
