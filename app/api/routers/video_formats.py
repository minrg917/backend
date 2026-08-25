"""숏폼 포맷 API (API명세서 5.1 목록 / 5.2 단건 상세 / 5.3 찜)."""

from typing import Annotated

from fastapi import APIRouter, Query

from app.api.deps import CurrentUser, DbSession
from app.schemas.common import MessageResponse
from app.schemas.video_format import (
    FavoriteResponse,
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
    requires_face: Annotated[bool | None, Query(description="얼굴 노출 필수 여부")] = None,
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
    del period  # 랭킹 데이터가 생기면 사용한다
    formats = format_service.list_formats(
        db,
        format_type=format_type,
        requires_face=requires_face,
        keyword=keyword,
        sort=sort,
        page=page,
        size=size,
    )
    return VideoFormatListResponse(
        formats=format_service.build_recommendations(db, user, formats, project_id)
    )


# `/favorites`는 `/{format_id}`보다 **먼저** 선언해야 한다.
# 아래에 두면 "favorites"가 format_id로 해석돼 422가 난다(`/stores/search`와 같은 패턴).
@router.get("/favorites", response_model=VideoFormatListResponse)
def list_favorites(
    user: CurrentUser,
    db: DbSession,
    page: Annotated[int, Query(ge=1)] = 1,
    size: Annotated[int, Query(ge=1, le=100)] = 20,
) -> VideoFormatListResponse:
    """찜한 포맷 목록. 최근 찜한 순이며 응답 형태는 5.1과 같다."""
    formats = format_service.list_favorites(db, user, page=page, size=size)
    return VideoFormatListResponse(
        formats=format_service.build_recommendations(db, user, formats, favorites_only=True)
    )


@router.get("/{format_id}", response_model=VideoFormatDetailResponse)
def get_format(format_id: int, user: CurrentUser, db: DbSession) -> VideoFormatDetailResponse:
    """포맷 단건 상세. 원본 영상은 `reference_url`로 임베드해 보여준다."""
    video_format = format_service.get_format(db, format_id)
    return VideoFormatDetailResponse.model_validate(video_format).model_copy(
        update={"is_favorite": format_service.is_favorite(db, user, format_id)}
    )


@router.post("/{format_id}/favorite", response_model=FavoriteResponse)
def add_favorite(format_id: int, user: CurrentUser, db: DbSession) -> FavoriteResponse:
    """포맷을 찜한다. 이미 찜했어도 에러가 아니라 기존 기록을 돌려준다(멱등).

    **첫 호출도 201이 아니라 200이다.** 멱등한 API라 처음인지 아닌지에 따라 상태코드가
    달라지면 프론트가 두 경우를 구분해야 해서, 항상 같은 응답으로 통일했다
    (`docs/API명세서.md` 5.3).
    """
    favorite = format_service.add_favorite(db, user, format_id)
    return FavoriteResponse(
        video_format_id=favorite.video_format_id,
        is_favorite=True,
        created_at=favorite.created_at,
    )


@router.delete("/{format_id}/favorite", response_model=MessageResponse)
def remove_favorite(format_id: int, user: CurrentUser, db: DbSession) -> MessageResponse:
    """찜을 해제한다. 찜하지 않은 포맷이어도 200이다(멱등)."""
    format_service.remove_favorite(db, user, format_id)
    return MessageResponse(message="찜을 해제했습니다.")
