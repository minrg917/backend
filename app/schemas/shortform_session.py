"""숏폼 Agent 세션 스키마 (R06 재설계, 2026-08-26).

`project_state`·`recommendation`은 AI 응답을 그대로 캐시하는 자리라 `promotion_detail`
과 같은 이유로 고정 스키마 대신 `dict[str, Any]`로 둔다 — AI 스펙(`docs/AI_연동_입출력.md`)
이 v0.1이라 필드가 더 늘 수 있고, 우리가 구조를 검증할 필요도 없다(그대로 캐시했다가
그대로 돌려줄 뿐).
"""

from enum import StrEnum
from typing import Any

from app.models.shortform_session import SessionStatus
from app.schemas.common import BaseSchema, UtcDatetime


class TurnInputType(StrEnum):
    TEXT = "TEXT"
    OPTION = "OPTION"
    CONFIRM = "CONFIRM"


class TurnInput(BaseSchema):
    """대화 turn 입력. `type`에 따라 나머지 필드 중 하나만 채운다."""

    type: TurnInputType
    text: str | None = None
    option_id: str | None = None
    value: bool | None = None


class TurnRequest(BaseSchema):
    input: TurnInput


class SessionOptionResponse(BaseSchema):
    id: str
    label: str


class RecommendationResponse(BaseSchema):
    recommendation_id: str
    project_title: str
    title: str
    concept: str
    editing_template_id: str
    editing_template_version: int


class SessionCreateResponse(BaseSchema):
    id: int
    status: SessionStatus
    assistant_message: str | None
    options: list[SessionOptionResponse]
    project_state: dict[str, Any]


class TurnResponse(BaseSchema):
    id: int
    action: str
    assistant_message: str | None
    project_state: dict[str, Any]
    options: list[SessionOptionResponse]
    recommendation: RecommendationResponse | None


class NextRecommendationResponse(BaseSchema):
    id: int
    recommendation: RecommendationResponse
    shown_template_ids: list[str]


class SessionAcceptResponse(BaseSchema):
    """추천 수락 → 프로젝트 생성 (4.1 `ProjectCreateResponse`의 상위집합).

    `project_title`·`video_format_id`가 이미 채워진 채로 만들어지는 것이
    기존 4.1(직접 진입)과의 차이다.
    """

    id: int
    store_id: int
    project_title: str | None
    video_format_id: int
    promotion_purpose: str
    menu_id: int | None
    shorts_status: str
    created_at: UtcDatetime
