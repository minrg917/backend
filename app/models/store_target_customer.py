"""타깃고객 모델 (`docs/ERD.sql`의 `store_target_customers`)."""

from enum import StrEnum

from sqlalchemy import Enum, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import Base
from app.models.mixins import TimestampMixin
from app.models.types import BigInt


class TargetStatus(StrEnum):
    """확인 상태 (2026-08-23 FE 확인 완료).

    - `SUGGESTED`: AI가 제안했고 사장님 확인 대기
    - `CONFIRMED`: 사장님이 "맞아요"로 확정
    - `HIDDEN`: 사장님이 숨김 처리 (기능명세서 S03.5.2)

    목록 조회(3.4 GET)는 `HIDDEN`도 **거르지 않고 그대로 내려준다** — 화면에서
    숨길지는 프론트 판단이다(API명세서 3.4 노트).
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
