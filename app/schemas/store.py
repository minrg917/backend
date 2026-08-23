"""가게 관련 요청/응답 스키마 (API명세서 2.1~2.3)."""

from decimal import Decimal
from enum import StrEnum

from pydantic import Field, model_validator

from app.schemas.common import BaseSchema, UtcDatetime


class SearchSource(StrEnum):
    """검색 결과 출처 (기능명세서 S02.1.1 "검색 결과 출처를 후보에 표시한다")."""

    NAVER = "NAVER"
    KAKAO = "KAKAO"


class ImportItemStatus(StrEnum):
    PENDING = "PENDING"
    IN_PROGRESS = "IN_PROGRESS"
    SUCCESS = "SUCCESS"
    FAILED = "FAILED"


# ---------------------------------------------------------------- 2.1 가게 통합검색


class StoreSearchResult(BaseSchema):
    source: SearchSource
    name: str
    address: str | None = None
    phone: str | None = None
    latitude: Decimal | None = None
    longitude: Decimal | None = None
    category: str | None = None
    # 요청에 기준 좌표(latitude/longitude)가 없으면 계산할 수 없어 null로 나간다.
    # 키를 빼지 않고 null로 두는 건 프론트가 키 존재 여부로 분기하지 않게 하기 위함이다.
    distance_m: int | None = None
    external_channel_url: str | None = None


class StoreSearchResponse(BaseSchema):
    results: list[StoreSearchResult]


# ---------------------------------------------------------------- 2.2 가게 등록


class StoreCreateRequest(BaseSchema):
    name: str = Field(min_length=1, max_length=200)
    category: str = Field(min_length=1, max_length=100)
    address: str | None = Field(default=None, max_length=255)
    phone: str | None = Field(default=None, max_length=20)
    info_source: str | None = Field(default=None, max_length=50)
    external_channel_url: str | None = Field(default=None, max_length=255)
    # 검색(2.1) 결과로 등록할 때 좌표를 그대로 넘길 수 있게 받는다. 상권분석에 필요하다.
    latitude: Decimal | None = None
    longitude: Decimal | None = None

    @model_validator(mode="after")
    def check_address_or_channel(self) -> "StoreCreateRequest":
        """기능명세서 S02.1.3: 필수 항목은 상호명, 업종, 주소 또는 온라인 채널 중 하나."""
        if not self.address and not self.external_channel_url:
            raise ValueError("address 또는 external_channel_url 중 하나는 반드시 필요합니다.")
        return self


class StoreCreateResponse(BaseSchema):
    id: int
    name: str
    category: str | None
    address: str | None
    info_source: str | None
    import_status: ImportItemStatus
    created_at: UtcDatetime


# ---------------------------------------------------------------- 2.3 가져오기 진행상태


class ImportStatusItem(BaseSchema):
    field: str
    status: ImportItemStatus


class ImportStatusResponse(BaseSchema):
    store_id: int
    overall_status: ImportItemStatus
    items: list[ImportStatusItem]
