"""성과분석 API (API명세서 17.1 지표 조회 / 17.2 성과 비교 / 17.4 베스트 영상·추천)."""

from datetime import date
from typing import Annotated

from fastapi import APIRouter, Query

from app.api.deps import CurrentUser, DbSession
from app.schemas.performance import (
    BestPerformingResponse,
    BestPostItem,
    ComparisonItem,
    ComparisonResponse,
    MetricItem,
    MetricListResponse,
    PlatformWeeklyTotal,
    WeeklySummaryResponse,
)
from app.schemas.sns import SnsPostLinkRequest, SnsPostLinkResponse, SnsPostResponse
from app.services import performance as perf_service
from app.services import sns as sns_service
from app.services import store as store_service
from app.services import video_format as format_service

router = APIRouter(prefix="/sns-posts", tags=["sns-posts"])


@router.get("/compare", response_model=ComparisonResponse)
def compare_posts(
    user: CurrentUser,
    db: DbSession,
    store_id: Annotated[int, Query(description="비교할 가게 ID")],
    platform: Annotated[str | None, Query(description="플랫폼(생략하면 전체)")] = None,
    goal: Annotated[str | None, Query(description="홍보 목적(생략하면 전체)")] = None,
) -> ComparisonResponse:
    """같은 조건의 게시물을 비율 지표로 비교한다.

    누적 조회수를 그대로 비교하면 오래된 영상이 항상 이기므로, 절대값이 아니라
    비율로 줄을 세운다. 플랫폼마다 조회수 집계 기준이 달라 섞지 않는 것도 같은
    이유다.

    **경로가 `/{postId}/metrics`보다 먼저 선언돼야 한다** — 뒤에 두면 `compare`가
    `postId`로 해석돼 422가 난다.
    """
    store = store_service.get_owned_store(db, user, store_id)
    rows = perf_service.compare(db, store, platform, goal)
    return ComparisonResponse(
        comparison=[
            ComparisonItem(
                sns_post_id=post.id,
                view_rate=view_rate,
                save_rate=save_rate,
                days_since_posted=days,
                confidence=confidence,
            )
            for post, view_rate, save_rate, days, confidence in rows
        ]
    )


@router.get("/weekly-summary", response_model=WeeklySummaryResponse)
def get_weekly_summary(
    user: CurrentUser,
    db: DbSession,
    store_id: Annotated[int, Query(description="조회할 가게 ID")],
) -> WeeklySummaryResponse:
    """플랫폼별 "이번 주(월~일, KST) 신규 조회수·좋아요 합산"을 돌려준다.

    마이페이지 인사이트의 총합 카드용이다. 영상 개별 지표는 17.1, 여러 영상
    비교는 17.2를 쓰고, 이건 "이번 주에 이 가게 콘텐츠가 전체적으로 얼마나
    반응을 얻었는지" 한눈에 보는 용도다.

    **경로가 `/{postId}`보다 먼저 선언돼야 한다** — `/compare`와 같은 이유로,
    뒤에 두면 `weekly-summary`가 `postId`로 해석돼 422가 난다.
    """
    store = store_service.get_owned_store(db, user, store_id)
    week_start, rows = perf_service.weekly_summary(db, store)
    return WeeklySummaryResponse(
        week_start=week_start,
        platforms=[
            PlatformWeeklyTotal(platform=platform, weekly_views=views, weekly_likes=likes)
            for platform, views, likes in rows
        ],
    )


@router.get("/best-performing", response_model=BestPerformingResponse)
def get_best_performing(
    user: CurrentUser,
    db: DbSession,
    store_id: Annotated[int, Query(description="조회할 가게 ID")],
) -> BestPerformingResponse:
    """가장 반응이 좋았던 영상과, 그걸 근거로 한 다음 포맷 추천을 돌려준다.

    아직 게시물이 없거나 지표가 하나도 수집되지 않았으면 둘 다 `null`이다.

    **경로가 `/{postId}`보다 먼저 선언돼야 한다** — `/compare`·`/weekly-summary`와
    같은 이유로, 뒤에 두면 `best-performing`이 `postId`로 해석돼 422가 난다.
    """
    store = store_service.get_owned_store(db, user, store_id)
    best = perf_service.best_performing_post(db, store)
    if best is None:
        return BestPerformingResponse(best_post=None, recommended_format=None)

    post, views, likes = best
    recommended = perf_service.recommend_next_format(db, store, post)
    recommended_summary = (
        format_service.build_recommendations(db, user, [recommended])[0]
        if recommended is not None
        else None
    )
    return BestPerformingResponse(
        best_post=BestPostItem(
            sns_post_id=post.id,
            platform=post.post_platform,
            views=views,
            likes=likes,
            posted_at=post.posted_at,
        ),
        recommended_format=recommended_summary,
    )


@router.get("/{post_id}/metrics", response_model=MetricListResponse)
def get_metrics(
    post_id: int,
    user: CurrentUser,
    db: DbSession,
    date_from: Annotated[date | None, Query(alias="from", description="수집 시작일")] = None,
    date_to: Annotated[date | None, Query(alias="to", description="수집 종료일(당일 포함)")] = None,
) -> MetricListResponse:
    """게시물의 성과 지표 스냅샷을 시간순으로 돌려준다.

    같은 지표가 여러 번 쌓이므로 추이 그래프를 그릴 수 있다. **플랫폼이 주지 않는
    지표는 행 자체가 없다** — 화면에서는 N/A로 표시한다.
    """
    post = sns_service.get_owned_post(db, user, post_id)
    metrics = perf_service.list_metrics(db, post, date_from, date_to)
    return MetricListResponse(
        sns_post_id=post.id,
        metrics=[MetricItem.model_validate(metric) for metric in metrics],
    )


# ---------------------------------------------------------------- 16.3 게시상태 / 연결확정


@router.get("/{post_id}", response_model=SnsPostResponse)
def get_post(post_id: int, user: CurrentUser, db: DbSession) -> SnsPostResponse:
    """게시물의 연결 상태를 돌려준다.

    `post_status`는 **게시 성공 여부가 아니라 연결 상태**다. 공유 핸드오프 방식이라
    서버는 실제로 올라갔는지 확인할 수 없고, "실제 게시물과 이어졌는지"만 안다.
    """
    post = sns_service.get_owned_post(db, user, post_id)
    return SnsPostResponse.model_validate(post)


@router.patch("/{post_id}", response_model=SnsPostLinkResponse)
def link_post(
    post_id: int, payload: SnsPostLinkRequest, user: CurrentUser, db: DbSession
) -> SnsPostLinkResponse:
    """사장님이 올린 실제 게시물과 연결한다.

    **이 연결이 성과 조회의 열쇠다.** 플랫폼에서 지표를 가져오려면 그쪽 게시물 ID가
    필요한데, 공유 핸드오프에서는 서버가 알 수 없어 사장님이 알려줘야 한다.
    """
    post = sns_service.get_owned_post(db, user, post_id)
    post = sns_service.link_post(db, post, payload.external_post_id, payload.posted_at)
    return SnsPostLinkResponse.model_validate(post)
