"""파일 저장소 계층.

라우터·서비스는 `Storage` 인터페이스만 보고, 실제로 어디에 저장되는지는 모른다.
지금은 로컬 디스크(`LocalStorage`)를 쓰고, 배포 시 S3 구현을 추가해
`STORAGE_BACKEND` 설정만 바꾸면 전환된다.
"""

from app.storage.base import Storage, StorageError, to_public_url
from app.storage.factory import get_storage
from app.storage.local import LocalStorage

__all__ = ["LocalStorage", "Storage", "StorageError", "get_storage", "to_public_url"]
