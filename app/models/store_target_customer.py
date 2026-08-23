"""타깃고객 모델 (`docs/ERD.sql`의 `store_target_customers`)."""

from enum import StrEnum

from sqlalchemy import Enum, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import Base
from app.models.mixins import TimestampMixin
from app.models.types import BigInt


class TargetStatus(StrEnum):
    """확인 상태.

    `SUGGESTED`/`CONFIRMED`는 API명세서 3.4 예시 기준이고, `HIDDEN`은 기능명세서
    S03.5.2의 "숨김" 요구사항에 대응해 백엔드가 추정으로 넣은 값이다.
    **실제 값 이름은 PM·프론트 확인 대기 중**(`docs/PM_DECISIONS.md` 「확인 대기 중」).
    """

    SUGGESTED = "SUGGESTED"
    CONFIRMED = "CONFIRMED"
    HIDDEN = "HIDDEN"


class StoreTargetCustomer(Base, TimestampMixin):
    """AI가 제안하거나 사장님이 직접 만든 타깃고객."""

    __tablename__ = "store_target_customers"

    id: Mapped[int] = mapped_column(BigInt, primary_key=True, autoincrement=True, comment="타깃 ID")
    store_id: Mapped[int] = mapped_column(
        BigInt,
        ForeignKey("stores.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
        comment="가게 ID",
    )
    target_type: Mapped[str | None] = mapped_column(
        String(20), nullable=True, comment="타깃 유형(주/보조/성장)"
    )
    target_description: Mapped[str | None] = mapped_column(
        Text, nullable=True, comment="타깃 설명(생활맥락/구매동기 등)"
    )
    ai_confidence: Mapped[str | None] = mapped_column(
        String(20), nullable=True, comment="AI 추론 신뢰도"
    )
    status: Mapped[TargetStatus] = mapped_column(
        Enum(TargetStatus, native_enum=False, length=20),
        default=TargetStatus.SUGGESTED,
        nullable=False,
        comment="확인 상태(AI제안/사장님확정/숨김)",
    )

    def __repr__(self) -> str:
        return f"<StoreTargetCustomer id={self.id} type={self.target_type!r}>"
