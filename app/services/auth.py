"""회원가입/로그인/세션갱신/탈퇴 로직 (API명세서 1.2~1.4)."""

import logging
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.exceptions import BadRequestError, ConflictError, UnauthorizedError
from app.core.security import (
    InactiveUser,
    IssuedToken,
    TokenType,
    create_access_token,
    create_refresh_token,
    decode_token,
    hash_password,
    verify_password,
)
from app.models.mixins import utcnow
from app.models.user import User
from app.schemas.auth import SignupRequest, UserProfileUpdateRequest

logger = logging.getLogger(__name__)


class EmailAlreadyExists(ConflictError):
    error_code = "EMAIL_ALREADY_EXISTS"
    message = "이미 가입된 이메일입니다."


class TermsNotAgreed(BadRequestError):
    error_code = "TERMS_NOT_AGREED"
    message = "필수 약관에 동의해야 가입할 수 있습니다."


class InvalidCredentials(UnauthorizedError):
    error_code = "INVALID_CREDENTIALS"
    message = "이메일 또는 비밀번호가 올바르지 않습니다."


def get_user_by_email(db: Session, email: str) -> User | None:
    return db.scalar(select(User).where(User.email == email))


def signup(db: Session, payload: SignupRequest) -> User:
    """새 계정을 만든다.

    필수 약관 미동의는 400, 이메일 중복은 409.
    """
    if not payload.terms_agreed:
        raise TermsNotAgreed

    if get_user_by_email(db, payload.email) is not None:
        raise EmailAlreadyExists

    user = User(
        email=payload.email,
        phone=payload.phone,
        password_hash=hash_password(payload.password),
        name=payload.name,
        is_active=True,
        terms_agreed=payload.terms_agreed,
        marketing_agreed=payload.marketing_agreed,
        agreed_at=utcnow(),
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def authenticate(db: Session, email: str, password: str) -> User:
    """이메일/비밀번호를 검증하고 사용자를 돌려준다.

    계정이 없는 경우와 비밀번호가 틀린 경우를 같은 에러로 응답한다
    (가입 여부가 노출되지 않도록).
    """
    user = get_user_by_email(db, email)
    if user is None or not verify_password(password, user.password_hash):
        raise InvalidCredentials
    if not user.is_active:
        raise InactiveUser
    return user


def issue_login_tokens(user: User) -> tuple[IssuedToken, IssuedToken]:
    """로그인 시 발급할 (액세스, 리프레시) 토큰 쌍."""
    return create_access_token(user.id), create_refresh_token(user.id)


def reissue_access_token(db: Session, refresh_token: str) -> IssuedToken:
    """리프레시 토큰으로 액세스 토큰을 다시 발급한다.

    토큰이 만료·위조됐거나 액세스 토큰을 대신 넣은 경우 401(`decode_token`),
    계정이 사라졌거나 탈퇴 상태면 401.
    """
    payload = decode_token(refresh_token, TokenType.REFRESH)

    user = db.get(User, payload.user_id)
    if user is None:
        raise InvalidCredentials
    if not user.is_active:
        raise InactiveUser

    return create_access_token(user.id)


def withdraw(db: Session, user: User, reason: str | None = None) -> datetime:
    """회원탈퇴. 레코드를 지우지 않고 `is_active`만 내린다.

    ERD의 `is_active` 코멘트가 "FALSE=탈퇴"로 정의돼 있고, 가게/프로젝트 등이
    `user_id`를 참조하고 있어 하드 삭제하면 참조가 깨진다.
    탈퇴 사유(`reason`)는 저장할 컬럼이 ERD에 없어 로그로만 남긴다.
    """
    user.is_active = False
    deleted_at = utcnow()
    user.updated_at = deleted_at
    db.commit()

    if reason:
        logger.info("회원탈퇴 user_id=%s reason=%s", user.id, reason)

    return deleted_at


def update_profile(db: Session, user: User, payload: UserProfileUpdateRequest) -> User:
    """회원정보를 부분 수정한다 (API명세서 1.5 PATCH).

    보낸 필드만 반영한다. 스키마가 `name`·`phone`·`marketing_agreed`만 받으므로
    `email`이나 비밀번호가 섞여 와도 여기까지 오지 않는다.
    """
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(user, field, value)
    db.commit()
    db.refresh(user)
    return user
