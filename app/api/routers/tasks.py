"""촬영 태스크 API (API명세서 8.2 상태 변경).

**경로가 `/shorts-projects/...` 아래가 아니라 최상위 `/tasks/{taskId}`다**
(명세서 기준). 태스크 ID만으로 접근하므로 소유권은 태스크 → 프로젝트 → 가게 →
사용자로 거슬러 확인한다.
"""

from fastapi import APIRouter

from app.api.deps import CurrentUser, DbSession
from app.schemas.shorts_project import TaskStatusUpdateRequest, TaskStatusUpdateResponse
from app.services import shooting_task as task_service

router = APIRouter(prefix="/tasks", tags=["tasks"])


@router.patch("/{task_id}", response_model=TaskStatusUpdateResponse)
def update_task_status(
    task_id: int, payload: TaskStatusUpdateRequest, user: CurrentUser, db: DbSession
) -> TaskStatusUpdateResponse:
    """태스크 진행 상태를 변경한다.

    실제로는 업로드 시작 시 `IN_PROGRESS`를 표시하는 용도로 주로 쓰인다 —
    `DONE`이 되는 정상 경로는 9.2(촬영본 업로드 성공)다(2026-08-21 확정).
    다만 API는 ENUM 값을 그대로 받으며, 편집 시작(14.1)이 `footage_url` 기준으로
    검증하므로 여기서 `DONE`을 막지 않아도 구멍은 없다.
    """
    task = task_service.get_owned_task(db, user, task_id)
    task = task_service.update_status(db, task, payload.task_status)
    return TaskStatusUpdateResponse.model_validate(task)
