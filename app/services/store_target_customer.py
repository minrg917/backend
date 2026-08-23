"""타깃고객 로직 (API명세서 3.4)."""

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.exceptions import NotFoundError
from app.models.store import Store
from app.models.store_target_customer import StoreTargetCustomer, TargetStatus
from app.schemas.store import TargetCustomerCreateRequest, TargetCustomerUpdateRequest


class TargetCustomerNotFound(NotFoundError):
    error_code = "TARGET_CUSTOMER_NOT_FOUND"
    message = "타깃고객 정보를 찾을 수 없습니다."


def list_target_customers(db: Session, store: Store) -> list[StoreTargetCustomer]:
    return list(
        db.scalars(
            select(StoreTargetCustomer)
            .where(StoreTargetCustomer.store_id == store.id)
            .order_by(StoreTargetCustomer.id)
        )
    )


def create_target_customer(
    db: Session, store: Store, payload: TargetCustomerCreateRequest
) -> StoreTargetCustomer:
    """사장님이 직접 타깃을 추가한다.

    `status`는 `CONFIRMED`로 둔다 — `SUGGESTED`는 "AI가 제안했고 사장님 확인 대기"라는
    뜻인데, 사장님이 직접 적어 넣은 타깃은 이미 확정된 것이라 다시 확인받을 게 없다.
    `ai_confidence`는 AI 추론값이므로 직접 입력 경로에서는 NULL로 남긴다.
    (`docs/IMPLEMENTATION.md` 2026-08-23 항목)
    """
    target = StoreTargetCustomer(
        store_id=store.id,
        target_type=payload.target_type,
        target_description=payload.target_description,
        ai_confidence=None,
        status=TargetStatus.CONFIRMED,
    )
    db.add(target)
    db.commit()
    db.refresh(target)
    return target


def get_target_customer(db: Session, store: Store, target_id: int) -> StoreTargetCustomer:
    target = db.get(StoreTargetCustomer, target_id)
    if target is None or target.store_id != store.id:
        raise TargetCustomerNotFound
    return target


def update_target_customer(
    db: Session, target: StoreTargetCustomer, payload: TargetCustomerUpdateRequest
) -> StoreTargetCustomer:
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(target, field, value)
    db.commit()
    db.refresh(target)
    return target
