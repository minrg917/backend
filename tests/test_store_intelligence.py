"""가게 인텔리전스 API 테스트 (API명세서 3.1 / 3.2 / 3.4 / 3.5)."""

from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.models.mixins import utcnow
from app.models.store_insight import StoreInsight
from app.models.store_target_customer import TargetStatus

STORE_BODY: dict[str, Any] = {
    "name": "행복분식 강남점",
    "category": "분식",
    "address": "서울 강남구 테헤란로 1길 10",
    "info_source": "KAKAO",
}


@pytest.fixture
def store_id(client: TestClient, auth_headers: dict[str, str]) -> int:
    response = client.post("/stores", json=STORE_BODY, headers=auth_headers)
    assert response.status_code == 201, response.text
    return response.json()["id"]


@pytest.fixture
def other_headers(client: TestClient) -> dict[str, str]:
    """다른 사용자 — 소유권 검증 테스트용."""
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


# ---------------------------------------------------------------- 3.1 기본정보


def test_get_store_returns_spec_fields(
    client: TestClient, auth_headers: dict[str, str], store_id: int
) -> None:
    response = client.get(f"/stores/{store_id}", headers=auth_headers)

    assert response.status_code == 200
    body = response.json()
    assert set(body) == {
        "id",
        "name",
        "category",
        "sub_category",
        "address",
        "latitude",
        "longitude",
        "phone",
        "business_hours",
        "brand_tone",
        "brand_color",
        "logo_url",
        "info_source",
        "external_channel_url",
        "updated_at",
    }
    assert body["name"] == STORE_BODY["name"]
    assert body["updated_at"].endswith("Z")


def test_patch_store_returns_only_changed_fields(
    client: TestClient, auth_headers: dict[str, str], store_id: int
) -> None:
    """명세서 3.1 PATCH 응답은 바꾼 필드 + id + updated_at만 담는다."""
    response = client.patch(
        f"/stores/{store_id}",
        json={"business_hours": "매일 10:00-22:00", "brand_color": "#FF6B35"},
        headers=auth_headers,
    )

    assert response.status_code == 200
    assert set(response.json()) == {"id", "business_hours", "brand_color", "updated_at"}


def test_patch_store_leaves_unsent_fields_untouched(
    client: TestClient, auth_headers: dict[str, str], store_id: int
) -> None:
    client.patch(f"/stores/{store_id}", json={"brand_tone": "정겨운"}, headers=auth_headers)

    store = client.get(f"/stores/{store_id}", headers=auth_headers).json()
    assert store["brand_tone"] == "정겨운"
    assert store["name"] == STORE_BODY["name"]  # 안 보낸 필드는 그대로
    assert store["address"] == STORE_BODY["address"]


def test_patch_store_can_clear_a_field_with_explicit_null(
    client: TestClient, auth_headers: dict[str, str], store_id: int
) -> None:
    """null을 명시적으로 보내면 값을 비우는 것으로 처리한다."""
    client.patch(f"/stores/{store_id}", json={"phone": "02-1111-2222"}, headers=auth_headers)
    client.patch(f"/stores/{store_id}", json={"phone": None}, headers=auth_headers)

    assert client.get(f"/stores/{store_id}", headers=auth_headers).json()["phone"] is None


def test_store_detail_hidden_from_other_user(
    client: TestClient, store_id: int, other_headers: dict[str, str]
) -> None:
    assert client.get(f"/stores/{store_id}", headers=other_headers).status_code == 404
    assert (
        client.patch(f"/stores/{store_id}", json={"brand_tone": "x"}, headers=other_headers)
    ).status_code == 404


def test_store_detail_requires_authentication(client: TestClient, store_id: int) -> None:
    assert client.get(f"/stores/{store_id}").status_code == 401


# ---------------------------------------------------------------- 3.2 대표메뉴


def _create_menu(client: TestClient, headers: dict[str, str], store_id: int, **over: Any) -> Any:
    body = {"name": "치즈라면", "price": 5000, "description": "얼큰한 라면", "is_new_menu": True}
    return client.post(f"/stores/{store_id}/menus", json={**body, **over}, headers=headers)


def test_create_menu_returns_spec_fields(
    client: TestClient, auth_headers: dict[str, str], store_id: int
) -> None:
    response = _create_menu(client, auth_headers, store_id)

    assert response.status_code == 201
    assert set(response.json()) == {"id", "name", "price", "is_new_menu", "created_at"}


