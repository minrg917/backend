"""숏폼 프로젝트 모델 (`docs/ERD.sql`의 `store_shorts_projects`)."""

from enum import StrEnum
from typing import Any

from sqlalchemy import JSON, Enum, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import Base
from app.models.mixins import TimestampMixin
from app.models.types import BigInt


class PromotionPurpose(StrEnum):
    """홍보 목적 (기능명세서 F04.1).

    이 값에 따라 `promotion_detail`의 구조와 `menu_id` 사용 여부가 갈린다
    (API명세서 4.2 「menu_id / promotion_detail 규칙」).
    """

    MENU = "메뉴소개"
    EVENT = "이벤트알리기"
    STORE = "가게소개"
    CUSTOMER = "고객늘리기"


class ShortsStatus(StrEnum):
    DRAFT = "DRAFT"
    IN_PROGRESS = "IN_PROGRESS"
    COMPLETED = "COMPLETED"


class ShortsProject(Base, TimestampMixin):
    """가게의 숏폼 제작 프로젝트.

    작성자는 `store_id → stores.user_id`로 도출한다(ERD 코멘트) — 프로젝트에
    `user_id`를 따로 두지 않는다. 가게 소유자가 곧 프로젝트 소유자다.
    """

    __tablename__ = "store_shorts_projects"

    id: Mapped[int] = mapped_column(
        BigInt, primary_key=True, autoincrement=True, comment="숏폼 프로젝트 ID"
    )
    store_id: Mapped[int] = mapped_column(
        BigInt,
        ForeignKey("stores.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
        comment="가게 ID(작성자는 store_id -> stores.user_id로 도출)",
    )
    video_format_id: Mapped[int | None] = mapped_column(
        BigInt,
        ForeignKey("video_formats.id", ondelete="SET NULL"),
        nullable=True,
        comment="선택한 포맷 ID",
    )
    store_target_customer_id: Mapped[int | None] = mapped_column(
        BigInt,
        ForeignKey("store_target_customers.id", ondelete="SET NULL"),
        nullable=True,
        comment="선택한 타깃 ID",
    )
    menu_id: Mapped[int | None] = mapped_column(
        BigInt,
        ForeignKey("store_menus.id", ondelete="SET NULL"),
        nullable=True,
        comment="홍보 목적이 메뉴소개일 때 선택한 메뉴 ID. 그 외 목적일 땐 NULL",
    )
    # 진입 경로마다 목적을 받는 시점이 달라 NULL을 허용한다 — 홈 피드에서 포맷을 고르는
    # 경로는 목적을 묻지 않고 바로 촬영 준비로 넘어간다(2026-08-23 화면 확인).
    promotion_purpose: Mapped[PromotionPurpose | None] = mapped_column(
        String(50), nullable=True, comment="홍보 목적(메뉴소개/이벤트알리기/가게소개/고객늘리기)"
    )
    promotion_detail: Mapped[dict[str, Any] | None] = mapped_column(
        JSON, nullable=True, comment="홍보 목적별 상세 데이터. promotion_purpose에 따라 구조가 다름"
    )
    face_exposure_mode: Mapped[str | None] = mapped_column(
        String(20), nullable=True, comment="얼굴 노출 모드"
    )
    shooting_condition: Mapped[str | None] = mapped_column(
        Text, nullable=True, comment="촬영 조건(촬영자 유무, 가능 시간 등)"
    )
    shorts_status: Mapped[ShortsStatus] = mapped_column(
        Enum(ShortsStatus, native_enum=False, length=20),
        default=ShortsStatus.DRAFT,
        nullable=False,
        comment="진행 상태(초안/진행중/완료)",
    )

    def __repr__(self) -> str:
        return f"<ShortsProject id={self.id} purpose={self.promotion_purpose!r}>"
