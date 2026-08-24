"""가게 모델 (`docs/ERD.sql`의 `stores`)."""

from decimal import Decimal

from sqlalchemy import DECIMAL, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import Base
from app.models.mixins import TimestampMixin
from app.models.types import BigInt


class Store(Base, TimestampMixin):
    """사장님이 등록한 가게.

    ERD와 다른 점(이유는 `docs/IMPLEMENTATION.md` 결정 로그 참고):
    소유 관계인 `user_id`에 실제 FK 제약을 걸었고, 목록·소유권 검증에 매번 쓰이므로
    인덱스를 준다. `name`은 가게를 식별하는 최소 정보라 NOT NULL로 둔다.
    """

    __tablename__ = "stores"

    id: Mapped[int] = mapped_column(BigInt, primary_key=True, autoincrement=True, comment="가게 ID")
    user_id: Mapped[int] = mapped_column(
        BigInt,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
        comment="소유 사용자 ID",
    )
    name: Mapped[str] = mapped_column(String(200), nullable=False, comment="상호명")
    category: Mapped[str | None] = mapped_column(String(100), nullable=True, comment="업종")
    sub_category: Mapped[str | None] = mapped_column(
        String(100), nullable=True, comment="세부 업종"
    )
    address: Mapped[str | None] = mapped_column(String(255), nullable=True, comment="주소")
    latitude: Mapped[Decimal | None] = mapped_column(DECIMAL(10, 7), nullable=True, comment="위도")
    longitude: Mapped[Decimal | None] = mapped_column(DECIMAL(10, 7), nullable=True, comment="경도")
    phone: Mapped[str | None] = mapped_column(String(20), nullable=True, comment="전화번호")
    business_hours: Mapped[str | None] = mapped_column(
        String(500), nullable=True, comment="영업시간/휴무일"
    )
    brand_tone: Mapped[str | None] = mapped_column(
        Text, nullable=True, comment="브랜드 분위기/말투"
    )
    brand_color: Mapped[str | None] = mapped_column(
        String(20), nullable=True, comment="브랜드 색상"
    )
    logo_url: Mapped[str | None] = mapped_column(
        String(255), nullable=True, comment="로고 이미지 URL"
    )
    info_source: Mapped[str | None] = mapped_column(
        String(50), nullable=True, comment="이 정보를 가져온 출처(NAVER/KAKAO/MANUAL 등)"
    )
    external_channel_url: Mapped[str | None] = mapped_column(
        String(255), nullable=True, comment="네이버플레이스/배달앱 등 외부 채널 URL"
    )

    def __repr__(self) -> str:
        return f"<Store id={self.id} name={self.name!r}>"
