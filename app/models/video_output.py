"""편집 산출물 모델 (`docs/ERD.sql`의 `video_outputs`).

**수정 요청(14.3)마다 새 행이 쌓인다** — ERD의 `created_at` 코멘트가
"수정 요청마다 새 행이 쌓여 자연스럽게 버전 이력이 됨"이다. 기존 행을 고치지
않으므로 되돌아갈 수 있고, 어떤 편집 명령으로 만들어졌는지도 `edit_recipe`에 남는다.

프로젝트당 여러 행이 존재할 수 있다 — 플랫폼별 산출물과 수정 이력 양쪽 때문이다.
"""

from enum import StrEnum

from sqlalchemy import JSON, Enum, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import Base
from app.models.mixins import TimestampMixin
from app.models.types import BigInt


class RenderStatus(StrEnum):
    PENDING = "PENDING"
    PROCESSING = "PROCESSING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    # 편집 Agent가 현재 촬영본으로는 템플릿 구조를 못 만들 때(`docs/AI_연동_입출력.md`
    # 21번 "Source Gap"). FAILED와 달리 재시도가 아니라 **사용자가 선택**해야 한다
    # (`missing_scene_roles`·`available_options` 참고). 2026-08-26 R14 재설계로 추가.
    SOURCE_GAP = "SOURCE_GAP"


class VideoOutput(Base, TimestampMixin):
    __tablename__ = "video_outputs"

    id: Mapped[int] = mapped_column(
        BigInt, primary_key=True, autoincrement=True, comment="산출물 ID"
    )
    shorts_project_id: Mapped[int] = mapped_column(
        BigInt,
        ForeignKey("store_shorts_projects.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
        comment="숏폼 프로젝트 ID",
    )
    edit_recipe: Mapped[str | None] = mapped_column(
        Text, nullable=True, comment="편집 레시피(JSON) - 이 산출물을 만든 편집 명령"
    )
    video_url: Mapped[str | None] = mapped_column(
        String(255), nullable=True, comment="결과 영상 파일 URL"
    )
    cover_image_url: Mapped[str | None] = mapped_column(
        String(255), nullable=True, comment="커버 이미지 URL"
    )
    target_platform: Mapped[str | None] = mapped_column(
        String(50), nullable=True, comment="대상 플랫폼/출력 규격"
    )
    resolution: Mapped[str | None] = mapped_column(String(20), nullable=True, comment="해상도")
    has_licensed_audio: Mapped[bool | None] = mapped_column(
        nullable=True, comment="상업 안전 음원 포함 여부"
    )
    render_status: Mapped[RenderStatus] = mapped_column(
        Enum(RenderStatus, native_enum=False, length=20),
        default=RenderStatus.PENDING,
        nullable=False,
        comment="상태(대기/처리중/완료/실패/소스부족)",
    )
    # AI 편집 Agent 쪽 실행 식별자(`docs/AI_연동_입출력.md` 16번 run_id). 진행 상태를
    # 폴링할 때 쓴다. ERD 원문에는 없던 컬럼, IMPLEMENTATION.md 2026-08-26 항목 참조.
    ai_run_id: Mapped[str | None] = mapped_column(
        String(64), nullable=True, comment="AI 편집 실행(run) 식별자"
    )
    # SOURCE_GAP 상태일 때만 채워진다(21번). 사장님이 선택할 대안을 보여주는 데 쓴다.
    missing_scene_roles: Mapped[list[str] | None] = mapped_column(
        JSON, nullable=True, comment="부족한 장면 역할 목록(SOURCE_GAP 전용)"
    )
    available_options: Mapped[list[str] | None] = mapped_column(
        JSON, nullable=True, comment="선택 가능한 대응 옵션(SOURCE_GAP 전용)"
    )

    def __repr__(self) -> str:
        return f"<VideoOutput id={self.id} status={self.render_status}>"
