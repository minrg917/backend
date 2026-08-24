"""편집 산출물 API (API명세서 14.3 수정 요청).

경로가 `/shorts-projects/...` 아래가 아니라 최상위 `/video-outputs/{outputId}`다
(명세서 기준). 소유권은 산출물 → 프로젝트 → 가게 → 사용자로 거슬러 확인한다.
"""

from fastapi import APIRouter

from app.api.deps import CurrentUser, DbSession
from app.schemas.shorts_project import EditReviseRequest, EditReviseResponse
from app.schemas.sns import PublishRequest, PublishResponse
from app.services import sns as sns_service
from app.services import video_edit as edit_service

router = APIRouter(prefix="/video-outputs", tags=["video-outputs"])


@router.post("/{output_id}/revise", response_model=EditReviseResponse)
def revise_output(
    output_id: int, payload: EditReviseRequest, user: CurrentUser, db: DbSession
) -> EditReviseResponse:
    """편집 수정을 요청한다. 간단버튼과 자연어 요청을 같은 경로로 받는다.

    **기존 산출물을 고치지 않고 새 버전을 만든다** — 이전 버전으로 돌아갈 수 있다.
    """
    output = edit_service.get_owned_output(db, user, output_id)
    revised = edit_service.revise(db, output, payload.request_type, payload.action)
    return EditReviseResponse(
        video_output_id=revised.id,
        render_status=revised.render_status,
        revision_id=edit_service.revision_number(db, revised),
    )


@router.post("/{output_id}/publish", response_model=PublishResponse)
def publish_output(
    output_id: int, payload: PublishRequest, user: CurrentUser, db: DbSession
) -> PublishResponse:
    """게시 기록을 남긴다 (API명세서 16.2).

    **`HANDOFF`는 실제로 플랫폼에 올리지 않는다.** 사장님이 영상을 내려받아 앱에서
    직접 올리고, 서버는 "올렸다"는 사실만 기록한다. 그래서 상태가 항상
    `PENDING_LINK`로 시작하며, 16.3으로 실제 게시물을 연결해야 `LINKED`가 된다.

    이 기록이 필요한 이유는 **성과 조회(17.x)의 출발점**이기 때문이다.

    `DIRECT`(서버가 대신 게시)는 플랫폼 앱 검수를 통과해야 동작하므로 지금은
    400으로 막는다.
    """
    output = sns_service.get_owned_output(db, user, output_id)
    post = sns_service.publish(
        db,
        user,
        output,
        platform=payload.platform,
        publish_mode=payload.publish_mode.value,
        connection_id=payload.sns_connection_id,
        caption=payload.post_caption,
        hashtags=payload.post_hashtags,
    )
    return PublishResponse(
        sns_post_id=post.id,
        post_platform=post.post_platform,
        post_status=post.post_status,
        created_at=post.created_at,
    )
