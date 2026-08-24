"""가게사진 API 테스트 (API명세서 3.3) + 저장소 계층."""

import io
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.storage import LocalStorage, get_storage, to_public_url

# 1x1 PNG. 실제 이미지 바이트라야 업로드 경로를 그대로 통과한다.
PNG_BYTES = bytes.fromhex(
    "89504e470d0a1a0a0000000d494844520000000100000001080600000"
    "01f15c4890000000a49444154789c6300010000050001"
    "0d0a2db40000000049454e44ae426082"
)


@pytest.fixture
def store_id(client: TestClient, auth_headers: dict[str, str]) -> int:
    response = client.post(
        "/stores",
        json={"name": "행복분식", "category": "분식", "address": "서울 강남구 테헤란로 1길 10"},
        headers=auth_headers,
    )
    return response.json()["id"]


def _upload(
    client: TestClient,
    headers: dict[str, str],
    store_id: int,
    *,
    content: bytes = PNG_BYTES,
    filename: str = "photo.png",
    content_type: str = "image/png",
    category: str | None = None,
) -> Any:
    data = {"category": category} if category else None
    return client.post(
        f"/stores/{store_id}/photos",
        files={"file": (filename, io.BytesIO(content), content_type)},
        data=data,
        headers=headers,
    )


# ---------------------------------------------------------------- 업로드


def test_upload_returns_spec_fields(
    client: TestClient, auth_headers: dict[str, str], store_id: int
) -> None:
    response = _upload(client, auth_headers, store_id, category="간판")

    assert response.status_code == 201, response.text
    body = response.json()
    assert set(body) == {"id", "file_url", "category", "has_sensitive_info", "created_at"}
    assert body["category"] == "간판"
    assert body["has_sensitive_info"] is None
    assert body["created_at"].endswith("Z")


def test_upload_returns_full_url_not_storage_key(
    client: TestClient, auth_headers: dict[str, str], store_id: int
) -> None:
    """DB에는 키를 저장하지만 응답은 명세서대로 전체 URL이어야 한다."""
    body = _upload(client, auth_headers, store_id).json()

    assert body["file_url"].startswith("http://")
    assert "/media/stores/" in body["file_url"]


def test_uploaded_file_is_actually_written(
    client: TestClient, auth_headers: dict[str, str], store_id: int, temp_media_root: Path
) -> None:
    _upload(client, auth_headers, store_id)

    saved = list(temp_media_root.rglob("*.png"))
    assert len(saved) == 1
    assert saved[0].read_bytes() == PNG_BYTES


def test_upload_without_category_defaults_to_etc(
    client: TestClient, auth_headers: dict[str, str], store_id: int
) -> None:
    """AI 자동분류가 붙기 전까지 분류를 안 주면 '기타'다."""
    assert _upload(client, auth_headers, store_id).json()["category"] == "기타"


def test_upload_generates_server_side_filename(
    client: TestClient, auth_headers: dict[str, str], store_id: int, temp_media_root: Path
) -> None:
    """원본 파일명을 경로에 쓰지 않는다 — 중복·한글 인코딩·경로 조작 회피."""
    _upload(client, auth_headers, store_id, filename="../../위험한 이름.png")

    saved = list(temp_media_root.rglob("*.png"))
    assert len(saved) == 1
    assert "위험한" not in saved[0].name
    assert temp_media_root in saved[0].parents


def test_upload_rejects_non_image(
    client: TestClient, auth_headers: dict[str, str], store_id: int
) -> None:
    response = _upload(
        client,
        auth_headers,
        store_id,
        content=b"not an image",
        filename="doc.pdf",
        content_type="application/pdf",
    )

    assert response.status_code == 415
    assert response.json()["error_code"] == "UNSUPPORTED_FILE_TYPE"


def test_upload_rejects_empty_file(
    client: TestClient, auth_headers: dict[str, str], store_id: int
) -> None:
    response = _upload(client, auth_headers, store_id, content=b"")

    assert response.status_code == 400
    assert response.json()["error_code"] == "EMPTY_FILE"


