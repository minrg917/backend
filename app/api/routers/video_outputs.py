"""편집 산출물 API (API명세서 14.3 수정 요청).

경로가 `/shorts-projects/...` 아래가 아니라 최상위 `/video-outputs/{outputId}`다
(명세서 기준). 소유권은 산출물 → 프로젝트 → 가게 → 사용자로 거슬러 확인한다.
"""

from fastapi import APIRouter

from app.api.deps import CurrentUser, DbSession
from app.schemas.shorts_project import EditReviseRequest, EditReviseResponse
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
