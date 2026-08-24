"""숏폼 프로젝트 모델 (`docs/ERD.sql`의 `store_shorts_projects`)."""

from datetime import datetime
from enum import StrEnum
from typing import Any

from sqlalchemy import JSON, DateTime, Enum, ForeignKey, Integer, String, Text
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
    # 7.1 AI 기획이 지어주는 제목. 사장님이 입력하는 값이 아니다.
    # 없으면 화면은 promotion_purpose를 라벨로 쓴다 — 목적이 4종뿐이라 영상이
    # 쌓이면 카드가 전부 똑같아 보이는 문제를 이 컬럼이 해결한다.
    # ERD 원문에는 없던 컬럼, IMPLEMENTATION.md 2026-08-24 항목 참조
    project_title: Mapped[str | None] = mapped_column(
        String(200), nullable=True, comment="AI가 지은 프로젝트 제목 - 7.1 결과"
    )
    # R06(숏폼 Agent) 6.4 수락 시 저장. AI 문서(`docs/AI_연동_입출력.md` 11번)가
    # "Backend는 현재 Recommendation에서 recommendation_id를 프로젝트에 저장한다"고
    # 명시한다 — 16번(편집 실행 생성) 요청의 `selected_shortform.recommendation_id`로
    # 다시 필요해질 값이라 지금부터 보관해둔다. 화면에 노출하는 값이 아니다.
    recommendation_id: Mapped[str | None] = mapped_column(
        String(64), nullable=True, comment="R06 수락 시점의 AI 추천 ID(내부용, R14 연동 시 재사용)"
    )
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
    # 7.1 AI 기획 결과의 촬영 준비 요약. AI가 만든 값이라 재계산할 수 없어 저장한다
    # (`#/project/:id/prep` 화면을 다시 열 때 필요).
    # ⚠️ `estimated_shooting_sec`은 **예상 촬영 소요시간**이다. `video_formats`의
    # `expected_duration_sec`(완성 영상 길이)와 이름이 비슷하지만 뜻이 다르다.
    estimated_shooting_sec: Mapped[int | None] = mapped_column(
        Integer, nullable=True, comment="예상 촬영 소요시간(초)"
    )
    required_people: Mapped[int | None] = mapped_column(Integer, nullable=True, comment="필요 인원")
    props: Mapped[list[str] | None] = mapped_column(JSON, nullable=True, comment="필요 소품 목록")
    shooting_difficulty: Mapped[str | None] = mapped_column(
        String(20), nullable=True, comment="촬영 난이도"
    )

    # 9.3 자동저장·이어하기. 앱이 맡겨두는 값이라 서버는 내용을 해석하지 않는다.
    # 15.1 게시자료(캡션·해시태그·post_note). ERD 원문에는 없던 컬럼 —
    # sns_posts.post_caption은 "이미 게시한 글"이라 게시 전 초안을 담을 자리가 없었다.
    # 7.1 AI 기획 결과(estimated_shooting_sec 등)와 같은 방식으로 프로젝트에 붙인다.
    publish_kit: Mapped[dict | None] = mapped_column(
        JSON, nullable=True, comment="게시자료(캡션/해시태그/post_note) - 15.1 AI 생성 결과"
    )
    current_step: Mapped[str | None] = mapped_column(String(30), nullable=True, comment="진행 단계")
    client_state: Mapped[dict | None] = mapped_column(JSON, nullable=True, comment="앱 복원용 상태")
    # `updated_at`은 태스크 상태 변경 등으로도 갱신돼 "마지막 임시저장 시각"과 다르다.
    last_saved_at: Mapped[datetime | None] = mapped_column(
        DateTime, nullable=True, comment="마지막 임시저장 시각(UTC)"
    )

    shorts_status: Mapped[ShortsStatus] = mapped_column(
        Enum(ShortsStatus, native_enum=False, length=20),
        default=ShortsStatus.DRAFT,
        nullable=False,
        comment="진행 상태(초안/진행중/완료)",
    )

    def __repr__(self) -> str:
        return f"<ShortsProject id={self.id} purpose={self.promotion_purpose!r}>"