def test_upload_rejects_oversized_file(
    client: TestClient,
    auth_headers: dict[str, str],
    store_id: int,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.core import config

    monkeypatch.setattr(config.settings, "MAX_UPLOAD_SIZE_MB", 0)

    response = _upload(client, auth_headers, store_id)

    assert response.status_code == 413
    assert response.json()["error_code"] == "FILE_TOO_LARGE"


def test_upload_rejects_unknown_category(
    client: TestClient, auth_headers: dict[str, str], store_id: int
) -> None:
    response = _upload(client, auth_headers, store_id, category="없는분류")

    assert response.status_code == 422
    assert response.json()["error_code"] == "VALIDATION_ERROR"


def test_upload_requires_authentication(client: TestClient, store_id: int) -> None:
    response = client.post(
        f"/stores/{store_id}/photos",
        files={"file": ("photo.png", io.BytesIO(PNG_BYTES), "image/png")},
    )

    assert response.status_code == 401


# ---------------------------------------------------------------- 분류 수정 (2026-08-26)


def test_update_category_changes_classification(
    client: TestClient, auth_headers: dict[str, str], store_id: int
) -> None:
    photo_id = _upload(client, auth_headers, store_id, category="기타").json()["id"]

    response = client.patch(
        f"/stores/{store_id}/photos/{photo_id}", json={"category": "간판"}, headers=auth_headers
    )

    assert response.status_code == 200, response.text
    assert response.json() == {"id": photo_id, "category": "간판"}
    listed = client.get(f"/stores/{store_id}/photos", headers=auth_headers).json()["photos"]
    assert listed[0]["category"] == "간판"


def test_update_category_rejects_unknown_value(
    client: TestClient, auth_headers: dict[str, str], store_id: int
) -> None:
    photo_id = _upload(client, auth_headers, store_id).json()["id"]

    response = client.patch(
        f"/stores/{store_id}/photos/{photo_id}", json={"category": "없는분류"}, headers=auth_headers
    )

    assert response.status_code == 422


def test_update_category_of_another_store_is_not_reachable(
    client: TestClient, auth_headers: dict[str, str], store_id: int
) -> None:
    photo_id = _upload(client, auth_headers, store_id).json()["id"]
    other_store_id = client.post(
        "/stores",
        json={"name": "두번째가게", "category": "분식", "address": "서울 마포구 양화로 100"},
        headers=auth_headers,
    ).json()["id"]

    response = client.patch(
        f"/stores/{other_store_id}/photos/{photo_id}",
        json={"category": "간판"},
        headers=auth_headers,
    )

    assert response.status_code == 404
    assert response.json()["error_code"] == "PHOTO_NOT_FOUND"


def test_update_category_requires_authentication(
    client: TestClient, auth_headers: dict[str, str], store_id: int
) -> None:
    photo_id = _upload(client, auth_headers, store_id).json()["id"]

    response = client.patch(f"/stores/{store_id}/photos/{photo_id}", json={"category": "간판"})

    assert response.status_code == 401


# ---------------------------------------------------------------- 목록 / 삭제


def test_list_photos_returns_full_urls(
    client: TestClient, auth_headers: dict[str, str], store_id: int
) -> None:
    _upload(client, auth_headers, store_id, category="간판")

    photos = client.get(f"/stores/{store_id}/photos", headers=auth_headers).json()["photos"]

    assert len(photos) == 1
    assert photos[0]["file_url"].startswith("http://")


def test_list_photos_filters_by_category(
    client: TestClient, auth_headers: dict[str, str], store_id: int
) -> None:
    _upload(client, auth_headers, store_id, category="간판")
    _upload(client, auth_headers, store_id, category="내부")

    photos = client.get(
        f"/stores/{store_id}/photos", params={"category": "간판"}, headers=auth_headers
    ).json()["photos"]

    assert [p["category"] for p in photos] == ["간판"]


def test_delete_removes_row_and_file(
    client: TestClient, auth_headers: dict[str, str], store_id: int, temp_media_root: Path
) -> None:
    photo_id = _upload(client, auth_headers, store_id).json()["id"]

    response = client.delete(f"/stores/{store_id}/photos/{photo_id}", headers=auth_headers)

    assert response.status_code == 200
    assert response.json() == {"message": "사진이 삭제되었습니다."}
    assert client.get(f"/stores/{store_id}/photos", headers=auth_headers).json()["photos"] == []
    assert list(temp_media_root.rglob("*.png")) == []


def test_photo_of_another_store_is_not_reachable(
    client: TestClient, auth_headers: dict[str, str], store_id: int
) -> None:
    photo_id = _upload(client, auth_headers, store_id).json()["id"]
    other_store_id = client.post(
        "/stores",
        json={"name": "두번째가게", "category": "분식", "address": "서울 마포구 양화로 100"},
        headers=auth_headers,
    ).json()["id"]

    response = client.delete(f"/stores/{other_store_id}/photos/{photo_id}", headers=auth_headers)

    assert response.status_code == 404
    assert response.json()["error_code"] == "PHOTO_NOT_FOUND"


# ---------------------------------------------------------------- 2.3 연동


def test_import_status_photo_becomes_success_after_upload(
    client: TestClient, auth_headers: dict[str, str], store_id: int
) -> None:
    before = {
        i["field"]: i["status"]
        for i in client.get(f"/stores/{store_id}/import-status", headers=auth_headers).json()[
            "items"
        ]
    }
    assert before["사진"] == "PENDING"

    _upload(client, auth_headers, store_id)

    after = {
        i["field"]: i["status"]
        for i in client.get(f"/stores/{store_id}/import-status", headers=auth_headers).json()[
            "items"
        ]
    }
    assert after["사진"] == "SUCCESS"


# ---------------------------------------------------------------- 저장소 계층


def test_absolute_urls_pass_through_unchanged() -> None:
    """외부에서 받아온 URL(로고·메뉴 이미지)에 베이스 주소를 덧붙이면 안 된다."""
    storage = get_storage()

    external = "https://map.naver.com/photo/1.jpg"
    assert to_public_url(storage, external) == external
    assert to_public_url(storage, "stores/1/photos/a.jpg").startswith("http://")
    assert to_public_url(storage, None) is None
    assert to_public_url(storage, "") is None


def test_storage_rejects_key_escaping_root(tmp_path: Path) -> None:
    """키에 상위 경로가 섞여도 저장 루트를 벗어나지 못한다."""
    from app.storage.base import StorageError

    storage = LocalStorage(root=tmp_path, base_url="http://localhost:8000/media")

    with pytest.raises(StorageError):
        storage.save("../escaped.png", io.BytesIO(PNG_BYTES))


def test_storage_delete_is_idempotent(tmp_path: Path) -> None:
    """이미 없는 파일을 지워도 예외가 나면 안 된다 — 삭제 API가 실패해선 안 되므로."""
    storage = LocalStorage(root=tmp_path, base_url="http://localhost:8000/media")

    storage.delete("nothing/here.png")  # 예외 없이 통과해야 한다
    assert storage.exists("nothing/here.png") is False
