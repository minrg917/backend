"""숏폼 포맷 API 테스트 (API명세서 5.1~5.2)."""

from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.models.video_format import VideoFormat


def _add_format(db: Session, **overrides: Any) -> VideoFormat:
    base: dict[str, Any] = {
        "format_title": "가격 공개 반전 챌린지",
        "format_type": "밈",
        "reference_url": "https://www.youtube.com/watch?v=aaa",
        "source_platform": "YOUTUBE",
        "expected_duration_sec": 25,
        "shooting_difficulty": "하",
        "face_exposure_level": "낮음",
    }
    video_format = VideoFormat(**{**base, **overrides})
    db.add(video_format)
    db.commit()
    db.refresh(video_format)
    return video_format


@pytest.fixture
def formats(db_session: Session) -> list[VideoFormat]:
    return [
        _add_format(
            db_session,
            format_title="가격 공개 반전 챌린지",
            format_type="밈",
            reference_url="https://youtu.be/1",
            face_exposure_level="낮음",
        ),
        _add_format(
            db_session,
            format_title="사장님 메뉴 추천",
            format_type="잔잔한 소개",
            reference_url="https://youtu.be/2",
            face_exposure_level="높음",
        ),
        _add_format(
            db_session,
            format_title="가게 한 바퀴",
            format_type="잔잔한 소개",
            reference_url="https://youtu.be/3",
            face_exposure_level="낮음",
        ),
    ]


# ---------------------------------------------------------------- 5.1 목록


def test_list_returns_spec_fields(
    client: TestClient, auth_headers: dict[str, str], formats: list[VideoFormat]
) -> None:
    response = client.get("/video-formats", headers=auth_headers)

    assert response.status_code == 200
    assert set(response.json()["formats"][0]) == {
        "id",
        "format_title",
        "format_type",
        "expected_duration_sec",
        "shooting_difficulty",
        "face_exposure_level",
        "reference_url",
        "source_platform",
        "recommend_reasons",
    }


def test_recommend_reasons_is_empty_before_ai(
    client: TestClient, auth_headers: dict[str, str], formats: list[VideoFormat]
) -> None:
    """AI 연동 전이라 추천 이유는 비어 있다. 키 자체는 계약대로 존재해야 한다."""
    body = client.get("/video-formats", headers=auth_headers).json()

    assert all(item["recommend_reasons"] == [] for item in body["formats"])


def test_list_filters_by_format_type(
    client: TestClient, auth_headers: dict[str, str], formats: list[VideoFormat]
) -> None:
    body = client.get("/video-formats", params={"format_type": "밈"}, headers=auth_headers).json()

    assert [f["format_title"] for f in body["formats"]] == ["가격 공개 반전 챌린지"]


def test_list_filters_by_face_exposure_level(
    client: TestClient, auth_headers: dict[str, str], formats: list[VideoFormat]
) -> None:
    body = client.get(
        "/video-formats", params={"face_exposure_level": "낮음"}, headers=auth_headers
    ).json()

    assert len(body["formats"]) == 2


def test_list_searches_by_keyword(
    client: TestClient, auth_headers: dict[str, str], formats: list[VideoFormat]
) -> None:
    body = client.get("/video-formats", params={"keyword": "가게"}, headers=auth_headers).json()

    assert [f["format_title"] for f in body["formats"]] == ["가게 한 바퀴"]


def test_list_combines_filters(
    client: TestClient, auth_headers: dict[str, str], formats: list[VideoFormat]
) -> None:
    body = client.get(
        "/video-formats",
        params={"format_type": "잔잔한 소개", "face_exposure_level": "낮음"},
        headers=auth_headers,
    ).json()

    assert [f["format_title"] for f in body["formats"]] == ["가게 한 바퀴"]


def test_list_returns_empty_when_nothing_matches(
    client: TestClient, auth_headers: dict[str, str], formats: list[VideoFormat]
) -> None:
    """0건은 에러가 아니다 — 프론트가 조건 완화를 제안하는 분기다(S05.2.2)."""
    response = client.get(
        "/video-formats", params={"keyword": "존재하지않는포맷"}, headers=auth_headers
    )

    assert response.status_code == 200
    assert response.json()["formats"] == []


def test_list_paginates(
    client: TestClient, auth_headers: dict[str, str], formats: list[VideoFormat]
) -> None:
    """피드 무한 스크롤용 페이지네이션."""
    page1 = client.get(
        "/video-formats", params={"page": 1, "size": 2}, headers=auth_headers
    ).json()["formats"]
    page2 = client.get(
        "/video-formats", params={"page": 2, "size": 2}, headers=auth_headers
    ).json()["formats"]

    assert len(page1) == 2
    assert len(page2) == 1
    assert {f["id"] for f in page1}.isdisjoint({f["id"] for f in page2})


def test_list_works_without_project_id(
    client: TestClient, auth_headers: dict[str, str], formats: list[VideoFormat]
) -> None:
    """홈 피드를 프로젝트 생성 전에 볼 수 있어야 한다 — project_id는 선택이다."""
    response = client.get("/video-formats", headers=auth_headers)

    assert response.status_code == 200
    assert len(response.json()["formats"]) == 3


def test_list_rejects_unknown_sort(client: TestClient, auth_headers: dict[str, str]) -> None:
    response = client.get("/video-formats", params={"sort": "없는정렬"}, headers=auth_headers)

    assert response.status_code == 422


def test_list_requires_authentication(client: TestClient) -> None:
    assert client.get("/video-formats").status_code == 401


# ---------------------------------------------------------------- 5.2 단건 상세


def test_detail_returns_spec_fields(
    client: TestClient, auth_headers: dict[str, str], formats: list[VideoFormat]
) -> None:
    response = client.get(f"/video-formats/{formats[0].id}", headers=auth_headers)

    assert response.status_code == 200
    assert set(response.json()) == {
        "id",
        "format_title",
        "format_type",
        "reference_url",
        "source_platform",
        "expected_duration_sec",
        "shooting_difficulty",
        "face_exposure_level",
    }


def test_detail_returns_404_for_unknown_format(
    client: TestClient, auth_headers: dict[str, str]
) -> None:
    response = client.get("/video-formats/999999", headers=auth_headers)

    assert response.status_code == 404
    assert response.json()["error_code"] == "FORMAT_NOT_FOUND"


def test_detail_requires_authentication(client: TestClient) -> None:
    assert client.get("/video-formats/1").status_code == 401


# ---------------------------------------------------------------- 프로젝트 연결


def test_project_can_reference_a_format(
    client: TestClient, auth_headers: dict[str, str], formats: list[VideoFormat]
) -> None:
    """R04에서 FK 없이 두었던 video_format_id가 이제 실제 포맷을 가리킨다.

    다만 **포맷을 저장하는 API는 아직 없다**(`docs/PM_DECISIONS.md` 「확인 대기 중」).
    여기서는 조회 시 null로 나오는 것까지만 확인한다.
    """
    store_id = client.post(
        "/stores",
        json={"name": "행복분식", "category": "분식", "address": "서울 강남구"},
        headers=auth_headers,
    ).json()["id"]
    project_id = client.post(
        "/shorts-projects",
        json={"store_id": store_id, "promotion_purpose": "메뉴소개"},
        headers=auth_headers,
    ).json()["id"]

    body = client.get(f"/shorts-projects/{project_id}", headers=auth_headers).json()

    assert body["video_format_id"] is None
