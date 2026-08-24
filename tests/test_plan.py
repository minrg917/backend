"""가게 맞춤 기획 API 테스트 (API명세서 7.1 기획 생성 / 7.2 콘티)."""

from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.models.shorts_project import ShortsProject
from app.models.video_format import VideoFormat

STORE_BODY: dict[str, Any] = {
    "name": "행복분식",
    "category": "분식",
    "address": "서울 강남구 테헤란로 1길 10",
}


@pytest.fixture
def formats(db_session: Session) -> list[VideoFormat]:
    items = [
        VideoFormat(
            format_title="가격 공개 반전 챌린지",
            format_type="밈",
            reference_url="https://youtu.be/1",
            source_platform="YOUTUBE",
            expected_duration_sec=24,
            shooting_difficulty="하",
            face_exposure_level="낮음",
        ),
        VideoFormat(
            format_title="가게 한 바퀴",
            format_type="잔잔한 소개",
            reference_url="https://youtu.be/2",
            source_platform="YOUTUBE",
            expected_duration_sec=40,
            shooting_difficulty="중",
            face_exposure_level="낮음",
        ),
    ]
    db_session.add_all(items)
    db_session.commit()
    for item in items:
        db_session.refresh(item)
    return items


@pytest.fixture
def project_id(client: TestClient, auth_headers: dict[str, str]) -> int:
    store_id = client.post("/stores", json=STORE_BODY, headers=auth_headers).json()["id"]
    response = client.post(
        "/shorts-projects",
        json={"store_id": store_id, "promotion_purpose": "메뉴소개"},
        headers=auth_headers,
    )
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


def _create_plan(
    client: TestClient, headers: dict[str, str], project_id: int, format_id: int
) -> Any:
    return client.post(
        f"/shorts-projects/{project_id}/plan",
        json={"video_format_id": format_id},
        headers=headers,
    )


# ---------------------------------------------------------------- 7.1 기획 생성


def test_plan_returns_spec_fields(
    client: TestClient, auth_headers: dict[str, str], project_id: int, formats: list[VideoFormat]
) -> None:
    response = _create_plan(client, auth_headers, project_id, formats[0].id)

    assert response.status_code == 200, response.text
    body = response.json()
    assert set(body) == {"shooting_summary", "scenes_preview"}
    assert set(body["shooting_summary"]) == {
        "expected_duration_sec",
        "required_people",
        "props",
        "difficulty",
    }
    assert set(body["scenes_preview"][0]) == {
        "id",
        "scene_order",
        "scene_description",
        "scene_dialogue",
        "target_duration_sec",
    }


def test_plan_saves_video_format_id(
    client: TestClient, auth_headers: dict[str, str], project_id: int, formats: list[VideoFormat]
) -> None:
    """7.1이 포맷을 저장하는 유일한 경로다 (2026-08-23 확정)."""
    _create_plan(client, auth_headers, project_id, formats[0].id)

    project = client.get(f"/shorts-projects/{project_id}", headers=auth_headers).json()
    assert project["video_format_id"] == formats[0].id


def test_plan_overwrites_scenes_on_regeneration(
    client: TestClient, auth_headers: dict[str, str], project_id: int, formats: list[VideoFormat]
) -> None:
    """포맷을 바꿔 재생성하면 기존 장면이 덮어써진다 — 쌓이면 안 된다.

    ID 재사용 여부는 DB마다 다르므로(SQLite는 재사용, MySQL은 안 함) 검사하지 않는다.
    장면이 누적되지 않는 것과, 내용이 새 포맷 기준으로 바뀌는 것만 본다.
    """
    first = _create_plan(client, auth_headers, project_id, formats[0].id).json()

    second = _create_plan(client, auth_headers, project_id, formats[1].id).json()

    scenes = client.get(f"/shorts-projects/{project_id}/scenes", headers=auth_headers).json()[
        "scenes"
    ]
    # 두 번 만들었지만 한 벌만 남는다
    assert len(scenes) == len(second["scenes_preview"])
    assert {scene["id"] for scene in scenes} == {scene["id"] for scene in second["scenes_preview"]}
    # 포맷 길이가 다르므로(24초 → 40초) 장면 길이도 새 포맷 기준으로 바뀐다
    assert (
        first["scenes_preview"][0]["target_duration_sec"]
        != second["scenes_preview"][0]["target_duration_sec"]
    )


