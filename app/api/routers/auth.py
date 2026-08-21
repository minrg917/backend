"""인증 API (API명세서 1.2 회원가입 / 1.3 로그인 / 1.4 로그아웃·세션갱신)."""

from http import HTTPStatus

from fastapi import APIRouter

from app.api.deps import CurrentUser, DbSession
from app.core.security import access_token_expires_in
from app.schemas.auth import (
    LoginRequest,
    LoginResponse,
    LoginUser,
    RefreshRequest,
    RefreshResponse,
    SignupRequest,
    SignupResponse,
)
from app.schemas.common import MessageResponse
from app.services import auth as auth_service

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/signup", response_model=SignupResponse, status_code=HTTPStatus.CREATED)
def signup(payload: SignupRequest, db: DbSession) -> SignupResponse:
    """회원가입. 인증 불필요."""
    user = auth_service.signup(db, payload)
    return SignupResponse.model_validate(user)


@router.post("/login", response_model=LoginResponse)
def login(payload: LoginRequest, db: DbSession) -> LoginResponse:
    """로그인. 액세스/리프레시 토큰을 발급한다. 인증 불필요."""
    user = auth_service.authenticate(db, payload.email, payload.password)
    access, refresh = auth_service.issue_login_tokens(user)
    return LoginResponse(
        access_token=access.token,
        refresh_token=refresh.token,
        expires_in=access_token_expires_in(),
        user=LoginUser.model_validate(user),
    )


@router.post("/logout", response_model=MessageResponse)
def logout(user: CurrentUser) -> MessageResponse:
    """로그아웃.

    토큰을 서버에 저장하지 않는 무상태 방식이라, 서버가 할 일은 요청자가 유효한
    로그인 상태인지 확인하는 것까지다. 실제 폐기는 클라이언트가 저장소에서
    액세스/리프레시 토큰을 지우는 것으로 완료된다.
    (`docs/IMPLEMENTATION.md` 결정 로그 2026-08-21 참고)
    """
    del user  # 인증 확인 용도로만 받는다
    return MessageResponse(message="로그아웃 되었습니다.")


@router.post("/refresh", response_model=RefreshResponse)
def refresh(payload: RefreshRequest, db: DbSession) -> RefreshResponse:
    """리프레시 토큰으로 액세스 토큰을 재발급한다. 액세스 토큰이 만료된 상태로
    호출되므로 인증 헤더는 요구하지 않는다."""
    access = auth_service.reissue_access_token(db, payload.refresh_token)
    return RefreshResponse(access_token=access.token, expires_in=access_token_expires_in())
