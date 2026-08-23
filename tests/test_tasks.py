"""촬영 태스크 API 테스트 (API명세서 8.1 보드 / 8.2 상태 변경)."""

from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.models.shooting_task import ShootingTask, TaskStatus
from app.models.video_format import VideoFormat

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
def project_id(client: TestClient, auth_headers: dict[str, str]) -> int:
    store_id = client.post("/stores", json=STORE_BODY, headers=auth_headers).json()["id"]
    return client.post(
        "/shorts-projects",
        json={"store_id": store_id, "promotion_purpose": "메뉴소개"},
        headers=auth_headers,
    ).json()["id"]


@pytest.fixture
def planned(
    client: TestClient, auth_headers: dict[str, str], project_id: int, video_format: VideoFormat
) -> int:
    """7.1을 호출해 콘티·태스크가 만들어진 프로젝트."""
    response = client.post(
        f"/shorts-projects/{project_id}/plan",
        json={"video_format_id": video_format.id},
        headers=auth_headers,
    )
    assert response.status_code == 200, response.text
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


def _board(client: TestClient, headers: dict[str, str], project_id: int) -> Any:
    return client.get(f"/shorts-projects/{project_id}/tasks", headers=headers).json()


# ---------------------------------------------------------------- 태스크 생성 (7.1 연동)


def test_plan_creates_tasks(client: TestClient, auth_headers: dict[str, str], planned: int) -> None:
    """태스크를 만드는 API가 없다 — 7.1이 콘티와 함께 만든다."""
    tasks = _board(client, auth_headers, planned)["tasks"]

    assert len(tasks) > 0
    assert all(task["task_status"] == "NOT_STARTED" for task in tasks)


def test_tasks_are_linked_to_scenes(
    client: TestClient, auth_headers: dict[str, str], planned: int
) -> None:
    scene_ids = {
        scene["id"]
        for scene in client.get(f"/shorts-projects/{planned}/scenes", headers=auth_headers).json()[
            "scenes"
        ]
    }
    tasks = _board(client, auth_headers, planned)["tasks"]

    assert all(task["scene_id"] in scene_ids for task in tasks)


def test_replanning_overwrites_tasks(
    client: TestClient,
    auth_headers: dict[str, str],
    planned: int,
    db_session: Session,
    video_format: VideoFormat,
) -> None:
    """7.1 재호출 시 태스크도 콘티와 함께 덮어써진다 — 쌓이면 안 된다."""
    before = len(_board(client, auth_headers, planned)["tasks"])

    other_format = VideoFormat(
        format_title="가게 한 바퀴",
        format_type="잔잔한 소개",
        reference_url="https://youtu.be/2",
        source_platform="YOUTUBE",
        expected_duration_sec=40,
        shooting_difficulty="중",
        face_exposure_level="낮음",
    )
    db_session.add(other_format)
    db_session.commit()
    db_session.refresh(other_format)

    client.post(
        f"/shorts-projects/{planned}/plan",
        json={"video_format_id": other_format.id},
        headers=auth_headers,
    )

    assert len(_board(client, auth_headers, planned)["tasks"]) == before


# ---------------------------------------------------------------- 8.1 보드 조회


def test_board_returns_spec_fields(
    client: TestClient, auth_headers: dict[str, str], planned: int
) -> None:
    body = _board(client, auth_headers, planned)

    assert set(body) == {"progress_rate", "estimated_remaining_min", "tasks"}
    assert set(body["tasks"][0]) == {
        "id",
        "scene_id",
        "task_type",
        "task_title",
        "task_status",
        "display_order",
    }


def test_board_is_empty_before_plan(
    client: TestClient, auth_headers: dict[str, str], project_id: int
) -> None:
    body = _board(client, auth_headers, project_id)

    assert body["tasks"] == []
    assert body["progress_rate"] == 0
    assert body["estimated_remaining_min"] is None


def test_tasks_are_ordered_by_display_order(
    client: TestClient, auth_headers: dict[str, str], planned: int
) -> None:
    tasks = _board(client, auth_headers, planned)["tasks"]

    assert [task["display_order"] for task in tasks] == sorted(
        task["display_order"] for task in tasks
    )


def test_board_requires_authentication(client: TestClient, project_id: int) -> None:
    assert client.get(f"/shorts-projects/{project_id}/tasks").status_code == 401


def test_board_hidden_from_other_user(
    client: TestClient, planned: int, other_headers: dict[str, str]
) -> None:
    response = client.get(f"/shorts-projects/{planned}/tasks", headers=other_headers)

    assert response.status_code == 404


# ---------------------------------------------------------------- progress_rate 공식


