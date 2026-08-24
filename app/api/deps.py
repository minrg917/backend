"""라우터에서 공용으로 쓰는 FastAPI 의존성."""

from typing import Annotated

from fastapi import Depends
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.core.exceptions import UnauthorizedError
from app.core.security import InactiveUser, TokenType, decode_token
from app.db.session import get_db
from app.models.user import User

# auto_error=False: 헤더가 없을 때 FastAPI 기본 403 대신 우리 401 포맷으로 응답하기 위함.
bearer_scheme = HTTPBearer(auto_error=False)

DbSession = Annotated[Session, Depends(get_db)]


class AuthenticationRequired(UnauthorizedError):
    error_code = "AUTHENTICATION_REQUIRED"
    message = "인증이 필요합니다. Authorization 헤더를 확인해주세요."


def get_current_user(
    db: DbSession,
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer_scheme)] = None,
) -> User:
    """`Authorization: Bearer {accessToken}`를 검증하고 로그인 사용자를 돌려준다.

    헤더가 없거나 / 토큰이 만료·위조됐거나 / 계정이 탈퇴 상태면 401.
    """
    if credentials is None or not credentials.credentials:
        raise AuthenticationRequired

    payload = decode_token(credentials.credentials, TokenType.ACCESS)

    user = db.get(User, payload.user_id)
    if user is None:
        raise AuthenticationRequired
    if not user.is_active:
        raise InactiveUser

    return user


# 라우터에서 `user: CurrentUser` 로 선언하면 인증이 걸린다.
CurrentUser = Annotated[User, Depends(get_current_user)]
