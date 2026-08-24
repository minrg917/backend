"""숏폼 Agent 세션 모델 (`docs/ERD.sql`의 `shortform_sessions`).

ERD 원문에는 없던 테이블 — R06(돋보기 질문형 생성) 재설계로 신설
(2026-08-26, `docs/AI_연동_입출력.md` 5~12번 근거).

AI 서버가 대화 상태(LangGraph Session)를 직접 들고 있고, 우리는 그 세션을
가리키는 토큰과 **최신 응답만** 캐시한다. `project_state`·`last_recommendation`은
AI 응답 형식이 아직 확정 전이라 컬럼으로 쪼개지 않고 JSON으로 그대로 둔다
(`promotion_detail`·`guide`·`props`와 같은 판단).
"""

from enum import StrEnum

from sqlalchemy import JSON, Enum, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import Base
from app.models.mixins import TimestampMixin
from app.models.types import BigInt


class SessionStatus(StrEnum):
    """세션의 BE 쪽 생명주기.

    AI가 돌려주는 `status`(COLLECTING 등)·`stage`와는 다른 축이다 — 저건 AI 대화
    진행 상태이고, 이건 "이 세션으로 아직 프로젝트를 만들 수 있는가"를 나타낸다.
    """

    ACTIVE = "ACTIVE"
    ACCEPTED = "ACCEPTED"
    DISCARDED = "DISCARDED"


class ShortformSession(Base, TimestampMixin):
    __tablename__ = "shortform_sessions"

    id: Mapped[int] = mapped_column(
        BigInt, primary_key=True, autoincrement=True, comment="세션 ID"
    )
    store_id: Mapped[int] = mapped_column(
        BigInt,
        ForeignKey("stores.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
        comment="가게 ID(작성자는 store_id -> stores.user_id로 도출)",
    )
    # AI 서버가 관리하는 LangGraph 세션 식별자. AI 연동 전(placeholder)에는
    # 우리가 UUID로 만들어 채운다. 응답으로 노출하지 않는다 — 프론트는
    # 우리 `id`(BIGINT)만 경로 파라미터로 쓴다.
    session_token: Mapped[str] = mapped_column(
        String(64), unique=True, nullable=False, comment="AI 세션 식별자"
    )
    status: Mapped[SessionStatus] = mapped_column(
        Enum(SessionStatus, native_enum=False, length=20),
        default=SessionStatus.ACTIVE,
        nullable=False,
        comment="세션 생명주기(진행중/수락됨/폐기됨)",
    )
    # AI 응답의 project_state를 그대로 캐시한다(promotion_subject/promotion_objective/
    # filming_time/face_exposure/ready_for_confirmation).
    project_state: Mapped[dict | None] = mapped_column(
        JSON, nullable=True, comment="최신 project_state 캐시(AI 응답 그대로)"
    )
    # 마지막으로 받은 추천. accept() 시 이 값을 그대로 프로젝트에 반영한다 —
    # 프론트가 추천 전체를 다시 보내지 않아도 되게 하기 위함.
    last_recommendation: Mapped[dict | None] = mapped_column(
        JSON, nullable=True, comment="최신 recommendation 캐시(AI 응답 그대로)"
    )
    # AI 서버가 세션 안에서 직접 관리하는 값이라 우리가 제외 로직을 계산하지 않는다
    # (`docs/AI_연동_입출력.md` 10번 "Backend가 거절 이유를 보내지 않는다"). 응답으로
    # 받은 목록을 그대로 쌓아 화면에 "이미 본 후보" 개수 정도를 보여주는 용도로만 쓴다.
    shown_template_ids: Mapped[list[str] | None] = mapped_column(
        JSON, nullable=True, comment="지금까지 보여준 영상편집템플릿 ID 목록(AI 응답 캐시)"
    )

    def __repr__(self) -> str:
        return f"<ShortformSession id={self.id} status={self.status}>"
