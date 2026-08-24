"""숏폼 프로젝트 API 테스트 (API명세서 4.1~4.3).

핵심은 `promotion_detail`이 `promotion_purpose`에 따라 4갈래로 갈리는 검증이다.
판별자가 요청 Body가 아니라 DB에 있어서 서비스 계층이 직접 분기한다.
"""

from typing import Any

import pytest
from fastapi.testclient import TestClient

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


def _create_project(
    client: TestClient, headers: dict[str, str], store_id: int, purpose: str = "메뉴소개"
) -> int:
    response = client.post(
        "/shorts-projects",
        json={"store_id": store_id, "promotion_purpose": purpose},
        headers=headers,
    )
    assert response.status_code == 201, response.text
    return response.json()["id"]


def _create_menu(client: TestClient, headers: dict[str, str], store_id: int) -> int:
    return client.post(
        f"/stores/{store_id}/menus", json={"name": "떡볶이", "price": 4000}, headers=headers
    ).json()["id"]


# ---------------------------------------------------------------- 4.1 생성 / 목록


def test_create_project_returns_spec_fields(
    client: TestClient, auth_headers: dict[str, str], store_id: int
) -> None:
    response = client.post(
        "/shorts-projects",
        json={"store_id": store_id, "promotion_purpose": "메뉴소개"},
        headers=auth_headers,
    )

    assert response.status_code == 201
    body = response.json()
    assert set(body) == {"id", "store_id", "promotion_purpose", "shorts_status", "created_at"}
    assert body["shorts_status"] == "DRAFT"
    assert body["created_at"].endswith("Z")


def test_cannot_create_project_on_other_users_store(
    client: TestClient, store_id: int, other_headers: dict[str, str]
) -> None:
    response = client.post(
        "/shorts-projects",
        json={"store_id": store_id, "promotion_purpose": "메뉴소개"},
        headers=other_headers,
    )

    assert response.status_code == 404
    assert response.json()["error_code"] == "STORE_NOT_FOUND"


def test_create_rejects_unknown_purpose(
    client: TestClient, auth_headers: dict[str, str], store_id: int
) -> None:
    response = client.post(
        "/shorts-projects",
        json={"store_id": store_id, "promotion_purpose": "없는목적"},
        headers=auth_headers,
    )

    assert response.status_code == 422


def test_list_returns_spec_fields(
    client: TestClient, auth_headers: dict[str, str], store_id: int
) -> None:
    _create_project(client, auth_headers, store_id)

    body = client.get("/shorts-projects", headers=auth_headers).json()

    assert set(body["projects"][0]) == {
        "id",
        "project_title",
        "promotion_purpose",
        "shorts_status",
        "updated_at",
    }


def test_list_filters_by_store_and_status(
    client: TestClient, auth_headers: dict[str, str], store_id: int
) -> None:
    _create_project(client, auth_headers, store_id, "메뉴소개")
    other_store = client.post(
        "/stores", json={**STORE_BODY, "name": "두번째"}, headers=auth_headers
    ).json()["id"]
    _create_project(client, auth_headers, other_store, "가게소개")

    all_projects = client.get("/shorts-projects", headers=auth_headers).json()["projects"]
    filtered = client.get(
        "/shorts-projects", params={"store_id": store_id}, headers=auth_headers
    ).json()["projects"]
    by_status = client.get(
        "/shorts-projects", params={"status": "COMPLETED"}, headers=auth_headers
    ).json()["projects"]

    assert len(all_projects) == 2
    assert [p["promotion_purpose"] for p in filtered] == ["메뉴소개"]
    assert by_status == []


def test_list_excludes_other_users_projects(
    client: TestClient, auth_headers: dict[str, str], store_id: int, other_headers: dict[str, str]
) -> None:
    _create_project(client, auth_headers, store_id)

    assert client.get("/shorts-projects", headers=other_headers).json()["projects"] == []


def test_list_requires_authentication(client: TestClient) -> None:
    assert client.get("/shorts-projects").status_code == 401


# ---------------------------------------------------------------- 4.2 목적별 promotion_detail