def test_progress_rate_counts_retake_needed_as_done(
    client: TestClient, auth_headers: dict[str, str], planned: int, db_session: Session
) -> None:
    """RETAKE_NEEDED도 완료로 센다 — 촬영본은 있고 품질 경고만 붙은 상태다.

    2026-08-21 확정 공식: (DONE + RETAKE_NEEDED) / 전체 × 100
    """
    tasks = db_session.scalars(
        db_session.query(ShootingTask)
        .filter(ShootingTask.shorts_project_id == planned)
        .order_by(ShootingTask.display_order)
        .statement
    ).all()
    assert len(tasks) == 4  # 임시 기획은 장면 4개 → 태스크 4개

    tasks[0].task_status = TaskStatus.DONE
    tasks[1].task_status = TaskStatus.RETAKE_NEEDED
    tasks[2].task_status = TaskStatus.IN_PROGRESS
    db_session.commit()

    body = _board(client, auth_headers, planned)
    # DONE 1 + RETAKE_NEEDED 1 = 2 / 4 = 50%. IN_PROGRESS는 미완료로 센다.
    assert body["progress_rate"] == 50


def test_progress_rate_is_100_when_all_done(
    client: TestClient, auth_headers: dict[str, str], planned: int, db_session: Session
) -> None:
    for task in db_session.query(ShootingTask).filter(ShootingTask.shorts_project_id == planned):
        task.task_status = TaskStatus.DONE
    db_session.commit()

    body = _board(client, auth_headers, planned)
    assert body["progress_rate"] == 100
    assert body["estimated_remaining_min"] == 0


def test_remaining_time_decreases_as_tasks_complete(
    client: TestClient, auth_headers: dict[str, str], planned: int, db_session: Session
) -> None:
    """남은 시간은 남은 태스크 비율에 비례한다(근사값)."""
    before = _board(client, auth_headers, planned)["estimated_remaining_min"]

    task = db_session.query(ShootingTask).filter(ShootingTask.shorts_project_id == planned).first()
    assert task is not None
    task.task_status = TaskStatus.DONE
    db_session.commit()

    after = _board(client, auth_headers, planned)["estimated_remaining_min"]
    assert after < before


# ---------------------------------------------------------------- 8.2 상태 변경


def test_update_status_returns_spec_fields(
    client: TestClient, auth_headers: dict[str, str], planned: int
) -> None:
    task_id = _board(client, auth_headers, planned)["tasks"][0]["id"]

    response = client.patch(
        f"/tasks/{task_id}", json={"task_status": "IN_PROGRESS"}, headers=auth_headers
    )

    assert response.status_code == 200
    body = response.json()
    assert set(body) == {"id", "task_status", "updated_at"}
    assert body["task_status"] == "IN_PROGRESS"
    assert body["updated_at"].endswith("Z")


def test_update_status_reflects_in_board(
    client: TestClient, auth_headers: dict[str, str], planned: int
) -> None:
    task_id = _board(client, auth_headers, planned)["tasks"][0]["id"]

    client.patch(f"/tasks/{task_id}", json={"task_status": "DONE"}, headers=auth_headers)

    board = _board(client, auth_headers, planned)
    changed = next(task for task in board["tasks"] if task["id"] == task_id)
    assert changed["task_status"] == "DONE"
    assert board["progress_rate"] == 25  # 4개 중 1개


def test_update_rejects_unknown_status(
    client: TestClient, auth_headers: dict[str, str], planned: int
) -> None:
    task_id = _board(client, auth_headers, planned)["tasks"][0]["id"]

    response = client.patch(
        f"/tasks/{task_id}", json={"task_status": "없는상태"}, headers=auth_headers
    )

    assert response.status_code == 422


def test_update_hidden_from_other_user(
    client: TestClient, auth_headers: dict[str, str], planned: int, other_headers: dict[str, str]
) -> None:
    """태스크에는 사용자 정보가 없다 — 프로젝트·가게를 거슬러 확인해야 한다."""
    task_id = _board(client, auth_headers, planned)["tasks"][0]["id"]

    response = client.patch(
        f"/tasks/{task_id}", json={"task_status": "DONE"}, headers=other_headers
    )

    assert response.status_code == 404
    assert response.json()["error_code"] == "TASK_NOT_FOUND"


def test_update_unknown_task_returns_404(client: TestClient, auth_headers: dict[str, str]) -> None:
    response = client.patch("/tasks/999999", json={"task_status": "DONE"}, headers=auth_headers)

    assert response.status_code == 404
    assert response.json()["error_code"] == "TASK_NOT_FOUND"


def test_update_requires_authentication(client: TestClient, planned: int) -> None:
    assert client.patch("/tasks/1", json={"task_status": "DONE"}).status_code == 401
