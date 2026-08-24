"""가게사진 모델 (`docs/ERD.sql`의 `store_photos`)."""

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import Base
from app.models.mixins import utcnow
from app.models.types import BigInt


class StorePhoto(Base):
    """가게 사진.

    `file_url`이라는 이름이지만 **전체 URL이 아니라 저장소 키**를 담는다
    (예: `stores/10/photos/ab12cd34.jpg`). 응답을 만들 때 저장소가 전체 URL로
    바꿔주므로 프론트가 받는 값은 명세서 그대로다.
    전체 URL을 저장하면 S3 전환·도메인 변경 시 기존 행이 전부 깨진 링크가 된다
    (`docs/IMPLEMENTATION.md` 2026-08-23 항목).

    ERD에 `updated_at`이 없어 `TimestampMixin`을 쓰지 않는다 — 사진은 메타데이터만
    바뀌는 경우가 드물고 ERD도 `created_at`만 정의한다.
    """

    __tablename__ = "store_photos"

    id: Mapped[int] = mapped_column(BigInt, primary_key=True, autoincrement=True, comment="사진 ID")
    store_id: Mapped[int] = mapped_column(
        BigInt,
        ForeignKey("stores.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
        comment="가게 ID",
    )
    file_url: Mapped[str] = mapped_column(
        String(255), nullable=False, comment="저장소 키(응답에서 전체 URL로 변환)"
    )
    category: Mapped[str | None] = mapped_column(
        String(20),
        nullable=True,
        comment="사진 분류(간판/외관/내부/메뉴/제조·시술/인물/기타) - AI 자동분류 예정",
    )
    has_sensitive_info: Mapped[bool | None] = mapped_column(
        default=None,
        nullable=True,
        comment=(
            "고객 얼굴 등 민감정보 포함 여부(편집 시 사용 제한 판단). AI 판별 전에는 "
            "null(미확인) — false로 채우면 '민감정보 없음'으로 오인될 수 있다"
            "(AI팀 지침, docs/AI_연동_입출력.md 27번)"
        ),
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=utcnow, nullable=False, comment="등록일시(UTC)"
    )

    def __repr__(self) -> str:
        return f"<StorePhoto id={self.id} category={self.category!r}>"
