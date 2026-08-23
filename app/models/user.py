"""사용자 모델 (`docs/ERD.sql`의 `users`)."""

from datetime import datetime

from sqlalchemy import Boolean, DateTime, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import Base
from app.models.mixins import TimestampMixin
from app.models.types import BigInt


class User(Base, TimestampMixin):
    """사장님 계정.

    ERD와 다른 점(이유는 `docs/IMPLEMENTATION.md` 결정 로그 참고):
    로그인 식별자로 쓰는 `email`과 표시용 `name`, 그리고 플래그 컬럼들을
    NOT NULL로 두고 `email`에 UNIQUE 제약을 걸었다.
    """

    __tablename__ = "users"

    id: Mapped[int] = mapped_column(
        BigInt, primary_key=True, autoincrement=True, comment="사용자 ID"
    )
    email: Mapped[str] = mapped_column(String(255), unique=True, nullable=False, comment="이메일")
    phone: Mapped[str | None] = mapped_column(String(20), nullable=True, comment="전화번호")
    password_hash: Mapped[str | None] = mapped_column(
        String(255), nullable=True, comment="비밀번호 해시"
    )
    name: Mapped[str] = mapped_column(String(100), nullable=False, comment="이름/닉네임")
    is_active: Mapped[bool] = mapped_column(
        Boolean,
        default=True,
        nullable=False,
        comment="계정 활성화 여부(TRUE=활성, FALSE=탈퇴) - 로그인 가능 여부 판단",
    )
    terms_agreed: Mapped[bool] = mapped_column(
        Boolean, default=False, nullable=False, comment="이용약관/개인정보 필수 동의 여부"
    )
    marketing_agreed: Mapped[bool] = mapped_column(
        Boolean, default=False, nullable=False, comment="마케팅 수신 선택 동의 여부"
    )
    agreed_at: Mapped[datetime | None] = mapped_column(
        DateTime, nullable=True, comment="약관 동의 시각(UTC)"
    )

    def __repr__(self) -> str:
        return f"<User id={self.id} email={self.email!r}>"
