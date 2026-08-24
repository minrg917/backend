"""`users` 모델 기본값과 시각 직렬화 테스트."""

from datetime import UTC, datetime

from sqlalchemy.orm import Session

from app.models.mixins import utcnow
from app.models.user import User
from app.schemas.common import BaseSchema, UtcDatetime


class _UserResponse(BaseSchema):
    id: int
    email: str
    created_at: UtcDatetime


def test_user_defaults_are_applied(db_session: Session) -> None:
    user = User(email="boss01@example.com", name="김사장")
    db_session.add(user)
    db_session.commit()

    assert user.id is not None
    assert user.is_active is True
    assert user.terms_agreed is False
    assert user.marketing_agreed is False
    assert user.created_at is not None
    assert user.updated_at is not None


def test_utcnow_is_naive_utc() -> None:
    now = utcnow()

    assert now.tzinfo is None
    # 시스템 로컬시각(KST 등)이 아니라 UTC 기준이어야 한다.
    assert abs((now - datetime.now(UTC).replace(tzinfo=None)).total_seconds()) < 5


def test_datetime_is_serialized_as_iso8601_utc(db_session: Session) -> None:
    user = User(email="boss01@example.com", name="김사장")
    db_session.add(user)
    db_session.commit()

    dumped = _UserResponse.model_validate(user).model_dump()

    # API명세서 포맷: "2026-08-19T08:00:00Z"
    assert dumped["created_at"].endswith("Z")
    assert datetime.strptime(dumped["created_at"], "%Y-%m-%dT%H:%M:%SZ")
