"""숏폼 포맷 API (API명세서 5.1 목록 / 5.2 단건 상세)."""

from typing import Annotated

from fastapi import APIRouter, Query

from app.api.deps import CurrentUser, DbSession
from app.schemas.video_format import (
    FormatSort,
    VideoFormatDetailResponse,
    VideoFormatListResponse,
)
from app.services import video_format as format_service

router = APIRouter(prefix="/video-formats", tags=["video-formats"])


@router.get("", response_model=VideoFormatListResponse)
def list_formats(
    user: CurrentUser,
    db: DbSession,
    project_id: Annotated[
        int | None, Query(description="프로젝트 기준 개인화 추천. 없으면 일반 피드")
    ] = None,
    format_type: Annotated[str | None, Query(description="유형(밈/잔잔한 소개)")] = None,
    face_exposure_level: Annotated[str | None, Query(description="얼굴 노출 수준")] = None,
    keyword: Annotated[str | None, Query(description="포맷명 검색")] = None,
    sort: Annotated[FormatSort, Query(description="정렬 기준")] = FormatSort.TRENDING,
    period: Annotated[str | None, Query(description="기간(24h/3d/7d/30d)")] = None,
    page: Annotated[int, Query(ge=1, description="페이지 번호")] = 1,
    size: Annotated[int, Query(ge=1, le=100, description="페이지 크기")] = 20,
) -> VideoFormatListResponse:
    """포맷 목록. 피드·필터·정렬·검색이 한 엔드포인트에 통합돼 있다.

    `sort`·`period`는 계약대로 받지만 **현재는 최신순으로 동작한다** — 인기·급상승
    랭킹은 AI 서버가 포맷 목록과 함께 내려줄 예정이라 아직 우리 DB에 조회수가 없다.
    """
    del user, period  # user는 인증 확인용, period는 랭킹 데이터가 생기면 사용한다
    formats = format_service.list_formats(
        db,
        format_type=format_type,
        face_exposure_level=face_exposure_level,
        keyword=keyword,
        sort=sort,
        page=page,
        size=size,
    )
    return VideoFormatListResponse(
        formats=format_service.build_recommendations(formats, project_id)
    )


@router.get("/{format_id}", response_model=VideoFormatDetailResponse)
def get_format(format_id: int, user: CurrentUser, db: DbSession) -> VideoFormatDetailResponse:
    """포맷 단건 상세. 원본 영상은 `reference_url`로 임베드해 보여준다."""
    del user
    return VideoFormatDetailResponse.model_validate(format_service.get_format(db, format_id))
