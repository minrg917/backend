"""숏폼 포맷 모델 (`docs/ERD.sql`의 `video_formats`).

사장님이 따라 만들 **유행하는 숏폼 형식**의 카탈로그다. 사용자가 만드는 데이터가
아니라 서비스가 보유하는 데이터이며, 포맷 발굴과 랭킹은 AI 서버가 담당한다
(`docs/IMPLEMENTATION.md` 2026-08-23 항목).

**원본 영상은 저장하지 않고 링크만 보관한다** — 저작권 때문이며 YouTube 공식
임베드로 노출한다(기능명세서 S07.1.1 "원본 파일을 다운로드·재업로드하지 않는다").
"""

from sqlalchemy import Integer, String
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

    def __repr__(self) -> str:
        return f"<VideoFormat id={self.id} title={self.format_title!r}>"
