"""로컬 디스크 저장소.

배포 전 개발용이다. 저장 루트(`MEDIA_ROOT`)는 `.gitignore`에 있어 커밋되지 않고,
`app/main.py`가 `MEDIA_URL_PATH`로 정적 서빙을 붙인다.
"""

import shutil
from pathlib import Path
from typing import BinaryIO

from app.storage.base import Storage, StorageError


class LocalStorage(Storage):
    def __init__(self, root: Path, base_url: str) -> None:
        self._root = root
        self._base_url = base_url.rstrip("/")

    def _path(self, key: str) -> Path:
        """키를 실제 파일 경로로 바꾼다.

        키에 `..`이나 절대경로가 섞여 들어와 저장 루트 밖을 건드리는 걸 막는다.
        키는 서버가 생성하므로 정상 경로에서는 발생하지 않지만, 저장소는 호출부를
        신뢰하지 않는 편이 안전하다.
        """
        path = (self._root / key).resolve()
        if not path.is_relative_to(self._root.resolve()):
            raise StorageError(f"저장 루트를 벗어나는 키입니다: {key!r}")
        return path

    def save(self, key: str, stream: BinaryIO, content_type: str | None = None) -> str:
        del content_type  # 로컬 디스크는 콘텐츠 타입을 저장하지 않는다(확장자로 판단)
        path = self._path(key)
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("wb") as destination:
            shutil.copyfileobj(stream, destination)
        return key

    def delete(self, key: str) -> None:
        self._path(key).unlink(missing_ok=True)

    def url(self, key: str) -> str:
        return f"{self._base_url}/{key.lstrip('/')}"

    def exists(self, key: str) -> bool:
        return self._path(key).is_file()
