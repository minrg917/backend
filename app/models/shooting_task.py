"""촬영 태스크 모델 (`docs/ERD.sql`의 `shooting_tasks`).

콘티(`storyboard_scenes`)를 사장님이 하나씩 수행할 실행 단위로 쪼갠 것이다
(기능명세서 S08.1.1). **7.1 기획 생성이 콘티와 함께 만들며, 재호출하면 함께
덮어써진다** — 옛 포맷의 태스크가 남으면 찍지 않아도 될 컷을 찍게 된다.

ERD에 `created_at`이 없고 `updated_at`만 있다. 보드 정렬은 `display_order`로 한다.
"""

from datetime import datetime
from enum import StrEnum

from sqlalchemy import JSON, DateTime, Enum, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import Base
from app.models.mixins import utcnow
from app.models.types import BigInt


class TaskStatus(StrEnum):
    """진행 상태.

    `progress_rate` 집계에서 `DONE`과 `RETAKE_NEEDED`를 완료로 본다 —
    `RETAKE_NEEDED`는 촬영본 자체는 있고 품질 경고만 붙은 상태다(2026-08-21 확정).
    """

    NOT_STARTED = "NOT_STARTED"
    IN_PROGRESS = "IN_PROGRESS"
    DONE = "DONE"
    RETAKE_NEEDED = "RETAKE_NEEDED"


class FootageType(StrEnum):
    VIDEO = "VIDEO"
    IMAGE = "IMAGE"
    AUDIO = "AUDIO"


# progress_rate·남은 시간 계산에서 "끝난 것"으로 세는 상태
COMPLETED_STATUSES = frozenset({TaskStatus.DONE, TaskStatus.RETAKE_NEEDED})


class ShootingTask(Base):
    __tablename__ = "shooting_tasks"

    id: Mapped[int] = mapped_column(
        BigInt, primary_key=True, autoincrement=True, comment="태스크 ID"
    )
    shorts_project_id: Mapped[int] = mapped_column(
        BigInt,
        ForeignKey("store_shorts_projects.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
        comment="숏폼 프로젝트 ID",
    )
    scene_id: Mapped[int | None] = mapped_column(
        BigInt,
        ForeignKey("storyboard_scenes.id", ondelete="SET NULL"),
        nullable=True,
        comment="연결된 콘티 장면 ID",
    )
    task_type: Mapped[str | None] = mapped_column(
        String(50), nullable=True, comment="태스크 유형(영상촬영/대사/B-roll 등)"
    )
    task_title: Mapped[str | None] = mapped_column(String(200), nullable=True, comment="태스크명")
    task_status: Mapped[TaskStatus] = mapped_column(
        Enum(TaskStatus, native_enum=False, length=20),
        default=TaskStatus.NOT_STARTED,
        nullable=False,
        comment="진행 상태(완료/진행중/미완료/재촬영 필요)",
    )
    display_order: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, comment="태스크 보드 노출 순서"
    )
    footage_url: Mapped[str | None] = mapped_column(
        String(255), nullable=True, comment="촬영본 파일 URL(재촬영 시 덮어씀, 테이크 이력 없음)"
    )
    footage_type: Mapped[FootageType | None] = mapped_column(
        Enum(FootageType, native_enum=False, length=10),
        nullable=True,
        comment="촬영본 파일 유형",
    )
    footage_duration_sec: Mapped[int | None] = mapped_column(
        Integer, nullable=True, comment="촬영본 길이(초)"
    )
    # 촬영 안내. 7.1이 태스크와 함께 저장하고 9.1이 조합해 내려준다.
    # AI 응답 형식이 확정 전이라 컬럼을 쪼개지 않고 JSON으로 둔다.
    # `broll_shot.shot_type`은 여기 넣지 않는다 — `storyboard_scenes.shot_type`에 이미 있다.
    guide: Mapped[dict | None] = mapped_column(
        JSON, nullable=True, comment="촬영 안내(guide_type/instructions/broll_shot)"
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=utcnow,
        onupdate=utcnow,
        nullable=False,
        comment="상태/촬영본 최종 변경일시(UTC)",
    )

    def __repr__(self) -> str:
        return f"<ShootingTask id={self.id} status={self.task_status}>"
