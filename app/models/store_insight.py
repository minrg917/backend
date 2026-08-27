"""가게 인사이트 모델 (`docs/ERD.sql`의 `store_insights`)."""

from datetime import datetime
from typing import Any

from sqlalchemy import JSON, DateTime, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import Base
from app.models.mixins import utcnow
from app.models.types import BigInt


class StoreInsight(Base):
    """상권분석·카드뉴스·다음숏폼추천 등 가게 단위 분석 결과.

    다른 테이블과 달리 `created_at`/`updated_at` 대신 `generated_at` 하나만 갖는다
    (ERD 기준). 인사이트는 수정되는 게 아니라 갱신 시 새로 생성되며, 이 값이
    데이터 신선도 판단에 쓰인다.
    """

    __tablename__ = "store_insights"

    id: Mapped[int] = mapped_column(
        BigInt, primary_key=True, autoincrement=True, comment="인사이트 ID"
    )
    store_id: Mapped[int] = mapped_column(
        BigInt,
        ForeignKey("stores.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
        comment="가게 ID",
    )
    insight_type: Mapped[str | None] = mapped_column(
        String(30), nullable=True, comment="유형(상권분석/카드뉴스/다음숏폼추천 등)"
    )
    insight_title: Mapped[str | None] = mapped_column(String(200), nullable=True, comment="제목")
    insight_content: Mapped[str | None] = mapped_column(Text, nullable=True, comment="분석 내용")
    insight_source: Mapped[str | None] = mapped_column(
        String(50), nullable=True, comment="근거 출처(외부데이터/AI추론)"
    )
    # 2026-08-27 추가. 상권분석의 나이대·성별 분포처럼 텍스트로 담기 힘든 구조화된
    # 값 전용 — promotion_detail/guide/project_state와 같은 이유로 컬럼을 쪼개지
    # 않는다(인사이트 유형마다 모양이 다르고, AI 응답을 검증 없이 그대로 캐시한다).
    # 텍스트로 표현되는 값(제목·요약)은 그대로 insight_title/insight_content를 쓴다.
    insight_data: Mapped[dict[str, Any] | None] = mapped_column(
        JSON, nullable=True, comment="구조화된 분석 데이터(나이·성별 분포 등, 유형마다 모양 다름)"
    )
    generated_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=utcnow,
        nullable=False,
        index=True,
        comment="생성/갱신일시(UTC, 데이터 신선도 판단에 사용)",
    )

    def __repr__(self) -> str:
        return f"<StoreInsight id={self.id} type={self.insight_type!r}>"
