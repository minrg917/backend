"""가게 등록·조회 로직 (API명세서 2.2, 2.3)."""

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.exceptions import NotFoundError
from app.models.store import Store
from app.models.store_insight import StoreInsight
from app.models.store_menu import StoreMenu
from app.models.store_photo import StorePhoto
from app.models.user import User
from app.schemas.store import (
    ImportItemStatus,
    ImportStatusItem,
    ImportStatusResponse,
    StoreCreateRequest,
    StoreUpdateRequest,
)


class StoreNotFound(NotFoundError):
    error_code = "STORE_NOT_FOUND"
    message = "가게 정보를 찾을 수 없습니다."


def create_store(db: Session, owner: User, payload: StoreCreateRequest) -> Store:
    """가게를 등록한다.

    후보확정(2.1 검색 결과 선택) / 직접입력 / URL보완 세 경로가 같은 Body를 쓰며,
    무엇으로 등록했는지는 `info_source`가 구분한다(NAVER/KAKAO/MANUAL 등).
    """
    store = Store(
        user_id=owner.id,
        name=payload.name,
        category=payload.category,
        address=payload.address,
        phone=payload.phone,
        info_source=payload.info_source,
        external_channel_url=payload.external_channel_url,
        latitude=payload.latitude,
        longitude=payload.longitude,
    )
    db.add(store)
    db.commit()
    db.refresh(store)
    return store


def update_store(db: Session, store: Store, payload: StoreUpdateRequest) -> Store:
    """가게 정보를 부분 수정한다 (API명세서 3.1 PATCH).

    요청에 담겨 온 필드만 반영한다. `exclude_unset=True`라서 아예 보내지 않은 필드와
    `null`을 명시적으로 보낸 필드가 구분된다 — 후자는 값을 비우려는 의도로 본다.
    """
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(store, field, value)
    db.commit()
    db.refresh(store)
    return store


def get_owned_store(db: Session, owner: User, store_id: int) -> Store:
    """본인 소유 가게를 가져온다.

    남의 가게를 조회하면 403이 아니라 404로 응답한다 — 403은 "그 ID의 가게가
    존재하긴 한다"는 사실을 알려주는 셈이라, 존재 여부 자체를 숨긴다.
    """
    store = db.get(Store, store_id)
    if store is None or store.user_id != owner.id:
        raise StoreNotFound
    return store


def get_import_status(db: Session, store: Store) -> ImportStatusResponse:
    """외부데이터 가져오기 진행상태를 계산한다 (API명세서 2.3).

    상태를 저장하는 컬럼/테이블을 두지 않고 **실제 데이터가 있는지로 계산한다**
    (결정: `docs/IMPLEMENTATION.md` 2026-08-23). 가게가 등록됐다는 것 자체가
    기본정보 수집 완료를 뜻하므로 기본정보는 항상 SUCCESS다.

    메뉴는 `store_menus`, 사진은 `store_photos`, 상권분석은 `store_insights`
    (유형=상권분석)에 데이터가 있으면 SUCCESS다.
    """
    items = [
        # 가게 레코드가 존재한다는 것 자체가 기본정보 수집 완료를 뜻한다
        ImportStatusItem(field="기본정보", status=ImportItemStatus.SUCCESS),
        ImportStatusItem(field="메뉴", status=_status_of(_has_menu(db, store))),
        ImportStatusItem(field="사진", status=_status_of(_has_photo(db, store))),
        ImportStatusItem(field="상권분석", status=_status_of(_has_market_insight(db, store))),
    ]
    return ImportStatusResponse(
        store_id=store.id,
        overall_status=summarize_status([item.status for item in items]),
        items=items,
    )


MARKET_INSIGHT_TYPE = "상권분석"


def _status_of(exists: bool) -> ImportItemStatus:
    """데이터가 있으면 수집 완료, 없으면 아직 안 된 것으로 본다."""
    return ImportItemStatus.SUCCESS if exists else ImportItemStatus.PENDING


def _has_menu(db: Session, store: Store) -> bool:
    return (
        db.scalar(select(StoreMenu.id).where(StoreMenu.store_id == store.id).limit(1)) is not None
    )


def _has_photo(db: Session, store: Store) -> bool:
    return (
        db.scalar(select(StorePhoto.id).where(StorePhoto.store_id == store.id).limit(1)) is not None
    )


def _has_market_insight(db: Session, store: Store) -> bool:
    return (
        db.scalar(
            select(StoreInsight.id)
            .where(
                StoreInsight.store_id == store.id,
                StoreInsight.insight_type == MARKET_INSIGHT_TYPE,
            )
            .limit(1)
        )
        is not None
    )


def summarize_status(statuses: list[ImportItemStatus]) -> ImportItemStatus:
    """항목별 상태를 전체 상태 하나로 요약한다.

    한 소스가 실패해도 전체를 실패로 보지 않는다(기능명세서 S02.2.3
    "한 소스 실패가 전체 등록을 막지 않는다") — 남은 항목이 진행 중이면 IN_PROGRESS다.
    """
    if all(status is ImportItemStatus.SUCCESS for status in statuses):
        return ImportItemStatus.SUCCESS
    if all(status is ImportItemStatus.FAILED for status in statuses):
        return ImportItemStatus.FAILED
    return ImportItemStatus.IN_PROGRESS
