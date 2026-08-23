"""숏폼 프로젝트 스키마 (API명세서 4.1~4.3).

**`promotion_detail`의 구조는 `promotion_purpose`에 따라 4갈래로 갈린다.**
그런데 판별자인 `promotion_purpose`는 보통 4.1(생성) 때 정해지고 4.2 요청에는
들어오지 않는다. 그래서 Pydantic의 discriminated union을 쓸 수 없고, 저장된
프로젝트를 읽어 그 목적에 맞는 스키마로 검증한다(`app/services/shorts_project.py`).
목적과 상세가 한 요청에 함께 오면 **새 목적**을 기준으로 검증한다.

목적별 값 목록은 기획 확정 대기 중이다(`docs/PM_DECISIONS.md` 「확인 대기 중」).
확정되면 **값만 바뀌고 구조는 그대로**이므로, 값 정의를 이 파일 한곳에 모아둔다.
"""

from enum import StrEnum
from typing import Any

from pydantic import ConfigDict, Field

from app.models.shorts_project import PromotionPurpose, ShortsStatus
from app.schemas.common import BaseSchema, UtcDatetime


class MenuDetailTag(StrEnum):
    """메뉴소개 세부 태그."""

    SIGNATURE = "대표메뉴"
    NEW = "신메뉴"
    COMPARE = "비교"
    PROCESS = "제조과정"
    HIDDEN = "숨은메뉴"


class StoreIntroElement(StrEnum):
    """가게소개 요소 (복수 선택)."""

    SPACE = "공간"
    LOCATION = "위치"
    SERVICE = "서비스경험"
    PEOPLE = "사장님/직원"
    VLOG = "하루브이로그"


class CustomerGoal(StrEnum):
    """고객늘리기 목표."""

    NEW = "신규고객"
    RETURN = "재방문"
    TIME_SLOT = "특정시간"
    RESERVATION = "예약공석"
    TRUST = "신뢰형성"


class _DetailBase(BaseSchema):
    """목적별 상세 스키마의 공통 설정.

    `extra="forbid"` — 명세서 4.2가 "목적에 맞지 않는 키를 보내면 400"이라고
    규정한다. 예컨대 가게소개 프로젝트에 `event_name`을 보내면 거부된다.
    """

    model_config = ConfigDict(from_attributes=True, extra="forbid")


class MenuPromotionDetail(_DetailBase):
    detail_tag: MenuDetailTag


class EventPromotionDetail(_DetailBase):
    event_name: str = Field(min_length=1, max_length=200)
    benefit: str | None = Field(default=None, max_length=200)
    period: str | None = Field(default=None, max_length=100)
    condition: str | None = Field(default=None, max_length=200)
    limit: str | None = Field(default=None, max_length=200)
    cta: str | None = Field(default=None, max_length=100)


class StorePromotionDetail(_DetailBase):
    elements: list[StoreIntroElement] = Field(min_length=1)


class CustomerPromotionDetail(_DetailBase):
    goal: CustomerGoal
    # 자유 입력으로 뒀으나 기획 의도가 선택지(enum)일 가능성이 있다
    # (`docs/PM_DECISIONS.md` 「확인 대기 중」). 확정되면 이 필드만 바꾸면 된다.
    success_metric: str | None = Field(default=None, max_length=200)


# 목적 → 상세 스키마. 서비스 계층이 이 표를 보고 검증할 스키마를 고른다.
PROMOTION_DETAIL_SCHEMAS: dict[PromotionPurpose, type[_DetailBase]] = {
    PromotionPurpose.MENU: MenuPromotionDetail,
    PromotionPurpose.EVENT: EventPromotionDetail,
    PromotionPurpose.STORE: StorePromotionDetail,
    PromotionPurpose.CUSTOMER: CustomerPromotionDetail,
}


# ---------------------------------------------------------------- 4.1 생성 / 목록


class ProjectCreateRequest(BaseSchema):
    store_id: int
    # 선택 — 진입 경로마다 목적을 받는 시점이 다르다(2026-08-23).
    # 홈 피드에서 포맷을 고르는 경로는 목적을 묻지 않고 바로 촬영 준비로 넘어간다.
    promotion_purpose: PromotionPurpose | None = None


class ProjectCreateResponse(BaseSchema):
    id: int
    store_id: int
    promotion_purpose: PromotionPurpose | None
    shorts_status: ShortsStatus
    created_at: UtcDatetime


class ProjectSummary(BaseSchema):
    id: int
    promotion_purpose: PromotionPurpose | None
    shorts_status: ShortsStatus
    updated_at: UtcDatetime


class ProjectListResponse(BaseSchema):
    projects: list[ProjectSummary]


# ---------------------------------------------------------------- 4.2 설정 수정


class ProjectUpdateRequest(BaseSchema):
    """프로젝트 설정 부분 수정.

    `promotion_detail`은 여기서 `dict`로만 받고, 실제 구조 검증은 서비스 계층이
    저장된 `promotion_purpose`를 보고 수행한다 — 이 스키마 시점에는 어떤 목적인지
    알 수 없기 때문이다.
    """

    menu_id: int | None = None
    # 목적 없이 만든 프로젝트(홈 피드 경로)에 나중에 목적을 채울 수 있어야 한다
    promotion_purpose: PromotionPurpose | None = None
    promotion_detail: dict[str, Any] | None = None
    store_target_customer_id: int | None = None
    face_exposure_mode: str | None = Field(default=None, max_length=20)
    shooting_condition: str | None = None


class ProjectSettingsResponse(BaseSchema):
    """4.2 응답 — 바꾼 필드만이 아니라 **설정 필드 전체**를 돌려준다.

    3.1/3.2/3.4의 PATCH와 다르다. 명세서 4.2 응답 예시가 요청에 없던
    `promotion_purpose`까지 포함하고 있어 전체 설정을 보여주는 형태다.
    """

    id: int
    menu_id: int | None
    promotion_purpose: PromotionPurpose | None
    promotion_detail: dict[str, Any] | None
    store_target_customer_id: int | None
    face_exposure_mode: str | None
    shooting_condition: str | None
    updated_at: UtcDatetime


# ---------------------------------------------------------------- 4.3 단건 조회


class ProjectDetailResponse(BaseSchema):
    id: int
    store_id: int
    video_format_id: int | None
    store_target_customer_id: int | None
    menu_id: int | None
    promotion_purpose: PromotionPurpose | None
    promotion_detail: dict[str, Any] | None
    face_exposure_mode: str | None
    shooting_condition: str | None
    shorts_status: ShortsStatus
    created_at: UtcDatetime
    updated_at: UtcDatetime