def test_menu_flags_default_to_false(
    client: TestClient, auth_headers: dict[str, str], store_id: int
) -> None:
    _create_menu(client, auth_headers, store_id, is_new_menu=False)

    menu = client.get(f"/stores/{store_id}/menus", headers=auth_headers).json()["menus"][0]
    assert menu["is_new_menu"] is False
    assert menu["is_event_menu"] is False
    assert menu["is_sold_out"] is False


def test_list_menus_returns_spec_fields(
    client: TestClient, auth_headers: dict[str, str], store_id: int
) -> None:
    _create_menu(client, auth_headers, store_id)

    body = client.get(f"/stores/{store_id}/menus", headers=auth_headers).json()

    assert set(body["menus"][0]) == {
        "id",
        "name",
        "price",
        "description",
        "image_url",
        "is_new_menu",
        "is_event_menu",
        "is_sold_out",
    }


def test_patch_menu_returns_only_changed_fields(
    client: TestClient, auth_headers: dict[str, str], store_id: int
) -> None:
    menu_id = _create_menu(client, auth_headers, store_id).json()["id"]

    response = client.patch(
        f"/stores/{store_id}/menus/{menu_id}", json={"is_sold_out": True}, headers=auth_headers
    )

    assert response.status_code == 200
    assert set(response.json()) == {"id", "is_sold_out", "updated_at"}
    assert response.json()["is_sold_out"] is True


def test_delete_menu(client: TestClient, auth_headers: dict[str, str], store_id: int) -> None:
    menu_id = _create_menu(client, auth_headers, store_id).json()["id"]

    response = client.delete(f"/stores/{store_id}/menus/{menu_id}", headers=auth_headers)

    assert response.status_code == 200
    assert response.json() == {"message": "메뉴가 삭제되었습니다."}
    assert client.get(f"/stores/{store_id}/menus", headers=auth_headers).json()["menus"] == []


def test_menu_of_another_store_is_not_reachable(
    client: TestClient, auth_headers: dict[str, str], store_id: int
) -> None:
    """내 가게 경로로 다른 가게의 메뉴 ID를 조회할 수 없어야 한다."""
    menu_id = _create_menu(client, auth_headers, store_id).json()["id"]
    other_store_id = client.post(
        "/stores", json={**STORE_BODY, "name": "두번째가게"}, headers=auth_headers
    ).json()["id"]

    response = client.patch(
        f"/stores/{other_store_id}/menus/{menu_id}",
        json={"is_sold_out": True},
        headers=auth_headers,
    )

    assert response.status_code == 404
    assert response.json()["error_code"] == "MENU_NOT_FOUND"


def test_menu_price_cannot_be_negative(
    client: TestClient, auth_headers: dict[str, str], store_id: int
) -> None:
    response = _create_menu(client, auth_headers, store_id, price=-1)

    assert response.status_code == 422
    assert response.json()["error_code"] == "VALIDATION_ERROR"


# ---------------------------------------------------------------- 3.4 타깃고객


def _create_target(client: TestClient, headers: dict[str, str], store_id: int, **over: Any) -> Any:
    body = {"target_type": "보조", "target_description": "자녀와 함께 방문하는 30-40대 학부모"}
    return client.post(
        f"/stores/{store_id}/target-customers", json={**body, **over}, headers=headers
    )


def test_create_target_customer_returns_spec_fields(
    client: TestClient, auth_headers: dict[str, str], store_id: int
) -> None:
    response = _create_target(client, auth_headers, store_id)

    assert response.status_code == 201
    assert set(response.json()) == {"id", "target_type", "target_description", "created_at"}


def test_owner_created_target_is_confirmed_without_ai_confidence(
    client: TestClient, auth_headers: dict[str, str], store_id: int
) -> None:
    """사장님이 직접 만든 타깃은 확인받을 게 없으므로 CONFIRMED, AI 신뢰도는 없다."""
    _create_target(client, auth_headers, store_id)

    target = client.get(f"/stores/{store_id}/target-customers", headers=auth_headers).json()[
        "target_customers"
    ][0]
    assert target["status"] == TargetStatus.CONFIRMED
    assert target["ai_confidence"] is None


