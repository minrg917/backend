"""숏폼 프로젝트 로직 (API명세서 4.1~4.3)."""

from typing import Any

from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.exceptions import BadRequestError, NotFoundError
from app.models.shorts_project import PromotionPurpose, ShortsProject, ShortsStatus
from app.models.store import Store
from app.models.store_menu import StoreMenu
from app.models.store_target_customer import StoreTargetCustomer
from app.models.user import User
from app.schemas.shorts_project import (
    PROMOTION_DETAIL_SCHEMAS,
    ProjectCreateRequest,
    ProjectUpdateRequest,
)
from app.services.store import get_owned_store


class ProjectNotFound(NotFoundError):
    error_code = "PROJECT_NOT_FOUND"
    message = "숏폼 프로젝트를 찾을 수 없습니다."


class InvalidPromotionDetail(BadRequestError):
    error_code = "INVALID_PROMOTION_DETAIL"
    message = "홍보 목적에 맞지 않는 상세 정보입니다."


class MenuNotAllowed(BadRequestError):
    error_code = "MENU_NOT_ALLOWED"
    message = "메뉴소개 목적일 때만 menu_id를 사용할 수 있습니다."


class InvalidReference(BadRequestError):
    error_code = "INVALID_REFERENCE"
    message = "이 가게에 속하지 않은 항목입니다."


def create_project(db: Session, owner: User, payload: ProjectCreateRequest) -> ShortsProject:
    """프로젝트를 만든다. 홍보 목적만 정하고 나머지 설정은 4.2에서 채운다."""
    store = get_owned_store(db, owner, payload.store_id)
    project = ShortsProject(
        store_id=store.id,
        promotion_purpose=payload.promotion_purpose,
        shorts_status=ShortsStatus.DRAFT,
    )
    db.add(project)
    db.commit()
    db.refresh(project)
    return project


def list_projects(
    db: Session,
    owner: User,
    store_id: int | None = None,
    status: ShortsStatus | None = None,
) -> list[ShortsProject]:
    """이어하기 목록. **최근 수정순**으로 돌려준다.

    `store_id`를 주면 그 가게만, 없으면 사용자가 가진 모든 가게의 프로젝트를 본다.
    어느 쪽이든 남의 가게 프로젝트는 조인 조건에서 걸러진다.
    """
    statement = (
        select(ShortsProject)
        .join(Store, ShortsProject.store_id == Store.id)
        .where(Store.user_id == owner.id)
    )
    if store_id is not None:
        statement = statement.where(ShortsProject.store_id == store_id)
    if status is not None:
        statement = statement.where(ShortsProject.shorts_status == status)
    return list(
        db.scalars(statement.order_by(ShortsProject.updated_at.desc(), ShortsProject.id.desc()))
    )


def get_owned_project(db: Session, owner: User, project_id: int) -> ShortsProject:
    """본인 가게의 프로젝트만 가져온다. 남의 것은 404(존재 자체를 숨긴다)."""
    project = db.get(ShortsProject, project_id)
    if project is None:
        raise ProjectNotFound
    store = db.get(Store, project.store_id)
    if store is None or store.user_id != owner.id:
        raise ProjectNotFound
    return project


def _validate_promotion_detail(purpose: PromotionPurpose, detail: dict[str, Any]) -> dict[str, Any]:
    """저장된 홍보 목적에 맞는 스키마로 상세 정보를 검증한다.

    판별자(`promotion_purpose`)가 요청 Body가 아니라 DB에 있어서 Pydantic의
    discriminated union을 쓸 수 없다. 목적으로 스키마를 골라 직접 검증한다.
    목적에 없는 키가 섞여 있으면 `extra="forbid"`에 걸려 400이 된다.
    """
    schema = PROMOTION_DETAIL_SCHEMAS[purpose]
    try:
        validated = schema.model_validate(detail)
    except ValidationError as exc:
        # 어느 키가 왜 틀렸는지 알려줘야 프론트가 고칠 수 있다
        reasons = "; ".join(
            f"{'.'.join(str(part) for part in error['loc']) or 'promotion_detail'}: {error['msg']}"
            for error in exc.errors()
        )
        raise InvalidPromotionDetail(
            f"홍보 목적이 '{purpose.value}'일 때 허용되지 않는 상세 정보입니다. {reasons}"
        ) from exc
    return validated.model_dump(mode="json")


def _validate_menu(db: Session, project: ShortsProject, menu_id: int) -> None:
    """메뉴가 그 프로젝트의 가게 것인지 확인한다.

    남의 가게 메뉴 ID를 넣어 참조를 만들 수 없게 한다.
    """
    menu = db.get(StoreMenu, menu_id)
    if menu is None or menu.store_id != project.store_id:
        raise InvalidReference("이 가게에 속하지 않은 메뉴입니다.")


def _validate_target(db: Session, project: ShortsProject, target_id: int) -> None:
    target = db.get(StoreTargetCustomer, target_id)
    if target is None or target.store_id != project.store_id:
        raise InvalidReference("이 가게에 속하지 않은 타깃고객입니다.")


def update_project(
    db: Session, project: ShortsProject, payload: ProjectUpdateRequest
) -> ShortsProject:
    """프로젝트 설정을 부분 수정한다 (API명세서 4.2)."""
    changes = payload.model_dump(exclude_unset=True)
    purpose = PromotionPurpose(project.promotion_purpose)

    if "menu_id" in changes and changes["menu_id"] is not None:
        # menu_id는 메뉴소개 전용이다. 다른 목적에 넣으면 의미가 없고,
        # 조용히 무시하면 프론트는 저장된 줄 알게 된다.
        if purpose is not PromotionPurpose.MENU:
            raise MenuNotAllowed(
                f"홍보 목적이 '{purpose.value}'인 프로젝트에는 menu_id를 지정할 수 없습니다."
            )
        _validate_menu(db, project, changes["menu_id"])

    if changes.get("store_target_customer_id") is not None:
        _validate_target(db, project, changes["store_target_customer_id"])

    if changes.get("promotion_detail") is not None:
        changes["promotion_detail"] = _validate_promotion_detail(
            purpose, changes["promotion_detail"]
        )

    for field, value in changes.items():
        setattr(project, field, value)
    db.commit()
    db.refresh(project)
    return project