def test_plan_updates_format_on_regeneration(
    client: TestClient, auth_headers: dict[str, str], project_id: int, formats: list[VideoFormat]
) -> None:
    _create_plan(client, auth_headers, project_id, formats[0].id)
    _create_plan(client, auth_headers, project_id, formats[1].id)

    project = client.get(f"/shorts-projects/{project_id}", headers=auth_headers).json()
    assert project["video_format_id"] == formats[1].id


def test_plan_rejects_unknown_format(
    client: TestClient, auth_headers: dict[str, str], project_id: int
) -> None:
    response = _create_plan(client, auth_headers, project_id, 999999)

    assert response.status_code == 404
    assert response.json()["error_code"] == "FORMAT_NOT_FOUND"


def test_plan_hidden_from_other_user(
    client: TestClient, project_id: int, other_headers: dict[str, str], formats: list[VideoFormat]
) -> None:
    response = _create_plan(client, other_headers, project_id, formats[0].id)

    assert response.status_code == 404
    assert response.json()["error_code"] == "PROJECT_NOT_FOUND"


def test_plan_requires_authentication(client: TestClient, project_id: int) -> None:
    response = client.post(f"/shorts-projects/{project_id}/plan", json={"video_format_id": 1})

    assert response.status_code == 401


# ---------------------------------------------------------------- 7.2 콘티 조회


def test_scenes_returns_spec_fields(
    client: TestClient, auth_headers: dict[str, str], project_id: int, formats: list[VideoFormat]
) -> None:
    _create_plan(client, auth_headers, project_id, formats[0].id)

    body = client.get(f"/shorts-projects/{project_id}/scenes", headers=auth_headers).json()

    assert set(body) == {"shooting_summary", "scenes"}
    assert set(body["scenes"][0]) == {
        "id",
        "scene_order",
        "scene_description",
        "scene_dialogue",
        "scene_subtitle",
        "shot_type",
        "target_duration_sec",
    }


def test_scenes_include_summary_for_prep_screen(
    client: TestClient, auth_headers: dict[str, str], project_id: int, formats: list[VideoFormat]
) -> None:
    """촬영 준비 화면(#/project/:id/prep)을 다시 열 때 요약이 필요하다.

    AI가 만든 값이라 재계산할 수 없어 저장해두고 여기서 돌려준다.
    """
    created = _create_plan(client, auth_headers, project_id, formats[0].id).json()

    reloaded = client.get(f"/shorts-projects/{project_id}/scenes", headers=auth_headers).json()

    assert reloaded["shooting_summary"] == created["shooting_summary"]


def test_scenes_are_empty_before_plan(
    client: TestClient, auth_headers: dict[str, str], project_id: int
) -> None:
    body = client.get(f"/shorts-projects/{project_id}/scenes", headers=auth_headers).json()

    assert body["shooting_summary"] is None
    assert body["scenes"] == []


def test_scenes_are_ordered(
    client: TestClient, auth_headers: dict[str, str], project_id: int, formats: list[VideoFormat]
) -> None:
    _create_plan(client, auth_headers, project_id, formats[0].id)

    scenes = client.get(f"/shorts-projects/{project_id}/scenes", headers=auth_headers).json()[
        "scenes"
    ]

    assert [scene["scene_order"] for scene in scenes] == sorted(
        scene["scene_order"] for scene in scenes
    )


# ---------------------------------------------------------------- 7.2 콘티 수정


def test_patch_updates_dialogue_and_subtitle(
    client: TestClient, auth_headers: dict[str, str], project_id: int, formats: list[VideoFormat]
) -> None:
    scene_id = _create_plan(client, auth_headers, project_id, formats[0].id).json()[
        "scenes_preview"
    ][0]["id"]

    response = client.patch(
        f"/shorts-projects/{project_id}/scenes",
        json={
            "scenes": [
                {"id": scene_id, "scene_dialogue": "드디어 공개!", "scene_subtitle": "드디어!"}
            ]
        },
        headers=auth_headers,
    )

    assert response.status_code == 200
    assert response.json() == {"message": "콘티가 수정되었습니다.", "updated_count": 1}

    scenes = client.get(f"/shorts-projects/{project_id}/scenes", headers=auth_headers).json()[
        "scenes"
    ]
    changed = next(scene for scene in scenes if scene["id"] == scene_id)
    assert changed["scene_dialogue"] == "드디어 공개!"
    assert changed["scene_subtitle"] == "드디어!"


