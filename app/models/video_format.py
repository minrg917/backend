"""숏폼 포맷 모델 (`docs/ERD.sql`의 `video_formats`).

사장님이 따라 만들 **유행하는 숏폼 형식**의 카탈로그다. 사용자가 만드는 데이터가
아니라 서비스가 보유하는 데이터이며, 포맷 발굴과 랭킹은 AI 서버가 담당한다
(`docs/IMPLEMENTATION.md` 2026-08-23 항목).

**원본 영상은 저장하지 않고 링크만 보관한다** — 저작권 때문이며 YouTube 공식
임베드로 노출한다(기능명세서 S07.1.1 "원본 파일을 다운로드·재업로드하지 않는다").
"""

from sqlalchemy import Boolean, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import Base
from app.models.mixins import TimestampMixin
from app.models.types import BigInt


class VideoFormat(Base, TimestampMixin):
    __tablename__ = "video_formats"

    id: Mapped[int] = mapped_column(BigInt, primary_key=True, autoincrement=True, comment="포맷 ID")
    format_title: Mapped[str] = mapped_column(String(200), nullable=False, comment="포맷명")
    format_type: Mapped[str | None] = mapped_column(
        String(20), nullable=True, index=True, comment="유형(밈/잔잔한 소개)"
    )
    # 같은 원본을 두 번 담지 않기 위한 기준. AI가 목록을 다시 내려줘도 중복이 쌓이지 않는다.
    reference_url: Mapped[str] = mapped_column(
        String(255),
        unique=True,
        nullable=False,
        comment="원본 참고 URL(원본 파일은 저장하지 않고 링크만 보관)",
    )
    source_platform: Mapped[str | None] = mapped_column(
        String(50), nullable=True, comment="원본 플랫폼(임베드 방식 분기에 사용)"
    )
    expected_duration_sec: Mapped[int | None] = mapped_column(
        Integer, nullable=True, comment="예상 촬영/영상 시간(초)"
    )
    shooting_difficulty: Mapped[str | None] = mapped_column(
        String(20), nullable=True, comment="촬영 난이도"
    )
    face_exposure_level: Mapped[str | None] = mapped_column(
        String(20), nullable=True, index=True, comment="얼굴 노출 요구 수준"
    )
    # 숏폼 Agent(R06)가 추천하는 "영상편집템플릿"과 연결하는 키. ERD 원문에는
    # 없던 컬럼 — 2026-08-26 R06 재설계로 신설(docs/AI_연동_입출력.md 9번).
    # **5.1(피드)과 R06(Agent 추천)은 같은 카탈로그를 쓴다**(2026-08-26 AI팀 확인 —
    # "별도 카탈로그를 두는 게 아니라 플랫폼의 영상편집템플릿 카탈로그가 원본"). 다만
    # 5.1로 들어온 기존 행 중 아직 이 값이 없는 것들이 있을 수 있다(전환기).
    # 두 값이 모두 NULL인 행끼리는 유니크 제약에 걸리지 않는다(MySQL은 NULL을
    # 서로 다른 값으로 취급).
    editing_template_id: Mapped[str | None] = mapped_column(
        String(64), nullable=True, comment="AI 서버의 영상편집템플릿 ID"
    )
    editing_template_version: Mapped[int | None] = mapped_column(
        Integer, nullable=True, comment="영상편집템플릿 버전"
    )
    # R06 추천 대상은 ACTIVE 템플릿으로 한정된다(2026-08-26 AI팀 확인: "추천에는
    # 그중 ACTIVE 상태인 템플릿만 사용하면 됨"). 5.1 목록도 같은 카탈로그이므로
    # 함께 필터링한다(`app/services/video_format.py::list_formats`).
    is_active: Mapped[bool] = mapped_column(
        Boolean,
        default=True,
        nullable=False,
        comment="ACTIVE 여부 - false면 추천·피드 노출 대상 아님",
    )

    __table_args__ = (
        UniqueConstraint(
            "editing_template_id", "editing_template_version", name="uq_video_formats_template"
        ),
    )

    def __repr__(self) -> str:
        return f"<VideoFormat id={self.id} title={self.format_title!r}>"
