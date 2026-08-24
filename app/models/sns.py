"""SNS 연동·게시 모델 (`docs/ERD.sql`의 `sns_connections` / `sns_posts`).

**R16 게시 로직은 아직 없다.** 15.2 `GET /stores/{storeId}/shorts`의 `is_posted`가
`sns_posts` 존재 여부로 계산되기 때문에 테이블만 먼저 만든다. `sns_posts.sns_connection_id`가
`sns_connections`를 참조하므로 두 테이블을 함께 둔다 — 한쪽만 만들면 FK를 걸 수 없다.

R16이 붙기 전까지 두 테이블은 항상 비어 있고, 따라서 `is_posted`는 항상 `false`다.
"""

from datetime import datetime
from decimal import Decimal
from enum import StrEnum

from sqlalchemy import DateTime, Enum, ForeignKey, Numeric, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import Base
from app.models.mixins import utcnow
from app.models.types import BigInt


class PostStatus(StrEnum):
    """게시물 **연결** 상태.

    백엔드는 플랫폼에 실제로 올라갔는지 직접 확인할 수 없다(공유 핸드오프 방식).
    그래서 "게시 성공/실패"가 아니라 "실제 게시물과 연결됐는지"만 표현한다.
    공유 직후에는 항상 `PENDING_LINK`로 생성된다.
    """

    PENDING_LINK = "PENDING_LINK"
    LINKED = "LINKED"


class SnsConnection(Base):
    __tablename__ = "sns_connections"

    id: Mapped[int] = mapped_column(BigInt, primary_key=True, autoincrement=True, comment="연동 ID")
    user_id: Mapped[int] = mapped_column(
        BigInt,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
        comment="사용자 ID",
    )
    sns_platform: Mapped[str | None] = mapped_column(
        String(30), nullable=True, comment="연동 플랫폼(INSTAGRAM/YOUTUBE/NAVER/TIKTOK)"
    )
    sns_account_name: Mapped[str | None] = mapped_column(
        String(100), nullable=True, comment="플랫폼상의 계정명(동일 플랫폼 복수 연동 시 구분용)"
    )
    access_token: Mapped[str | None] = mapped_column(
        String(500), nullable=True, comment="게시물 연결·통계 조회 API 호출용 액세스 토큰"
    )
    refresh_token: Mapped[str | None] = mapped_column(
        String(500), nullable=True, comment="리프레시 토큰"
    )
    token_expires_at: Mapped[datetime | None] = mapped_column(
        DateTime, nullable=True, comment="토큰 만료일시(UTC)"
    )

    def __repr__(self) -> str:
        return f"<SnsConnection id={self.id} platform={self.sns_platform}>"


class SnsPost(Base):
    __tablename__ = "sns_posts"

    id: Mapped[int] = mapped_column(
        BigInt, primary_key=True, autoincrement=True, comment="게시물 ID"
    )
    video_output_id: Mapped[int] = mapped_column(
        BigInt,
        ForeignKey("video_outputs.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
        comment="게시(공유)한 산출물 ID",
    )
    sns_connection_id: Mapped[int | None] = mapped_column(
        BigInt,
        ForeignKey("sns_connections.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
        comment="연결에 사용한 SNS 연동 계정 ID",
    )
    post_platform: Mapped[str | None] = mapped_column(
        String(30), nullable=True, comment="게시 플랫폼"
    )
    external_post_id: Mapped[str | None] = mapped_column(
        String(100),
        nullable=True,
        comment="플랫폼상의 실제 게시물 ID - 연결 확정 시점에 채워짐(성과 API 조회 키)",
    )
    post_caption: Mapped[str | None] = mapped_column(Text, nullable=True, comment="캡션/문구")
    post_hashtags: Mapped[str | None] = mapped_column(
        String(500), nullable=True, comment="해시태그"
    )
    post_status: Mapped[PostStatus] = mapped_column(
        Enum(PostStatus, native_enum=False, length=20),
        default=PostStatus.PENDING_LINK,
        nullable=False,
        comment="상태(연결대기/연결완료)",
    )
    posted_at: Mapped[datetime | None] = mapped_column(
        DateTime, nullable=True, comment="게시일시(연결된 게시물의 실제 게시 시각, UTC)"
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=utcnow, nullable=False, comment="레코드 생성일시(공유 버튼을 누른 시각)"
    )

    def __repr__(self) -> str:
        return f"<SnsPost id={self.id} output={self.video_output_id}>"


class SnsPostMetric(Base):
    """게시물 성과 지표 스냅샷 (`docs/ERD.sql`의 `sns_post_metrics`).

    **한 행이 "어느 게시물의, 어느 지표가, 언제 얼마였는지" 하나를 담는다.**
    지표를 컬럼으로 두지 않고 행으로 쌓는 이유는 두 가지다.

    1. **플랫폼마다 주는 지표가 다르다.** Instagram에는 `saves`가 있고 YouTube에는
       `averageViewPercentage`가 있다. 컬럼으로 두면 대부분이 NULL인 넓은 테이블이 되고,
       플랫폼이 지표를 추가할 때마다 마이그레이션이 필요하다.
    2. **없는 지표는 표시하지 않아야 한다**(기능명세서 S17.2.1). 행이 없으면 없는 것이라
       `0`과 구분된다 — `0`은 "실제로 0"이라는 주장이라 함부로 쓸 수 없다.

    같은 게시물의 같은 지표가 **여러 번 쌓인다**. 주기적으로 스냅샷을 남겨 추이
    그래프를 그리기 위함이다.
    """

    __tablename__ = "sns_post_metrics"

    id: Mapped[int] = mapped_column(BigInt, primary_key=True, autoincrement=True, comment="지표 ID")
    sns_post_id: Mapped[int] = mapped_column(
        BigInt,
        ForeignKey("sns_posts.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
        comment="게시물 ID",
    )
    metric_name: Mapped[str] = mapped_column(
        String(50), nullable=False, comment="지표명(views/likes/comments/shares/saves 등)"
    )
    # 정수 지표(조회수)와 비율 지표(평균 시청률)가 같은 컬럼에 들어와 DECIMAL을 쓴다.
    # float는 반올림 오차가 누적돼 "조회수 15229.999"처럼 보일 수 있다.
    metric_value: Mapped[Decimal | None] = mapped_column(
        Numeric(18, 2), nullable=True, comment="지표 값"
    )
    collected_at: Mapped[datetime] = mapped_column(
        DateTime, default=utcnow, nullable=False, comment="수집 시각(UTC)"
    )

    def __repr__(self) -> str:
        return f"<SnsPostMetric post={self.sns_post_id} {self.metric_name}={self.metric_value}>"
