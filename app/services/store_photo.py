"""가게사진 업로드·조회·삭제 로직 (API명세서 3.3)."""

import os
import uuid
from http import HTTPStatus

from fastapi import UploadFile
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.exceptions import AppError, NotFoundError
from app.models.store import Store
from app.models.store_photo import StorePhoto
from app.schemas.store import PhotoCategory
from app.storage import Storage

# content_type → 저장할 확장자. 원본 파일명을 믿지 않고 여기서 결정한다.
_EXTENSIONS = {
    "image/jpeg": ".jpg",
    "image/png": ".png",
    "image/webp": ".webp",
    "image/heic": ".heic",
}


class PhotoNotFound(NotFoundError):
    error_code = "PHOTO_NOT_FOUND"
    message = "사진을 찾을 수 없습니다."


class UnsupportedFileType(AppError):
    """사진(3.3)과 촬영본(9.2)이 함께 쓴다 — 기본 문구는 중립적으로 두고
    호출부가 상황에 맞는 안내를 넘긴다."""

    status_code = HTTPStatus.UNSUPPORTED_MEDIA_TYPE
    error_code = "UNSUPPORTED_FILE_TYPE"
    message = "지원하지 않는 파일 형식입니다."


class FileTooLarge(AppError):
    status_code = HTTPStatus.REQUEST_ENTITY_TOO_LARGE
    error_code = "FILE_TOO_LARGE"
    message = "파일 크기가 너무 큽니다."


class EmptyFile(AppError):
    status_code = HTTPStatus.BAD_REQUEST
    error_code = "EMPTY_FILE"
    message = "빈 파일은 업로드할 수 없습니다."


def list_photos(db: Session, store: Store, category: str | None = None) -> list[StorePhoto]:
    statement = select(StorePhoto).where(StorePhoto.store_id == store.id)
    if category:
        statement = statement.where(StorePhoto.category == category)
    return list(db.scalars(statement.order_by(StorePhoto.id)))


def validate_upload(
    upload: UploadFile,
    allowed_types: set[str],
    extensions: dict[str, str],
    max_bytes: int,
    limit_mb: int,
    unsupported_message: str,
) -> str:
    """업로드 파일을 검사하고 저장할 확장자를 돌려준다.

    사진(3.3)과 촬영본(9.2)이 같은 규칙을 다른 설정으로 쓴다 — 허용 형식과 크기
    제한만 다르고 검사 방식은 동일하다.

    콘텐츠 타입은 클라이언트가 보낸 값이라 완전히 믿을 수는 없지만, 확장자를 원본
    파일명에서 가져오는 것보다는 낫다(경로 조작·한글 파일명·이중 확장자 회피).
    """
    content_type = (upload.content_type or "").lower()
    if content_type not in allowed_types or content_type not in extensions:
        raise UnsupportedFileType(unsupported_message)

    # SpooledTemporaryFile이라 seek이 가능하다 — 전체를 메모리에 읽지 않고 크기를 잰다
    upload.file.seek(0, os.SEEK_END)
    size = upload.file.tell()
    upload.file.seek(0)

    if size == 0:
        raise EmptyFile
    if size > max_bytes:
        raise FileTooLarge(f"파일 크기가 너무 큽니다. 최대 {limit_mb}MB까지 업로드할 수 있습니다.")
    return extensions[content_type]


def _validate(upload: UploadFile) -> str:
    """가게 사진 업로드 검사."""
    return validate_upload(
        upload,
        allowed_types=settings.allowed_image_type_set,
        extensions=_EXTENSIONS,
        max_bytes=settings.max_upload_size_bytes,
        limit_mb=settings.MAX_UPLOAD_SIZE_MB,
        unsupported_message="지원하지 않는 파일 형식입니다. 이미지 파일만 업로드할 수 있습니다.",
    )


def create_photo(
    db: Session,
    storage: Storage,
    store: Store,
    upload: UploadFile,
    category: PhotoCategory | None = None,
) -> StorePhoto:
    """사진을 저장소에 올리고 DB에 기록한다.

    파일명은 서버가 UUID로 만든다 — 원본 파일명을 경로에 쓰면 중복·한글 인코딩·
    경로 조작 문제가 생긴다. DB에는 전체 URL이 아니라 **저장소 키**를 넣는다.
    """
    extension = _validate(upload)
    key = f"stores/{store.id}/photos/{uuid.uuid4().hex}{extension}"
    storage.save(key, upload.file, upload.content_type)

    photo = StorePhoto(
        store_id=store.id,
        file_url=key,
        # AI 자동분류(S03.2.1)가 붙기 전까지는 프론트가 지정하고, 없으면 기타로 둔다
        category=(category or PhotoCategory.ETC).value,
        has_sensitive_info=False,
    )
    db.add(photo)
    db.commit()
    db.refresh(photo)
    return photo


def get_photo(db: Session, store: Store, photo_id: int) -> StorePhoto:
    photo = db.get(StorePhoto, photo_id)
    if photo is None or photo.store_id != store.id:
        raise PhotoNotFound
    return photo


def delete_photo(db: Session, storage: Storage, photo: StorePhoto) -> None:
    """DB 행과 실제 파일을 함께 지운다.

    DB를 먼저 지운다 — 파일 삭제가 실패해도 사용자에겐 사라진 것으로 보여야 하고,
    남은 파일은 어디서도 참조되지 않는 고아 파일이라 나중에 정리할 수 있다.
    반대 순서였다면 DB 삭제 실패 시 깨진 링크가 남는다.
    """
    key = photo.file_url
    db.delete(photo)
    db.commit()
    storage.delete(key)
