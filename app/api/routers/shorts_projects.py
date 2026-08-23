"""숏폼 프로젝트 API (API명세서 4.1 생성·목록 / 4.2 설정수정 / 4.3 단건조회)."""

from http import HTTPStatus
from typing import Annotated

from fastapi import APIRouter, Query

from app.api.deps import CurrentUser, DbSession
from app.models.shorts_project import ShortsStatus
from app.schemas.shorts_project import (
    ProjectCreateRequest,
    ProjectCreateResponse,
    ProjectDetailResponse,
    ProjectListResponse,
    ProjectSettingsResponse,
    ProjectUpdateRequest,
)
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
