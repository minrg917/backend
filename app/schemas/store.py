"""가게 관련 요청/응답 스키마 (API명세서 2.1~2.3)."""

from decimal import Decimal
from enum import StrEnum

from pydantic import Field, model_validator

from app.models.store_target_customer import TargetStatus
from app.schemas.common import BaseSchema, Coordinate, UtcDatetime


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
    latitude: Coordinate | None = None
    longitude: Coordinate | None = None
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


# ---------------------------------------------------------------- 3.1 기본정보 + 브랜드톤


class StoreDetailResponse(BaseSchema):
    id: int
    name: str
    category: str | None
    sub_category: str | None
    address: str | None
    latitude: Coordinate | None
    longitude: Coordinate | None
    phone: str | None
    business_hours: str | None
    brand_tone: str | None
    brand_color: str | None
    logo_url: str | None
    info_source: str | None
    external_channel_url: str | None
    updated_at: UtcDatetime


class StoreUpdateRequest(BaseSchema):
    """부분 수정. 보낸 필드만 반영하고 나머지는 건드리지 않는다.

    모든 필드가 선택이라 `model_dump(exclude_unset=True)`로 "보낸 것"만 골라낸다.
    None을 명시적으로 보내면 그 필드를 비우는 것으로 처리된다.
    """

    name: str | None = Field(default=None, min_length=1, max_length=200)
    category: str | None = Field(default=None, max_length=100)
    sub_category: str | None = Field(default=None, max_length=100)
    address: str | None = Field(default=None, max_length=255)
    phone: str | None = Field(default=None, max_length=20)
    business_hours: str | None = Field(default=None, max_length=500)
    brand_tone: str | None = None
    brand_color: str | None = Field(default=None, max_length=20)
    logo_url: str | None = Field(default=None, max_length=255)
    external_channel_url: str | None = Field(default=None, max_length=255)
    latitude: Decimal | None = None
    longitude: Decimal | None = None


class StoreUpdateResponse(BaseSchema):
    """명세서 3.1 PATCH 응답 — 바꾼 필드만 담아 내보낸다.

    `id`/`updated_at` 외의 필드는 요청에 담겨 있던 것만 응답에 포함된다.
    라우터에서 `exclude_unset=True`로 직렬화하므로 나머지 키는 아예 나가지 않는다.
    """

    id: int
    name: str | None = None
    category: str | None = None
    sub_category: str | None = None
    address: str | None = None
    phone: str | None = None
    business_hours: str | None = None
    brand_tone: str | None = None
    brand_color: str | None = None
    logo_url: str | None = None
    external_channel_url: str | None = None
    latitude: Coordinate | None = None
    longitude: Coordinate | None = None
    updated_at: UtcDatetime


# ---------------------------------------------------------------- 3.2 대표메뉴


class MenuResponse(BaseSchema):
    id: int
    name: str
    price: int | None
    description: str | None
    image_url: str | None
    is_new_menu: bool
    is_event_menu: bool
    is_sold_out: bool


class MenuListResponse(BaseSchema):
    menus: list[MenuResponse]


class MenuCreateRequest(BaseSchema):
    name: str = Field(min_length=1, max_length=200)
    price: int | None = Field(default=None, ge=0)
    description: str | None = None
    image_url: str | None = Field(default=None, max_length=255)
    is_new_menu: bool = False
    is_event_menu: bool = False
    is_sold_out: bool = False


class MenuCreateResponse(BaseSchema):
    id: int
    name: str
    price: int | None
    is_new_menu: bool
    created_at: UtcDatetime


class MenuUpdateRequest(BaseSchema):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    price: int | None = Field(default=None, ge=0)
    description: str | None = None
    image_url: str | None = Field(default=None, max_length=255)
    is_new_menu: bool | None = None
    is_event_menu: bool | None = None
    is_sold_out: bool | None = None


