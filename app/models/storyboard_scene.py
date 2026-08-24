"""콘티 장면 모델 (`docs/ERD.sql`의 `storyboard_scenes`).

7.1(기획 생성)이 AI 결과로 만들고, 7.2에서 사장님이 대사·자막을 고친다.
**7.1을 다시 호출하면 기존 장면을 지우고 새로 넣는다**(2026-08-23 확정) —
포맷을 바꿔 재생성했을 때 옛 장면이 남아 섞이면 안 되기 때문이다.
"""

from sqlalchemy import ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import Base
from app.models.types import BigInt


class StoryboardScene(Base):
    __tablename__ = "storyboard_scenes"

    id: Mapped[int] = mapped_column(BigInt, primary_key=True, autoincrement=True, comment="장면 ID")
    shorts_project_id: Mapped[int] = mapped_column(
        BigInt,
        ForeignKey("store_shorts_projects.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
        comment="숏폼 프로젝트 ID",
    )
    scene_order: Mapped[int] = mapped_column(Integer, nullable=False, comment="장면 순서")
    scene_description: Mapped[str | None] = mapped_column(
        Text, nullable=True, comment="화면/행동/구도 설명"
    )
    scene_dialogue: Mapped[str | None] = mapped_column(Text, nullable=True, comment="대사 텍스트")
    scene_subtitle: Mapped[str | None] = mapped_column(Text, nullable=True, comment="자막 텍스트")
    shot_type: Mapped[str | None] = mapped_column(
        String(50), nullable=True, comment="샷 유형(촬영 가이드 오버레이 선택에 사용)"
    )
    target_duration_sec: Mapped[int | None] = mapped_column(
        Integer, nullable=True, comment="목표 길이(초)"
    )

    def __repr__(self) -> str:
        return f"<StoryboardScene id={self.id} order={self.scene_order}>"
