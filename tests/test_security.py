"""비밀번호 해싱 / JWT 유틸 테스트."""

import pytest

from app.core.exceptions import UnauthorizedError
from app.core.security import (
    TokenType,
    create_access_token,
    create_refresh_token,
    decode_token,
    hash_password,
    verify_password,
)


def test_password_hash_roundtrip() -> None:
    hashed = hash_password("sarils1234!")

    assert hashed != "sarils1234!"
    assert verify_password("sarils1234!", hashed) is True
    assert verify_password("wrong-password", hashed) is False


def test_verify_password_returns_false_for_missing_or_broken_hash() -> None:
    assert verify_password("sarils1234!", None) is False
    assert verify_password("sarils1234!", "not-a-bcrypt-hash") is False


def test_access_token_roundtrip() -> None:
    issued = create_access_token(user_id=1)

    payload = decode_token(issued.token, TokenType.ACCESS)

    assert payload.user_id == 1
    assert payload.jti == issued.jti
    assert payload.token_type is TokenType.ACCESS


def test_refresh_token_cannot_be_used_as_access_token() -> None:
    issued = create_refresh_token(user_id=1)

    with pytest.raises(UnauthorizedError) as exc_info:
        decode_token(issued.token, TokenType.ACCESS)

    assert exc_info.value.error_code == "INVALID_TOKEN"


def test_tampered_token_is_rejected() -> None:
    issued = create_access_token(user_id=1)
    header, payload, signature = issued.token.split(".")
    # 서명의 마지막 글자는 base64url 패딩 비트라 바꿔도 디코딩 결과가 같을 수 있다.
    # 6비트를 온전히 담는 첫 글자를 바꿔야 서명이 반드시 달라진다.
    tampered = f"{header}.{payload}.{'a' if signature[0] != 'a' else 'b'}{signature[1:]}"

    with pytest.raises(UnauthorizedError) as exc_info:
        decode_token(tampered, TokenType.ACCESS)

    assert exc_info.value.error_code == "INVALID_TOKEN"


def test_expired_token_is_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    from app.core import security

    monkeypatch.setattr(security.settings, "ACCESS_TOKEN_EXPIRE_MINUTES", -1)
    issued = create_access_token(user_id=1)

    with pytest.raises(UnauthorizedError) as exc_info:
        decode_token(issued.token, TokenType.ACCESS)

    assert exc_info.value.error_code == "TOKEN_EXPIRED"
