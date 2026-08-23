"""비밀번호 해싱과 JWT 토큰 발급/검증.

- 비밀번호: bcrypt로 해싱한다(솔트는 bcrypt가 해시 문자열 안에 포함).
- 토큰: HS256 JWT. 액세스 토큰은 API 인증에, 리프레시 토큰은 `/auth/refresh`에 쓴다.
  두 토큰은 payload의 `type`으로 구분하며, 액세스 토큰으로 refresh를 시도하는 등의
  오용을 `decode_token(expected_type=...)`에서 막는다.
"""

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from enum import StrEnum

import bcrypt
import jwt

from app.core.config import settings
from app.core.exceptions import UnauthorizedError

# bcrypt는 72바이트를 넘는 입력을 거부한다. 요청 스키마에서 미리 막는다.
MAX_PASSWORD_BYTES = 72


class TokenType(StrEnum):
    ACCESS = "access"
    REFRESH = "refresh"


@dataclass(frozen=True)
class IssuedToken:
    """발급된 토큰과, 저장/응답에 필요한 부가 정보."""

    token: str
    jti: str  # 토큰 식별자. 리프레시 토큰 폐기(로그아웃) 시 사용한다.
    expires_at: datetime


@dataclass(frozen=True)
class TokenPayload:
    user_id: int
    jti: str
    token_type: TokenType
    expires_at: datetime


class TokenExpired(UnauthorizedError):
    error_code = "TOKEN_EXPIRED"
    message = "토큰이 만료되었습니다. 다시 로그인해주세요."


class InvalidToken(UnauthorizedError):
    error_code = "INVALID_TOKEN"
    message = "유효하지 않은 토큰입니다."


def hash_password(plain_password: str) -> str:
    """비밀번호를 bcrypt 해시 문자열로 만든다."""
    return bcrypt.hashpw(plain_password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(plain_password: str, password_hash: str | None) -> bool:
    """평문 비밀번호가 해시와 일치하는지 확인한다.

    `password_hash`가 없거나(소셜 로그인 등) 형식이 깨진 경우에도 예외를 던지지 않고
    False를 돌려준다. 호출부에서 "이메일 없음"과 "비밀번호 틀림"을 구분하지 않기 위해서다.
    """
    if not password_hash:
        return False
    try:
        return bcrypt.checkpw(plain_password.encode("utf-8"), password_hash.encode("utf-8"))
    except ValueError:
        return False


def access_token_expires_in() -> int:
    """액세스 토큰 만료까지의 초. API명세서 1.3의 `expires_in` 값."""
    return settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60


def _create_token(user_id: int, token_type: TokenType, lifetime: timedelta) -> IssuedToken:
    now = datetime.now(UTC)
    expires_at = now + lifetime
    jti = str(uuid.uuid4())
    payload = {
        "sub": str(user_id),  # JWT 표준상 sub는 문자열이어야 한다
        "type": token_type.value,
        "jti": jti,
        "iat": int(now.timestamp()),
        "exp": int(expires_at.timestamp()),
    }
    token = jwt.encode(payload, settings.JWT_SECRET_KEY, algorithm=settings.JWT_ALGORITHM)
    return IssuedToken(token=token, jti=jti, expires_at=expires_at)


def create_access_token(user_id: int) -> IssuedToken:
    return _create_token(
        user_id,
        TokenType.ACCESS,
        timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES),
    )


def create_refresh_token(user_id: int) -> IssuedToken:
    return _create_token(
        user_id,
        TokenType.REFRESH,
        timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS),
    )


def decode_token(token: str, expected_type: TokenType) -> TokenPayload:
    """토큰을 검증하고 payload를 돌려준다.

    만료/서명오류/타입불일치는 모두 401(`UnauthorizedError`)로 통일한다.
    """
    try:
        payload = jwt.decode(token, settings.JWT_SECRET_KEY, algorithms=[settings.JWT_ALGORITHM])
    except jwt.ExpiredSignatureError as exc:
        raise TokenExpired from exc
    except jwt.PyJWTError as exc:
        raise InvalidToken from exc

    if payload.get("type") != expected_type.value:
        raise InvalidToken

    try:
        user_id = int(payload["sub"])
        jti = str(payload["jti"])
        expires_at = datetime.fromtimestamp(payload["exp"], tz=UTC)
    except (KeyError, TypeError, ValueError) as exc:
        raise InvalidToken from exc

    return TokenPayload(
        user_id=user_id,
        jti=jti,
        token_type=expected_type,
        expires_at=expires_at,
    )
