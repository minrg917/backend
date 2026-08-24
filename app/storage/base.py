"""저장소 인터페이스.

**키(key)와 URL을 구분하는 게 이 설계의 핵심이다.**

- *키*: 저장소 안에서의 경로. 예: `stores/10/photos/ab12.jpg`. **DB에는 이것만 저장한다.**
- *URL*: 브라우저가 접근할 수 있는 전체 주소. 응답을 만들 때 키로부터 조립한다.

DB에 전체 URL을 저장하면 저장소를 S3로 옮기거나 도메인이 바뀔 때 기존 행이 전부
깨진 링크가 되어 데이터 마이그레이션이 필요하다. 키만 저장하면 DB는 손대지 않는다.
"""

from abc import ABC, abstractmethod
from typing import BinaryIO


class StorageError(Exception):
    """저장소 조작 실패. 호출부에서 도메인 예외로 감싸 응답한다."""


class Storage(ABC):
    """파일 저장소."""

    @abstractmethod
    def save(self, key: str, stream: BinaryIO, content_type: str | None = None) -> str:
        """스트림을 `key` 위치에 저장하고 키를 돌려준다. 같은 키가 있으면 덮어쓴다."""

    @abstractmethod
    def delete(self, key: str) -> None:
        """파일을 지운다. **이미 없어도 예외를 던지지 않는다** — DB 행은 남았는데
        파일만 사라진 경우에도 삭제 API가 실패하면 안 되기 때문이다."""

    @abstractmethod
    def url(self, key: str) -> str:
        """키를 외부에서 접근 가능한 전체 URL로 바꾼다."""

    @abstractmethod
    def exists(self, key: str) -> bool:
        """파일이 실제로 있는지 확인한다(주로 테스트·점검용)."""


def to_public_url(storage: Storage, value: str | None) -> str | None:
    """저장된 값을 응답용 전체 URL로 바꾼다.

    **이미 절대 URL인 값은 그대로 통과시킨다.** 외부에서 받아온 값(가게 로고,
    메뉴 이미지처럼 NAVER·Kakao가 준 URL)과 우리가 저장한 키가 같은 컬럼에 섞여
    들어올 수 있어, 앞에 무언가를 붙이면 망가진다.
    """
    if not value:
        return None
    if value.startswith(("http://", "https://")):
        return value
    return storage.url(value)
