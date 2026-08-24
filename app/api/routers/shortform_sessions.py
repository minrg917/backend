"""숏폼 Agent 세션 API (R06 재설계, 2026-08-26).

세션 생성(`POST /stores/{storeId}/shortform-sessions`)만 가게 하위 경로이고,
이후 조작은 전부 세션 ID만으로 접근한다 — `/tasks/{taskId}`와 같은 방식이다.
"""

from http import HTTPStatus

from fastapi import APIRouter

from app.api.deps import CurrentUser, DbSession
from app.schemas.common import MessageResponse
from app.schemas.shortform_session import (
    NextRecommendationResponse,
    RecommendationResponse,
    SessionAcceptResponse,
    SessionOptionResponse,
    TurnRequest,
    TurnResponse,
)
from app.services import shortform_session as session_service

router = APIRouter(prefix="/shortform-sessions", tags=["shortform-sessions"])


@router.post("/{session_id}/turns", response_model=TurnResponse)
def submit_turn(
    session_id: int, payload: TurnRequest, user: CurrentUser, db: DbSession
) -> TurnResponse:
    """대화 turn 하나를 보낸다(텍스트/선택지/확인)."""
    session = session_service.get_owned_session(db, user, session_id)
    result = session_service.submit_turn(db, session, payload.input)
    return TurnResponse(
        id=session.id,
        action=result.action,
        assistant_message=result.assistant_message,
        project_state=result.project_state,
        options=[SessionOptionResponse(id=o.id, label=o.label) for o in result.options],
        recommendation=(
            RecommendationResponse(
                recommendation_id=result.recommendation.recommendation_id,
                project_title=result.recommendation.project_title,
                title=result.recommendation.title,
                concept=result.recommendation.concept,
                editing_template_id=result.recommendation.editing_template_id,
                editing_template_version=result.recommendation.editing_template_version,
            )
            if result.recommendation
            else None
        ),
    )


@router.post("/{session_id}/recommendations/next", response_model=NextRecommendationResponse)
def get_next_recommendation(
    session_id: int, user: CurrentUser, db: DbSession
) -> NextRecommendationResponse:
    """같은 세션에서 이전 템플릿을 제외한 다음 추천을 받는다."""
    session = session_service.get_owned_session(db, user, session_id)
    recommendation, shown_ids = session_service.get_next_recommendation(db, session)
    return NextRecommendationResponse(
        id=session.id,
        recommendation=RecommendationResponse(
            recommendation_id=recommendation.recommendation_id,
            project_title=recommendation.project_title,
            title=recommendation.title,
            concept=recommendation.concept,
            editing_template_id=recommendation.editing_template_id,
            editing_template_version=recommendation.editing_template_version,
        ),
        shown_template_ids=shown_ids,
    )


@router.post(
    "/{session_id}/accept", response_model=SessionAcceptResponse, status_code=HTTPStatus.CREATED
)
def accept_recommendation(
    session_id: int, user: CurrentUser, db: DbSession
) -> SessionAcceptResponse:
    """마지막 추천을 수락해 숏폼 프로젝트를 만든다. AI 호출 없이 BE 로직만으로 처리된다."""
    session = session_service.get_owned_session(db, user, session_id)
    project = session_service.accept_recommendation(db, session)
    return SessionAcceptResponse.model_validate(project)


@router.delete("/{session_id}", response_model=MessageResponse)
def discard_session(session_id: int, user: CurrentUser, db: DbSession) -> MessageResponse:
    """세션을 종료한다(새로고침/포기). 이미 종료된 세션도 200(멱등)."""
    session = session_service.get_owned_session(db, user, session_id)
    session_service.discard_session(db, session)
    return MessageResponse(message="세션이 종료되었습니다.")