def test_list_target_customers_returns_spec_fields(
    client: TestClient, auth_headers: dict[str, str], store_id: int
) -> None:
    _create_target(client, auth_headers, store_id)

    body = client.get(f"/stores/{store_id}/target-customers", headers=auth_headers).json()

    assert set(body["target_customers"][0]) == {
        "id",
        "target_type",
        "target_description",
        "ai_confidence",
        "status",
    }


def test_patch_target_customer_returns_only_changed_fields(
    client: TestClient, auth_headers: dict[str, str], store_id: int
) -> None:
    target_id = _create_target(client, auth_headers, store_id).json()["id"]

    response = client.patch(
        f"/stores/{store_id}/target-customers/{target_id}",
        json={"status": "HIDDEN"},
        headers=auth_headers,
    )

    assert response.status_code == 200
    assert set(response.json()) == {"id", "status", "updated_at"}
    assert response.json()["status"] == "HIDDEN"


def test_patch_target_customer_rejects_unknown_status(
    client: TestClient, auth_headers: dict[str, str], store_id: int
) -> None:
    target_id = _create_target(client, auth_headers, store_id).json()["id"]

    response = client.patch(
        f"/stores/{store_id}/target-customers/{target_id}",
        json={"status": "NOT_A_STATUS"},
        headers=auth_headers,
    )

    assert response.status_code == 422


# ---------------------------------------------------------------- 3.5 인사이트


def _add_insight(db: Session, store_id: int, insight_type: str, title: str) -> StoreInsight:
    insight = StoreInsight(
        store_id=store_id,
        insight_type=insight_type,
        insight_title=title,
        insight_content="내용",
        insight_source="외부데이터",
        generated_at=utcnow(),
    )
    db.add(insight)
    db.commit()
    return insight


def test_list_insights_returns_spec_fields(
    client: TestClient, auth_headers: dict[str, str], store_id: int, db_session: Session
) -> None:
    _add_insight(db_session, store_id, "상권분석", "역세권 오피스 상권")

    body = client.get(f"/stores/{store_id}/insights", headers=auth_headers).json()

    assert set(body["insights"][0]) == {
        "id",
        "insight_type",
        "insight_title",
        "insight_content",
        "insight_source",
        "generated_at",
    }
    assert body["insights"][0]["generated_at"].endswith("Z")


def test_list_insights_filters_by_type(
    client: TestClient, auth_headers: dict[str, str], store_id: int, db_session: Session
) -> None:
    _add_insight(db_session, store_id, "상권분석", "상권 A")
    _add_insight(db_session, store_id, "카드뉴스", "카드뉴스 B")

    filtered = client.get(
        f"/stores/{store_id}/insights", params={"type": "상권분석"}, headers=auth_headers
    ).json()["insights"]

    assert [i["insight_title"] for i in filtered] == ["상권 A"]


def test_list_insights_without_type_returns_all(
    client: TestClient, auth_headers: dict[str, str], store_id: int, db_session: Session
) -> None:
    _add_insight(db_session, store_id, "상권분석", "상권 A")
    _add_insight(db_session, store_id, "카드뉴스", "카드뉴스 B")

    body = client.get(f"/stores/{store_id}/insights", headers=auth_headers).json()

    assert len(body["insights"]) == 2


def test_insights_hidden_from_other_user(
    client: TestClient, store_id: int, other_headers: dict[str, str]
) -> None:
    response = client.get(f"/stores/{store_id}/insights", headers=other_headers)

    assert response.status_code == 404
    assert response.json()["error_code"] == "STORE_NOT_FOUND"


def test_list_includes_hidden_targets(
    client: TestClient, auth_headers: dict[str, str], store_id: int
) -> None:
    """숨김 타깃도 목록에 그대로 포함된다 (API명세서 3.4 노트, 2026-08-23 확정).

    화면에서 숨길지는 프론트 판단이므로 서버가 걸러내면 안 된다.
    """
    target_id = _create_target(client, auth_headers, store_id).json()["id"]
    client.patch(
        f"/stores/{store_id}/target-customers/{target_id}",
        json={"status": "HIDDEN"},
        headers=auth_headers,
    )

    targets = client.get(f"/stores/{store_id}/target-customers", headers=auth_headers).json()[
        "target_customers"
    ]

    assert [t["status"] for t in targets] == ["HIDDEN"]
