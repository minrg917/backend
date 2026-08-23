"""촬영 태스크 API (API명세서 8.2 상태 변경).

**경로가 `/shorts-projects/...` 아래가 아니라 최상위 `/tasks/{taskId}`다**
(명세서 기준). 태스크 ID만으로 접근하므로 소유권은 태스크 → 프로젝트 → 가게 →
사용자로 거슬러 확인한다.
"""

from typing import Annotated

from fastapi import APIRouter, Depends, File, Form, UploadFile

from app.api.deps import CurrentUser, DbSession
from app.models.shooting_task import FootageType
from app.schemas.shorts_project import (
    FootageUploadResponse,
    TaskGuideResponse,
    TaskStatusUpdateRequest,
    TaskStatusUpdateResponse,
)
from app.services import footage as footage_service
from app.services import shooting_task as task_service
from app.storage import Storage, get_storage, to_public_url

StorageDep = Annotated[Storage, Depends(get_storage)]

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


@router.get("/{task_id}/guide", response_model=TaskGuideResponse)
def get_guide(task_id: int, user: CurrentUser, db: DbSession) -> TaskGuideResponse:
    """태스크 촬영 가이드를 돌려준다.

    구도 오버레이 / 댄스 임베드 / B-roll 샷리스트가 `guide_type`으로 갈린다.
    값은 태스크의 `guide`(AI 생성), 콘티의 `shot_type`, 포맷의 `reference_url`
    세 곳에서 모은다.
    """
    task = task_service.get_owned_task(db, user, task_id)
    return footage_service.build_guide(db, task)


@router.post("/{task_id}/footage", response_model=FootageUploadResponse)
def upload_footage(
    task_id: int,
    user: CurrentUser,
    db: DbSession,
    storage: StorageDep,
    file: Annotated[UploadFile, File(description="촬영본 파일")],
    footage_type: Annotated[FootageType, Form()] = FootageType.VIDEO,
    footage_duration_sec: Annotated[int | None, Form(ge=0)] = None,
) -> FootageUploadResponse:
    """촬영본을 올린다. 성공하면 태스크가 `DONE`이 된다.

    재촬영은 기존 파일을 덮어쓴다(테이크 이력을 남기지 않는다).
    """
    task = task_service.get_owned_task(db, user, task_id)
    task = footage_service.upload_footage(
        db, storage, task, file, footage_type, footage_duration_sec
    )
    return FootageUploadResponse(
        task_id=task.id,
        file_url=to_public_url(storage, task.footage_url) or "",
        footage_type=task.footage_type,
        footage_duration_sec=task.footage_duration_sec,
        task_status=task.task_status,
    )
