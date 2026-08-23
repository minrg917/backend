"""사용자 API (API명세서 1.4 회원탈퇴)."""

from fastapi import APIRouter

from app.api.deps import CurrentUser, DbSession
from app.schemas.auth import WithdrawRequest, WithdrawResponse
from app.services import auth as auth_service

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
