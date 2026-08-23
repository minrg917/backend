"""설정에 따라 저장소 구현체를 고른다."""

from functools import lru_cache
from pathlib import Path

from app.core.config import settings
from app.storage.base import Storage
from app.storage.local import LocalStorage


@lru_cache
def get_storage() -> Storage:
    """설정된 저장소를 돌려준다. FastAPI 의존성으로도 쓸 수 있다.

    S3를 붙일 때는 여기에 분기를 하나 추가하면 되고, 라우터·서비스는 바뀌지 않는다.
    """
    if settings.STORAGE_BACKEND == "local":
        return LocalStorage(
            root=Path(settings.MEDIA_ROOT),
            base_url=f"{settings.MEDIA_BASE_URL}{settings.MEDIA_URL_PATH}",
        )
    raise ValueError(
        f"지원하지 않는 STORAGE_BACKEND입니다: {settings.STORAGE_BACKEND!r} (현재는 'local'만 지원)"
    )
