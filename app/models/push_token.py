"""편집 완료 푸시 알림용 디바이스 토큰 모델.

`docs/ERD.sql`엔 아직 없다 — 푸시 알림 자체가 신규 스코프 제안 단계라
(`docs/FE_NOTICE_2026-08-26-02.md` 참고) 기획 최종 확정 전에 백엔드가 먼저
뼈대를 준비해두는 것이다. 스코프가 확정되면 ERD에도 반영한다.

**사용자당 토큰 하나만 유지한다(upsert).** 여러 기기를 동시에 지원하는 대신,
재설치·재로그인으로 토큰이 바뀌면 새 토큰이 이전 값을 덮어쓴다 — 지금은 사장님
한 명이 폰 한 대로 쓰는 시나리오만 다루면 충분하고, 여러 기기를 다 추적하면
"어느 기기로 보내야 하는지" 같은 복잡도만 늘어난다.
"""

from enum import StrEnum

from sqlalchemy import Enum, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import Base
from app.models.mixins import TimestampMixin
from app.models.types import BigInt


class PushPlatform(StrEnum):
    IOS = "IOS"
    ANDROID = "ANDROID"


class PushToken(Base, TimestampMixin):
    __tablename__ = "push_tokens"

    id: Mapped[int] = mapped_column(
        BigInt, primary_key=True, autoincrement=True, comment="푸시 토큰 ID"
    )
    user_id: Mapped[int] = mapped_column(
        BigInt,
        ForeignKey("users.id", ondelete="CASCADE"),
        unique=True,
        nullable=False,
        comment="사용자 ID (사용자당 최신 토큰 하나만 유지)",
    )
    push_token: Mapped[str] = mapped_column(String(255), nullable=False, comment="Expo Push Token")
    platform: Mapped[PushPlatform] = mapped_column(
        Enum(PushPlatform, native_enum=False, length=10),
        nullable=False,
        comment="IOS 또는 ANDROID",
    )

    def __repr__(self) -> str:
        return f"<PushToken user={self.user_id} platform={self.platform}>"
