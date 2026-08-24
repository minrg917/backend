"""S3 저장소 테스트.

실제 S3를 부르지 않는다 — boto3 클라이언트를 가짜로 주입해 **우리 코드의 판단**
(URL 조립 방식, 예외 감싸기, 없는 파일 처리)만 검증한다. AWS 호출 자체는 boto3의
책임이라 여기서 확인할 게 아니다.
"""

import io
from typing import Any

import pytest

from app.storage import StorageError
from app.storage.s3 import S3Storage


class FakeS3Client:
    def __init__(self, *, fail: bool = False) -> None:
        self.fail = fail
        self.uploaded: list[tuple[str, str, dict[str, Any]]] = []
        self.deleted: list[str] = []
        self.existing: set[str] = set()

    def upload_fileobj(self, stream: Any, bucket: str, key: str, ExtraArgs: dict) -> None:  # noqa: N803
        if self.fail:
            raise RuntimeError("boom")
        self.uploaded.append((bucket, key, ExtraArgs))
        self.existing.add(key)

    def delete_object(self, Bucket: str, Key: str) -> None:  # noqa: N803
        if self.fail:
            raise RuntimeError("boom")
        self.deleted.append(Key)
        self.existing.discard(Key)

    def head_object(self, Bucket: str, Key: str) -> None:  # noqa: N803
        if Key not in self.existing:
            raise RuntimeError("404")

    def generate_presigned_url(self, operation: str, Params: dict, ExpiresIn: int) -> str:  # noqa: N803
        return f"https://signed.example.com/{Params['Key']}?exp={ExpiresIn}"


def _storage(**kwargs: Any) -> tuple[S3Storage, FakeS3Client]:
    client = FakeS3Client(fail=kwargs.pop("fail", False))
    storage = S3Storage(bucket="sarils-media", region="ap-northeast-2", client=client, **kwargs)
    return storage, client


def test_save_passes_content_type() -> None:
    storage, client = _storage()

    storage.save("stores/1/logo/a.png", io.BytesIO(b"x"), "image/png")

    assert client.uploaded == [
        ("sarils-media", "stores/1/logo/a.png", {"ContentType": "image/png"})
    ]


def test_save_without_content_type_sends_no_extra_args() -> None:
    storage, client = _storage()

    storage.save("k", io.BytesIO(b"x"), None)

    assert client.uploaded[0][2] == {}


def test_save_wraps_failure_in_storage_error() -> None:
    """boto3 예외가 그대로 올라가면 호출부가 저장소 종류를 알아야 한다."""
    storage, _ = _storage(fail=True)

    with pytest.raises(StorageError):
        storage.save("k", io.BytesIO(b"x"), None)


def test_delete_of_missing_key_does_not_raise() -> None:
    """인터페이스 규약 — 파일이 없어도 삭제는 성공해야 한다."""
    storage, _ = _storage()

    storage.delete("없는키")


def test_url_uses_bucket_address_by_default() -> None:
    storage, _ = _storage()

    assert storage.url("a/b.png") == "https://sarils-media.s3.ap-northeast-2.amazonaws.com/a/b.png"


def test_url_prefers_public_base_url() -> None:
    """CloudFront를 붙이면 S3 주소가 아니라 그쪽으로 나가야 한다."""
    storage, _ = _storage(public_base_url="https://cdn.sarils.com/")

    assert storage.url("a/b.png") == "https://cdn.sarils.com/a/b.png"


def test_url_signs_when_expiry_configured() -> None:
    """서명 URL을 켜면 공개 주소보다 우선한다 — 버킷을 비공개로 둘 수 있어야 한다."""
    storage, _ = _storage(public_base_url="https://cdn.sarils.com", presign_expire_seconds=3600)

    assert storage.url("a/b.png").startswith("https://signed.example.com/a/b.png")


def test_url_strips_leading_slash() -> None:
    storage, _ = _storage()

    assert "amazonaws.com/a/b.png" in storage.url("/a/b.png")


def test_exists_reflects_upload_and_delete() -> None:
    storage, _ = _storage()

    assert storage.exists("k") is False
    storage.save("k", io.BytesIO(b"x"), None)
    assert storage.exists("k") is True
    storage.delete("k")
    assert storage.exists("k") is False
