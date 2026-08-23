"""모델 공통 컬럼."""

from datetime import UTC, datetime

from sqlalchemy import DateTime
from sqlalchemy.orm import Mapped, mapped_column


def utcnow() -> datetime:
    """naive UTC 현재시각.

    ERD의 시각 컬럼은 전부 MySQL `DATETIME`(타임존 없음)이라 값 자체에 타임존을
    담을 수 없다. DB 서버 타임존(docker-compose는 Asia/Seoul)에 따라 값이 달라지는
    `NOW()` 대신, 애플리케이션에서 UTC로 계산한 naive datetime을 항상 넣는다.
    응답으로 나갈 때 UTC로 간주해 ISO 8601 `...Z` 형식으로 직렬화한다.
    """
    return datetime.now(UTC).replace(tzinfo=None)


class TimestampMixin:
    """`created_at` / `updated_at`을 갖는 모델용 믹스인."""

    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=utcnow,
        nullable=False,
        comment="생성일시(UTC)",
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=utcnow,
        onupdate=utcnow,
        nullable=False,
        comment="수정일시(UTC)",
    )