class MenuUpdateResponse(BaseSchema):
    """3.2 PATCH 응답 — 바꾼 필드만 (`exclude_unset`)."""

    id: int
    name: str | None = None
    price: int | None = None
    description: str | None = None
    image_url: str | None = None
    is_new_menu: bool | None = None
    is_event_menu: bool | None = None
    is_sold_out: bool | None = None
    updated_at: UtcDatetime


# ---------------------------------------------------------------- 3.4 타깃고객


class TargetCustomerResponse(BaseSchema):
    id: int
    target_type: str | None
    target_description: str | None
    ai_confidence: str | None
    status: TargetStatus


class TargetCustomerListResponse(BaseSchema):
    target_customers: list[TargetCustomerResponse]


class TargetCustomerCreateRequest(BaseSchema):
    target_type: str = Field(min_length=1, max_length=20)
    target_description: str = Field(min_length=1)


class TargetCustomerCreateResponse(BaseSchema):
    id: int
    target_type: str | None
    target_description: str | None
    created_at: UtcDatetime


class TargetCustomerUpdateRequest(BaseSchema):
    target_type: str | None = Field(default=None, min_length=1, max_length=20)
    target_description: str | None = Field(default=None, min_length=1)
    status: TargetStatus | None = None


class TargetCustomerUpdateResponse(BaseSchema):
    """3.4 PATCH 응답 — 바꾼 필드만 (`exclude_unset`)."""

    id: int
    target_type: str | None = None
    target_description: str | None = None
    status: TargetStatus | None = None
    updated_at: UtcDatetime


# ---------------------------------------------------------------- 3.5 인사이트


class InsightResponse(BaseSchema):
    id: int
    insight_type: str | None
    insight_title: str | None
    insight_content: str | None
    insight_source: str | None
    generated_at: UtcDatetime


class InsightListResponse(BaseSchema):
    insights: list[InsightResponse]


# ---------------------------------------------------------------- 3.3 가게사진


class PhotoCategory(StrEnum):
    """사진 분류 (기능명세서 S03.2.1).

    AI 자동분류가 붙기 전까지는 업로드 시 프론트가 지정하며, 지정하지 않으면 `기타`다.
    """

    SIGNBOARD = "간판"
    EXTERIOR = "외관"
    INTERIOR = "내부"
    MENU = "메뉴"
    PROCESS = "제조·시술"
    PERSON = "인물"
    ETC = "기타"


class PhotoResponse(BaseSchema):
    id: int
    file_url: str
    category: str | None
    has_sensitive_info: bool | None
    created_at: UtcDatetime


class PhotoListResponse(BaseSchema):
    photos: list[PhotoResponse]


class PhotoUpdateRequest(BaseSchema):
    """사진 분류를 사장님이 직접 고친다 (기능명세서 S03.2.1 "분류를 수정할 수 있다").

    `category`만 받는다 — `has_sensitive_info`는 AI 판별 몫이라 사람이 끄고 켜면
    오판 위험이 더 커진다(2026-08-26 결정, `docs/PM_DECISIONS.md`).
    """

    category: PhotoCategory


class PhotoUpdateResponse(BaseSchema):
    id: int
    category: str


# ---------------------------------------------------------------- 3.6 가게 로고


class LogoUploadResponse(BaseSchema):
    store_id: int
    logo_url: str
    updated_at: UtcDatetime


# ---------------------------------------------------------------- 15.2 완성 숏폼 목록


class StoreShortItem(BaseSchema):
    video_output_id: int
    shorts_project_id: int
    # 7.1 AI 기획이 지어준 제목. 없으면 화면은 promotion_purpose를 라벨로 쓴다.
    project_title: str | None
    promotion_purpose: str | None
    video_url: str | None
    cover_image_url: str | None
    # 포맷의 완성 영상 길이에서 온다 — video_outputs에는 길이 컬럼이 없다
    duration_sec: int | None
    is_posted: bool
    created_at: UtcDatetime


class StoreShortListResponse(BaseSchema):
    items: list[StoreShortItem]
    page: int
    size: int
    total: int