def test_menu_purpose_accepts_detail_tag_and_menu_id(
    client: TestClient, auth_headers: dict[str, str], store_id: int
) -> None:
    project_id = _create_project(client, auth_headers, store_id, "메뉴소개")
    menu_id = _create_menu(client, auth_headers, store_id)

    response = client.patch(
        f"/shorts-projects/{project_id}",
        json={"menu_id": menu_id, "promotion_detail": {"detail_tag": "대표메뉴"}},
        headers=auth_headers,
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["menu_id"] == menu_id
    assert body["promotion_detail"] == {"detail_tag": "대표메뉴"}


def test_event_purpose_accepts_event_fields(
    client: TestClient, auth_headers: dict[str, str], store_id: int
) -> None:
    project_id = _create_project(client, auth_headers, store_id, "이벤트알리기")

    response = client.patch(
        f"/shorts-projects/{project_id}",
        json={
            "promotion_detail": {
                "event_name": "오픈 3주년 감사 이벤트",
                "benefit": "아메리카노 1+1",
                "period": "2026-09-01 ~ 2026-09-07",
                "condition": "매장 이용 고객 한정",
                "limit": "1일 선착순 50잔",
                "cta": "매장 방문",
            }
        },
        headers=auth_headers,
    )

    assert response.status_code == 200, response.text
    assert response.json()["promotion_detail"]["event_name"] == "오픈 3주년 감사 이벤트"


def test_store_purpose_accepts_multiple_elements(
    client: TestClient, auth_headers: dict[str, str], store_id: int
) -> None:
    project_id = _create_project(client, auth_headers, store_id, "가게소개")

    response = client.patch(
        f"/shorts-projects/{project_id}",
        json={"promotion_detail": {"elements": ["공간", "사장님/직원"]}},
        headers=auth_headers,
    )

    assert response.status_code == 200, response.text
    assert response.json()["promotion_detail"] == {"elements": ["공간", "사장님/직원"]}


def test_customer_purpose_accepts_goal_and_metric(
    client: TestClient, auth_headers: dict[str, str], store_id: int
) -> None:
    project_id = _create_project(client, auth_headers, store_id, "고객늘리기")

    response = client.patch(
        f"/shorts-projects/{project_id}",
        json={"promotion_detail": {"goal": "신규고객", "success_metric": "예약·문의 수"}},
        headers=auth_headers,
    )

    assert response.status_code == 200, response.text
    assert response.json()["promotion_detail"]["goal"] == "신규고객"


def test_detail_of_wrong_purpose_is_rejected(
    client: TestClient, auth_headers: dict[str, str], store_id: int
) -> None:
    """가게소개 프로젝트에 이벤트 필드를 보내면 400 (명세서 4.2 명시)."""
    project_id = _create_project(client, auth_headers, store_id, "가게소개")

    response = client.patch(
        f"/shorts-projects/{project_id}",
        json={"promotion_detail": {"event_name": "이벤트"}},
        headers=auth_headers,
    )

    assert response.status_code == 400
    body = response.json()
    assert body["error_code"] == "INVALID_PROMOTION_DETAIL"
    # 어느 키가 문제인지 알려줘야 프론트가 고칠 수 있다
    assert "event_name" in body["message"]


def test_detail_with_extra_key_is_rejected(
    client: TestClient, auth_headers: dict[str, str], store_id: int
) -> None:
    project_id = _create_project(client, auth_headers, store_id, "메뉴소개")

    response = client.patch(
        f"/shorts-projects/{project_id}",
        json={"promotion_detail": {"detail_tag": "대표메뉴", "무단추가": "값"}},
        headers=auth_headers,
    )

    assert response.status_code == 400
    assert response.json()["error_code"] == "INVALID_PROMOTION_DETAIL"


def test_detail_with_unknown_enum_value_is_rejected(
    client: TestClient, auth_headers: dict[str, str], store_id: int
) -> None:
    project_id = _create_project(client, auth_headers, store_id, "메뉴소개")

    response = client.patch(
        f"/shorts-projects/{project_id}",
        json={"promotion_detail": {"detail_tag": "없는태그"}},
        headers=auth_headers,
    )

    assert response.status_code == 400
    assert response.json()["error_code"] == "INVALID_PROMOTION_DETAIL"


# ---------------------------------------------------------------- 4.2 menu_id 규칙


def test_menu_id_rejected_for_non_menu_purpose(
    client: TestClient, auth_headers: dict[str, str], store_id: int
) -> None:
    """menu_id는 메뉴소개 전용 — 조용히 무시하면 프론트는 저장된 줄 안다."""
    project_id = _create_project(client, auth_headers, store_id, "가게소개")
    menu_id = _create_menu(client, auth_headers, store_id)

    response = client.patch(
        f"/shorts-projects/{project_id}", json={"menu_id": menu_id}, headers=auth_headers
    )

    assert response.status_code == 400
    assert response.json()["error_code"] == "MENU_NOT_ALLOWED"


def test_menu_id_of_another_store_is_rejected(
    client: TestClient, auth_headers: dict[str, str], store_id: int
) -> None:
    project_id = _create_project(client, auth_headers, store_id, "메뉴소개")
    other_store = client.post(
        "/stores", json={**STORE_BODY, "name": "두번째"}, headers=auth_headers
    ).json()["id"]
    other_menu = _create_menu(client, auth_headers, other_store)

    response = client.patch(
        f"/shorts-projects/{project_id}", json={"menu_id": other_menu}, headers=auth_headers
    )

    assert response.status_code == 400
    assert response.json()["error_code"] == "INVALID_REFERENCE"


def test_target_customer_of_another_store_is_rejected(
    client: TestClient, auth_headers: dict[str, str], store_id: int
) -> None:
    project_id = _create_project(client, auth_headers, store_id, "메뉴소개")
    other_store = client.post(
        "/stores", json={**STORE_BODY, "name": "두번째"}, headers=auth_headers
    ).json()["id"]
    other_target = client.post(
        f"/stores/{other_store}/target-customers",
        json={"target_type": "주", "target_description": "직장인"},
        headers=auth_headers,
    ).json()["id"]

    response = client.patch(
        f"/shorts-projects/{project_id}",
        json={"store_target_customer_id": other_target},
        headers=auth_headers,
    )

    assert response.status_code == 400
    assert response.json()["error_code"] == "INVALID_REFERENCE"


# ---------------------------------------------------------------- 4.2 응답 형태


def test_update_returns_full_settings_not_only_changed(
    client: TestClient, auth_headers: dict[str, str], store_id: int
) -> None:
    """3.1/3.2/3.4의 PATCH와 달리 4.2는 설정 전체를 돌려준다 (명세서 예시 기준)."""
    project_id = _create_project(client, auth_headers, store_id, "가게소개")

    response = client.patch(
        f"/shorts-projects/{project_id}",
        json={"face_exposure_mode": "일부노출"},
        headers=auth_headers,
    )

    assert set(response.json()) == {
        "id",
        "menu_id",
        "promotion_purpose",
        "promotion_detail",
        "store_target_customer_id",
        "face_exposure_mode",
        "shooting_condition",
        "updated_at",
    }


def test_menu_id_is_null_not_missing_for_other_purposes(
    client: TestClient, auth_headers: dict[str, str], store_id: int
) -> None:
    """메뉴소개가 아니어도 키를 빼지 않고 null로 내린다 (프론트 분기 부담 감소)."""
    project_id = _create_project(client, auth_headers, store_id, "가게소개")

    body = client.patch(
        f"/shorts-projects/{project_id}",
        json={"promotion_detail": {"elements": ["공간"]}},
        headers=auth_headers,
    ).json()

    assert "menu_id" in body
    assert body["menu_id"] is None


# ---------------------------------------------------------------- 4.3 단건 조회


def test_get_project_returns_spec_fields(
    client: TestClient, auth_headers: dict[str, str], store_id: int
) -> None:
    project_id = _create_project(client, auth_headers, store_id)

    body = client.get(f"/shorts-projects/{project_id}", headers=auth_headers).json()

    assert set(body) == {
        "id",
        "store_id",
        "project_title",
        "video_format_id",
        "store_target_customer_id",
        "menu_id",
        "promotion_purpose",
        "promotion_detail",
        "face_exposure_mode",
        "shooting_condition",
        "shorts_status",
        "created_at",
        "updated_at",
    }
    # 포맷은 R05에서 고른다 — 아직 선택 전이다
    assert body["video_format_id"] is None


def test_project_hidden_from_other_user(
    client: TestClient, auth_headers: dict[str, str], store_id: int, other_headers: dict[str, str]
) -> None:
    project_id = _create_project(client, auth_headers, store_id)

    assert client.get(f"/shorts-projects/{project_id}", headers=other_headers).status_code == 404
    assert (
        client.patch(
            f"/shorts-projects/{project_id}",
            json={"face_exposure_mode": "비노출"},
            headers=other_headers,
        ).status_code
        == 404
    )


def test_unknown_project_returns_404(client: TestClient, auth_headers: dict[str, str]) -> None:
    response = client.get("/shorts-projects/999999", headers=auth_headers)

    assert response.status_code == 404
    assert response.json()["error_code"] == "PROJECT_NOT_FOUND"


# ---------------------------------------------------------------- 4.1 promotion_purpose 필수


def test_create_project_requires_promotion_purpose(
    client: TestClient, auth_headers: dict[str, str], store_id: int
) -> None:
    """홈 피드 진입에도 목적 선택 화면을 두기로 확정(2026-08-23) — 목적은 필수다.

    한때 선택으로 완화했다가 되돌린 계약이라, 회귀하지 않도록 테스트로 고정한다.
    """
    response = client.post("/shorts-projects", json={"store_id": store_id}, headers=auth_headers)

    assert response.status_code == 422
    body = response.json()
    assert body["error_code"] == "VALIDATION_ERROR"
    assert "promotion_purpose" in body["message"]


def test_purpose_cannot_be_changed_after_creation(
    client: TestClient, auth_headers: dict[str, str], store_id: int
) -> None:
    """목적은 생성 후 바꿀 수 없다(2026-08-23 확정).

    4.2가 `promotion_purpose`를 받지 않으므로 보내도 무시되고 원래 값이 유지된다.
    바꾸고 싶으면 프로젝트를 새로 만든다.
    """
    project_id = _create_project(client, auth_headers, store_id, "메뉴소개")

    response = client.patch(
        f"/shorts-projects/{project_id}",
        json={"promotion_purpose": "가게소개"},
        headers=auth_headers,
    )

    assert response.status_code == 200
    assert response.json()["promotion_purpose"] == "메뉴소개"


def test_settings_unrelated_to_purpose_still_work(
    client: TestClient, auth_headers: dict[str, str], store_id: int
) -> None:
    project_id = _create_project(client, auth_headers, store_id, "가게소개")

    response = client.patch(
        f"/shorts-projects/{project_id}",
        json={"face_exposure_mode": "비노출", "shooting_condition": "혼자 촬영"},
        headers=auth_headers,
    )

    assert response.status_code == 200
    assert response.json()["face_exposure_mode"] == "비노출"


def test_video_format_id_in_patch_is_ignored(
    client: TestClient, auth_headers: dict[str, str], store_id: int
) -> None:
    """포맷 선택은 7.1에서만 저장한다 — 4.2로 보내도 반영되지 않는다.

    프론트가 한때 4.2로도 보내고 있었는데 스키마에 없어 조용히 버려지고 있었다.
    그 동작이 유지되는지(=엉뚱하게 저장되지 않는지) 고정한다.
    """
    project_id = _create_project(client, auth_headers, store_id, "메뉴소개")

    response = client.patch(
        f"/shorts-projects/{project_id}", json={"video_format_id": 71}, headers=auth_headers
    )

    assert response.status_code == 200
    detail = client.get(f"/shorts-projects/{project_id}", headers=auth_headers).json()
    assert detail["video_format_id"] is None
