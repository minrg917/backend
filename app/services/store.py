"""가게 등록·조회 로직 (API명세서 2.2, 2.3)."""

from sqlalchemy.orm import Session

from app.core.exceptions import NotFoundError
from app.models.store import Store
from app.models.user import User
from app.schemas.store import (
    ImportItemStatus,
    ImportStatusItem,
    ImportStatusResponse,
    StoreCreateRequest,
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

    메뉴·사진·상권분석은 각각 `store_menus`·`store_photos`·`store_insights`가
    생기는 R03에서 실제 존재 여부로 바꾼다. 그 전까지는 수집된 적이 없으므로 PENDING이다.
    """
    del db  # R03에서 메뉴·사진·인사이트 개수를 조회할 때 사용한다

    items = [
        ImportStatusItem(field="기본정보", status=ImportItemStatus.SUCCESS),
        ImportStatusItem(field="메뉴", status=ImportItemStatus.PENDING),
        ImportStatusItem(field="사진", status=ImportItemStatus.PENDING),
        ImportStatusItem(field="상권분석", status=ImportItemStatus.PENDING),
    ]
    return ImportStatusResponse(
        store_id=store.id,
        overall_status=summarize_status([item.status for item in items]),
        items=items,
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
