"""설정에 따라 저장소 구현체를 고른다."""

from functools import lru_cache
from pathlib import Path

from app.core.config import settings
from app.storage.base import Storage
from app.storage.local import LocalStorage
from app.storage.s3 import S3Storage


@lru_cache
def get_storage() -> Storage:
    """설정된 저장소를 돌려준다. FastAPI 의존성으로도 쓸 수 있다.

    `STORAGE_BACKEND` 하나로 갈린다. 라우터·서비스는 어느 쪽이든 바뀌지 않는다.
    """
    if settings.STORAGE_BACKEND == "local":
        return LocalStorage(
            root=Path(settings.MEDIA_ROOT),
            base_url=f"{settings.MEDIA_BASE_URL}{settings.MEDIA_URL_PATH}",
        )
    if settings.STORAGE_BACKEND == "s3":
        if not settings.S3_BUCKET:
            raise ValueError("STORAGE_BACKEND=s3 이면 S3_BUCKET을 설정해야 합니다.")
        return S3Storage(
            bucket=settings.S3_BUCKET,
            region=settings.S3_REGION,
            public_base_url=settings.S3_PUBLIC_BASE_URL,
            presign_expire_seconds=settings.S3_PRESIGN_EXPIRE_SECONDS,
        )

    raise ValueError(
        f"지원하지 않는 STORAGE_BACKEND입니다: {settings.STORAGE_BACKEND!r} "
        "(현재는 'local'과 's3'만 지원)"
    )
