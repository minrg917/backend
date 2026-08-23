"""대표메뉴 모델 (`docs/ERD.sql`의 `store_menus`)."""

from sqlalchemy import ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import Base
from app.models.mixins import TimestampMixin
from app.models.types import BigInt


class StoreMenu(Base, TimestampMixin):
    """가게의 대표메뉴.

    `is_*` 플래그는 홍보 소재 선택에 쓰인다 — 신메뉴는 추천 우선순위를 올리고,
    품절 메뉴는 소재에서 제외한다. NULL이면 "모름"인지 "아님"인지 구분할 수 없어
    NOT NULL + 기본값 False로 둔다(`users`의 동의 플래그와 같은 판단).
    """

    __tablename__ = "store_menus"

    id: Mapped[int] = mapped_column(BigInt, primary_key=True, autoincrement=True, comment="메뉴 ID")
    store_id: Mapped[int] = mapped_column(
        BigInt,
        ForeignKey("stores.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
        comment="가게 ID",
    )
    name: Mapped[str] = mapped_column(String(200), nullable=False, comment="메뉴명")
    price: Mapped[int | None] = mapped_column(Integer, nullable=True, comment="가격")
    description: Mapped[str | None] = mapped_column(Text, nullable=True, comment="설명")
    image_url: Mapped[str | None] = mapped_column(
        String(255), nullable=True, comment="메뉴 이미지 URL"
    )
    is_new_menu: Mapped[bool] = mapped_column(
        default=False, nullable=False, comment="신메뉴 여부(추천 우선순위에 사용)"
    )
    is_event_menu: Mapped[bool] = mapped_column(
        default=False, nullable=False, comment="이벤트 메뉴 여부"
    )
    is_sold_out: Mapped[bool] = mapped_column(
        default=False, nullable=False, comment="품절 여부(홍보 소재 제외 판단에 사용)"
    )

    def __repr__(self) -> str:
        return f"<StoreMenu id={self.id} name={self.name!r}>"
