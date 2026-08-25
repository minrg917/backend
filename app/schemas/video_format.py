"""숏폼 포맷 스키마 (API명세서 5.1~5.2)."""

from enum import StrEnum

from pydantic import Field

from app.schemas.common import BaseSchema, UtcDatetime


class FormatSort(StrEnum):
    """정렬 기준 (기능명세서 S05.2.1).

    ⚠️ `trending`·`views`는 **아직 최신순으로 동작한다.** 랭킹은 AI 서버가
    포맷 목록과 함께 내려줄 예정이라 우리 DB에 조회수·시계열 데이터가 없다
    (`docs/IMPLEMENTATION.md` 2026-08-23 항목). 계약을 유지해두면 AI 연동 시
    응답 순서만 바뀌고 프론트는 그대로다.
    """

    TRENDING = "trending"
    VIEWS = "views"
    LATEST = "latest"


class VideoFormatSummary(BaseSchema):
    """5.1 목록 항목.

    `reference_url`·`source_platform`은 5.2와 동일한 필드를 목록에도 노출한 것이다
    (2026-08-21 추가). 프론트가 상세를 열지 않고도 YouTube 썸네일을 구성할 수 있다.
    """

    id: int
    format_title: str
    format_type: str | None
    expected_duration_sec: int | None
    shooting_difficulty: str | None
    face_exposure_level: str | None
    reference_url: str
    # 촬영 준비 화면에서 트는 가이드 영상. 홈 피드가 쓰는 대표 영상(`reference_url`)과
    # 다를 수 있다. 트렌드 클러스터에서 온 포맷에만 값이 있다.
    guide_video_url: str | None = None
    source_platform: str | None
    # 로그인 사용자가 이 포맷을 찜했는지. 피드에서 하트 채움 여부를 그리는 데 쓴다.
    is_favorite: bool = False
    # AI 추천 이유. 연동 전이라 항상 빈 배열이다(기능명세서 S05.1.2는 최소 2개 요구).
    recommend_reasons: list[str] = Field(default_factory=list)


class VideoFormatListResponse(BaseSchema):
    formats: list[VideoFormatSummary]


class VideoFormatDetailResponse(BaseSchema):
    id: int
    format_title: str
    format_type: str | None
    reference_url: str
    guide_video_url: str | None = None
    source_platform: str | None
    expected_duration_sec: int | None
    shooting_difficulty: str | None
    face_exposure_level: str | None
    is_favorite: bool = False


class FavoriteResponse(BaseSchema):
    """찜하기 응답 (5.3 POST)."""

    video_format_id: int
    is_favorite: bool
    created_at: UtcDatetime
