"""사용자 API (API명세서 1.4 회원탈퇴)."""

from fastapi import APIRouter

from app.api.deps import CurrentUser, DbSession
from app.schemas.auth import (
    UserProfileResponse,
    UserProfileUpdateRequest,
    UserProfileUpdateResponse,
    WithdrawRequest,
    WithdrawResponse,
)
from app.schemas.common import MessageResponse
from app.schemas.push_token import PushTokenRegisterRequest
from app.services import auth as auth_service
from app.services import push_token as push_token_service

router = APIRouter(prefix="/users", tags=["users"])


@router.delete("/me", response_model=WithdrawResponse)
def withdraw(
    user: CurrentUser,
    db: DbSession,
    payload: WithdrawRequest | None = None,
) -> WithdrawResponse:
    """회원탈퇴. 레코드를 삭제하지 않고 `is_active`를 FALSE로 내린다.

    탈퇴 사유(Body)는 선택이다. DELETE 요청 본문을 못 보내는 클라이언트가 있어
    Body 없이 호출해도 동작하게 했다.
    """
    deleted_at = auth_service.withdraw(db, user, payload.reason if payload else None)
    return WithdrawResponse(message="탈퇴가 완료되었습니다.", deleted_at=deleted_at)


@router.get("/me", response_model=UserProfileResponse)
def get_profile(user: CurrentUser) -> UserProfileResponse:
    """내 회원정보를 돌려준다 (API명세서 1.5)."""
    return UserProfileResponse.model_validate(user)


@router.patch("/me", response_model=UserProfileUpdateResponse, response_model_exclude_unset=True)
def update_profile(
    payload: UserProfileUpdateRequest, user: CurrentUser, db: DbSession
) -> UserProfileUpdateResponse:
    """회원정보를 수정한다.

    **가게 정보(가게명·업종·브랜드톤)는 3.1 `PATCH /stores/{storeId}`** 다.
    여기서는 사용자 계정 정보만 바꾼다.
    """
    changed = set(payload.model_dump(exclude_unset=True))
    user = auth_service.update_profile(db, user, payload)

    data: dict[str, object] = {"id": user.id, "updated_at": user.updated_at}
    data.update({field: getattr(user, field) for field in changed})
    return UserProfileUpdateResponse(**data)


@router.post("/me/push-tokens", response_model=MessageResponse)
def register_push_token(
    payload: PushTokenRegisterRequest, user: CurrentUser, db: DbSession
) -> MessageResponse:
    """편집 완료 푸시 알림을 받을 디바이스 토큰을 등록한다.

    사용자당 토큰 하나만 유지한다 — 같은 사용자가 새 토큰을 보내면 이전 값을
    덮어쓴다(재설치·재로그인 대응).
    """
    push_token_service.upsert_token(db, user, payload.push_token, payload.platform)
    return MessageResponse(message="푸시 토큰이 등록되었습니다.")
