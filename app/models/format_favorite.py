"""포맷 찜 모델 (`docs/ERD.sql`의 `format_favorites`).

홈 피드의 하트 버튼과 하단 「찜」 탭에서 쓴다.

**가게가 아니라 사용자(계정) 단위다.** 하단 탭의 찜 목록이 계정 전체에서 하나로
보이고, "이 포맷이 마음에 든다"는 취향은 가게가 아니라 사람에게 속한다.
사장님이 가게를 여러 개 가져도 찜 목록은 하나다.
"""

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import Base
from app.models.mixins import utcnow
from app.models.types import BigInt


class FormatFavorite(Base):
    __tablename__ = "format_favorites"
    __table_args__ = (
        # 같은 사용자가 같은 포맷을 두 번 찜할 수 없다.
        # 하트 연타·네트워크 재시도로 중복 요청이 와도 DB가 마지막 방어선이 된다.
        UniqueConstraint("user_id", "video_format_id", name="uq_format_favorites_user_format"),
    )

    id: Mapped[int] = mapped_column(BigInt, primary_key=True, autoincrement=True, comment="찜 ID")
    user_id: Mapped[int] = mapped_column(
        BigInt,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
        comment="찜한 사용자 ID",
    )
    video_format_id: Mapped[int] = mapped_column(
        BigInt,
        ForeignKey("video_formats.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
        comment="찜한 포맷 ID",
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=utcnow, nullable=False, comment="찜한 일시(UTC)"
    )

    def __repr__(self) -> str:
        return f"<FormatFavorite user={self.user_id} format={self.video_format_id}>"
