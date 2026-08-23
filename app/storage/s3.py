"""S3 저장소.

`LocalStorage`와 같은 인터페이스라 라우터·서비스는 바뀌지 않는다. DB에는 여전히
**키만** 들어가므로, 로컬에서 S3로 바꿔도 기존 행을 손댈 필요가 없다.

**자격증명은 코드에서 다루지 않는다.** boto3가 표준 순서(환경변수 → 공유 자격증명
파일 → EC2 인스턴스 프로파일)로 알아서 찾는다. 운영에서는 **IAM 역할**을 붙이는 게
안전하다 — 키를 서버에 두지 않아도 되고 유출 시 회수가 쉽다.
"""

from typing import TYPE_CHECKING, BinaryIO

from app.storage.base import Storage, StorageError

if TYPE_CHECKING:  # boto3는 런타임에만 필요하다(로컬 개발·CI에서는 임포트하지 않는다)
    from mypy_boto3_s3.client import S3Client


class S3Storage(Storage):
    def __init__(
        self,
        bucket: str,
        region: str,
        public_base_url: str = "",
        presign_expire_seconds: int = 0,
        client: "S3Client | None" = None,
    ) -> None:
        self._bucket = bucket
        self._region = region
        self._public_base_url = public_base_url.rstrip("/")
        self._presign_expire = presign_expire_seconds
        self._client = client

    @property
    def client(self) -> "S3Client":
        """boto3 클라이언트를 처음 쓸 때 만든다.

        생성자에서 만들지 않는 이유는 `get_storage()`가 앱 기동 시 불릴 수 있어서다 —
        자격증명이 없는 로컬/CI에서 임포트만으로 실패하면 안 된다.
        """
        if self._client is None:
            import boto3

            self._client = boto3.client("s3", region_name=self._region)
        return self._client

    def save(self, key: str, stream: BinaryIO, content_type: str | None = None) -> str:
        extra = {"ContentType": content_type} if content_type else {}
        try:
            self.client.upload_fileobj(stream, self._bucket, key, ExtraArgs=extra)
        except Exception as error:  # boto3 예외 종류가 많아 저장소 예외로 감싼다
            raise StorageError(f"S3 업로드에 실패했습니다: {key!r}") from error
        return key

    def delete(self, key: str) -> None:
        """S3 `delete_object`는 없는 키에도 성공을 돌려준다 — 인터페이스 규약과 맞다."""
        try:
            self.client.delete_object(Bucket=self._bucket, Key=key)
        except Exception as error:
            raise StorageError(f"S3 삭제에 실패했습니다: {key!r}") from error

    def url(self, key: str) -> str:
        """키를 접근 가능한 URL로 바꾼다.

        세 가지 방식이 있고 설정으로 고른다.

        1. `presign_expire_seconds > 0` — **서명 URL.** 지정한 시간 뒤 만료된다.
           버킷을 비공개로 둘 수 있어 안전하지만, 호출할 때마다 URL이 달라져
           캐시·북마크가 안 되고 응답 생성 비용이 조금 늘어난다.
        2. `public_base_url` 지정 — CloudFront나 커스텀 도메인.
        3. 둘 다 없으면 — S3 기본 주소. 버킷이 공개 읽기여야 열린다.
        """
        key = key.lstrip("/")
        if self._presign_expire > 0:
            try:
                return self.client.generate_presigned_url(
                    "get_object",
                    Params={"Bucket": self._bucket, "Key": key},
                    ExpiresIn=self._presign_expire,
                )
            except Exception as error:
                raise StorageError(f"S3 서명 URL 생성에 실패했습니다: {key!r}") from error

        if self._public_base_url:
            return f"{self._public_base_url}/{key}"
        return f"https://{self._bucket}.s3.{self._region}.amazonaws.com/{key}"

    def exists(self, key: str) -> bool:
        try:
            self.client.head_object(Bucket=self._bucket, Key=key)
        except Exception:
            # 없거나(404) 권한이 없거나(403) — 어느 쪽이든 "쓸 수 없다"로 본다
            return False
        return True
