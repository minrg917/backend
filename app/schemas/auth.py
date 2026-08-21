"""인증 관련 요청/응답 스키마 (API명세서 1.2~1.4)."""

from pydantic import EmailStr, Field, field_validator

from app.core.security import MAX_PASSWORD_BYTES
from app.schemas.common import BaseSchema, UtcDatetime

MIN_PASSWORD_LENGTH = 8


def _validate_password_bytes(value: str) -> str:
    # bcrypt는 72바이트를 넘는 입력을 거부한다. 한글은 글자당 3바이트라 글자 수만으로는
    # 막을 수 없어 바이트 길이로 검사한다.
    if len(value.encode("utf-8")) > MAX_PASSWORD_BYTES:
        raise ValueError(f"비밀번호는 UTF-8 기준 {MAX_PASSWORD_BYTES}바이트를 넘을 수 없습니다.")
    return value


class SignupRequest(BaseSchema):
    email: EmailStr
    phone: str | None = Field(default=None, max_length=20)
    password: str = Field(min_length=MIN_PASSWORD_LENGTH)
    name: str = Field(min_length=1, max_length=100)
    terms_agreed: bool
    marketing_agreed: bool = False

    _check_password = field_validator("password")(_validate_password_bytes)


class SignupResponse(BaseSchema):
    id: int
    email: str
    name: str
    is_active: bool
    terms_agreed: bool
    marketing_agreed: bool
    agreed_at: UtcDatetime | None
    created_at: UtcDatetime


class LoginRequest(BaseSchema):
    email: EmailStr
    password: str

    _check_password = field_validator("password")(_validate_password_bytes)


class LoginUser(BaseSchema):
    id: int
    email: str
    name: str


class LoginResponse(BaseSchema):
    access_token: str
    refresh_token: str
    expires_in: int
    user: LoginUser


class RefreshRequest(BaseSchema):
    refresh_token: str


class RefreshResponse(BaseSchema):
    access_token: str
    expires_in: int


class WithdrawRequest(BaseSchema):
    """회원탈퇴 요청. `reason`은 저장하지 않고 로그로만 남긴다."""

    reason: str | None = Field(default=None, max_length=500)


class WithdrawResponse(BaseSchema):
    message: str
    deleted_at: UtcDatetime
