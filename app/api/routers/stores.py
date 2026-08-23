"""가게 API (API명세서 2.1 통합검색 / 2.2 등록 / 2.3 가져오기 진행상태)."""

from decimal import Decimal
from http import HTTPStatus
from typing import Annotated

from fastapi import APIRouter, Query

from app.api.deps import CurrentUser, DbSession
from app.schemas.store import (
    ImportStatusResponse,
    StoreCreateRequest,
    StoreCreateResponse,
    StoreSearchResponse,
)
from app.services import store as store_service
from app.services import store_search

router = APIRouter(prefix="/stores", tags=["stores"])


@router.get("/search", response_model=StoreSearchResponse)
async def search_stores(
    user: CurrentUser,
    keyword: Annotated[str, Query(min_length=1, description="상호명 또는 주소")],
    latitude: Annotated[
        Decimal | None, Query(description="기준 위도. 주면 distance_m이 채워진다")
    ] = None,
    longitude: Annotated[Decimal | None, Query(description="기준 경도")] = None,
) -> StoreSearchResponse:
    """NAVER·Kakao에서 가게 후보를 찾아 중복을 합쳐 돌려준다.

    결과가 없으면 빈 배열이다(에러가 아니다) — 프론트는 이때 직접 입력을 제안한다
    (기능명세서 S02.1.1).
    """
    del user  # 로그인 확인 용도
    results = await store_search.search_stores(keyword, latitude, longitude)
    return StoreSearchResponse(results=results)


@router.post("", response_model=StoreCreateResponse, status_code=HTTPStatus.CREATED)
def create_store(
    payload: StoreCreateRequest, user: CurrentUser, db: DbSession
) -> StoreCreateResponse:
    """가게를 등록한다. 후보확정 / 직접입력 / URL보완 세 경로를 함께 처리한다."""
    store = store_service.create_store(db, user, payload)
    status = store_service.get_import_status(db, store)
    return StoreCreateResponse(
        id=store.id,
        name=store.name,
        category=store.category,
        address=store.address,
        info_source=store.info_source,
        import_status=status.overall_status,
        created_at=store.created_at,
    )


@router.get("/{store_id}/import-status", response_model=ImportStatusResponse)
def get_import_status(store_id: int, user: CurrentUser, db: DbSession) -> ImportStatusResponse:
    """외부데이터 가져오기 진행상태를 항목별로 돌려준다."""
    store = store_service.get_owned_store(db, user, store_id)
    return store_service.get_import_status(db, store)