def test_patch_updates_multiple_scenes(
    client: TestClient, auth_headers: dict[str, str], project_id: int, formats: list[VideoFormat]
) -> None:
    preview = _create_plan(client, auth_headers, project_id, formats[0].id).json()["scenes_preview"]

    response = client.patch(
        f"/shorts-projects/{project_id}/scenes",
        json={
            "scenes": [
                {"id": preview[0]["id"], "scene_dialogue": "첫 장면"},
                {"id": preview[1]["id"], "scene_dialogue": "둘째 장면"},
            ]
        },
        headers=auth_headers,
    )

    assert response.json()["updated_count"] == 2


def test_patch_rejects_scene_from_another_project(
    client: TestClient, auth_headers: dict[str, str], project_id: int, formats: list[VideoFormat]
) -> None:
    """남의 프로젝트 장면이 섞이면 하나도 반영하지 않는다.

    일부만 적용하면 프론트는 성공으로 알고 넘어가는데 실제로는 절반만 저장된다.
    """
    mine = _create_plan(client, auth_headers, project_id, formats[0].id).json()["scenes_preview"]

    store_id = client.post(
        "/stores", json={**STORE_BODY, "name": "두번째"}, headers=auth_headers
    ).json()["id"]
    other_project = client.post(
        "/shorts-projects",
        json={"store_id": store_id, "promotion_purpose": "가게소개"},
        headers=auth_headers,
    ).json()["id"]
    theirs = _create_plan(client, auth_headers, other_project, formats[1].id).json()[
        "scenes_preview"
    ]

    response = client.patch(
        f"/shorts-projects/{project_id}/scenes",
        json={
            "scenes": [
                {"id": mine[0]["id"], "scene_dialogue": "반영되면 안 됨"},
                {"id": theirs[0]["id"], "scene_dialogue": "남의 장면"},
            ]
        },
        headers=auth_headers,
    )

    assert response.status_code == 400
    assert response.json()["error_code"] == "SCENE_NOT_IN_PROJECT"

    # 하나도 반영되지 않았어야 한다
    scenes = client.get(f"/shorts-projects/{project_id}/scenes", headers=auth_headers).json()[
        "scenes"
    ]
    assert all(scene["scene_dialogue"] != "반영되면 안 됨" for scene in scenes)


def test_patch_rejects_unknown_scene_id(
    client: TestClient, auth_headers: dict[str, str], project_id: int, formats: list[VideoFormat]
) -> None:
    _create_plan(client, auth_headers, project_id, formats[0].id)

    response = client.patch(
        f"/shorts-projects/{project_id}/scenes",
        json={"scenes": [{"id": 999999, "scene_dialogue": "없는 장면"}]},
        headers=auth_headers,
    )

    assert response.status_code == 400
    assert response.json()["error_code"] == "SCENE_NOT_IN_PROJECT"


def test_patch_requires_at_least_one_scene(
    client: TestClient, auth_headers: dict[str, str], project_id: int
) -> None:
    response = client.patch(
        f"/shorts-projects/{project_id}/scenes", json={"scenes": []}, headers=auth_headers
    )

    assert response.status_code == 422


def test_scenes_hidden_from_other_user(
    client: TestClient, project_id: int, other_headers: dict[str, str]
) -> None:
    assert (
        client.get(f"/shorts-projects/{project_id}/scenes", headers=other_headers).status_code
        == 404
    )


def test_plan_leaves_title_null_without_ai(
    client: TestClient, auth_headers: dict[str, str], project_id: int
) -> None:
    """AI 연동 전에는 제목을 지어내지 않는다 — 목록 카드에 가짜 제목이 뜨면 안 된다."""
    body = client.get(f"/shorts-projects/{project_id}", headers=auth_headers).json()

    assert body["project_title"] is None


def test_replanning_keeps_existing_title(
    client: TestClient,
    auth_headers: dict[str, str],
    db_session: Session,
    project_id: int,
    formats: list[VideoFormat],
) -> None:
    """AI가 제목을 안 주는 재기획으로 멀쩡한 제목이 사라지면 카드가 도로 밋밋해진다."""
    project = db_session.get(ShortsProject, project_id)
    assert project is not None
    project.project_title = "신메뉴 로제떡볶이 가격 맞히기"
    db_session.commit()

    client.post(
        f"/shorts-projects/{project_id}/plan",
        json={"video_format_id": formats[0].id},
        headers=auth_headers,
    )

    body = client.get(f"/shorts-projects/{project_id}", headers=auth_headers).json()
    assert body["project_title"] == "신메뉴 로제떡볶이 가격 맞히기"
