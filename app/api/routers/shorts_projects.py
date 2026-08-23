"""숏폼 프로젝트 API (API명세서 4.1 생성·목록 / 4.2 설정수정 / 4.3 단건조회)."""

from http import HTTPStatus
from typing import Annotated

from fastapi import APIRouter, Query

from app.api.deps import CurrentUser, DbSession
from app.models.shorts_project import ShortsStatus
from app.schemas.shorts_project import (
    PlanCreateRequest,
    PlanResponse,
    ProjectCreateRequest,
    ProjectCreateResponse,
    ProjectDetailResponse,
    ProjectListResponse,
    ProjectSettingsResponse,
    ProjectUpdateRequest,
    SceneListResponse,
    ScenePreview,
    SceneResponse,
    SceneUpdateRequest,
    SceneUpdateResponse,
)
from app.services import plan as plan_service
from app.services import shorts_project as project_service

router = APIRouter(prefix="/shorts-projects", tags=["shorts-projects"])


@router.post("", response_model=ProjectCreateResponse, status_code=HTTPStatus.CREATED)
def create_project(
    payload: ProjectCreateRequest, user: CurrentUser, db: DbSession
) -> ProjectCreateResponse:
    """숏폼 프로젝트를 만든다. 홍보 목적만 정하고 나머지 설정은 4.2에서 채운다."""
    project = project_service.create_project(db, user, payload)
    return ProjectCreateResponse.model_validate(project)


@router.get("", response_model=ProjectListResponse)
def list_projects(
    user: CurrentUser,
    db: DbSession,
    store_id: Annotated[int | None, Query(description="특정 가게만 볼 때 지정")] = None,
    status: Annotated[ShortsStatus | None, Query(description="진행 상태 필터")] = None,
) -> ProjectListResponse:
    """이어하기 목록. 최근 수정순으로 돌려준다."""
    projects = project_service.list_projects(db, user, store_id, status)
    return ProjectListResponse(projects=projects)


@router.get("/{project_id}", response_model=ProjectDetailResponse)
def get_project(project_id: int, user: CurrentUser, db: DbSession) -> ProjectDetailResponse:
    project = project_service.get_owned_project(db, user, project_id)
    return ProjectDetailResponse.model_validate(project)


@router.patch("/{project_id}", response_model=ProjectSettingsResponse)
def update_project(
    project_id: int, payload: ProjectUpdateRequest, user: CurrentUser, db: DbSession
) -> ProjectSettingsResponse:
    """프로젝트 설정을 수정한다.

    `promotion_detail`의 허용 구조는 4.1에서 정한 `promotion_purpose`에 따라 다르다.
    목적에 맞지 않는 키를 보내면 400이다.
    """
    project = project_service.get_owned_project(db, user, project_id)
    project = project_service.update_project(db, project, payload)
    return ProjectSettingsResponse.model_validate(project)


# ---------------------------------------------------------------- 7.1 기획 생성


@router.post("/{project_id}/plan", response_model=PlanResponse)
def create_plan(
    project_id: int, payload: PlanCreateRequest, user: CurrentUser, db: DbSession
) -> PlanResponse:
    """선택한 포맷으로 가게 맞춤 대본·콘티를 만든다.

    `video_format_id`는 **이 호출로 프로젝트에 저장된다** — 포맷을 저장하는 유일한
    경로다. 다른 포맷으로 다시 호출하면 **기존 장면은 새 포맷 기준으로 덮어써진다.**
    """
    project = project_service.get_owned_project(db, user, project_id)
    project = plan_service.generate_plan(db, project, payload.video_format_id)

    summary = plan_service.build_summary(project)
    assert summary is not None  # 방금 생성했으므로 항상 있다
    scenes = plan_service.list_scenes(db, project)
    return PlanResponse(
        shooting_summary=summary,
        scenes_preview=[ScenePreview.model_validate(scene) for scene in scenes],
    )


# ---------------------------------------------------------------- 7.2 콘티


@router.get("/{project_id}/scenes", response_model=SceneListResponse)
def list_scenes(project_id: int, user: CurrentUser, db: DbSession) -> SceneListResponse:
    """콘티 전체와 촬영 준비 요약을 돌려준다.

    7.1을 호출한 적 없으면 `shooting_summary`는 `null`, `scenes`는 빈 배열이다.
    """
    project = project_service.get_owned_project(db, user, project_id)
    return SceneListResponse(
        shooting_summary=plan_service.build_summary(project),
        scenes=[
            SceneResponse.model_validate(scene) for scene in plan_service.list_scenes(db, project)
        ],
    )


@router.patch("/{project_id}/scenes", response_model=SceneUpdateResponse)
def update_scenes(
    project_id: int, payload: SceneUpdateRequest, user: CurrentUser, db: DbSession
) -> SceneUpdateResponse:
    """장면 여러 개를 한 번에 수정한다. 대사·자막 수정이 주 용도다."""
    project = project_service.get_owned_project(db, user, project_id)
    updated = plan_service.update_scenes(db, project, payload)
    return SceneUpdateResponse(message="콘티가 수정되었습니다.", updated_count=updated)
