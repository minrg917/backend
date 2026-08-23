"""요청 로깅 미들웨어 테스트 (`app/core/logging.py`)."""

import logging

import pytest
from fastapi.testclient import TestClient


def test_successful_request_logged_at_info(
    client: TestClient, caplog: pytest.LogCaptureFixture
) -> None:
    with caplog.at_level(logging.INFO, logger="sarils.request"):
        client.get("/onboarding")

    record = next(r for r in caplog.records if r.name == "sarils.request")
    assert record.levelno == logging.INFO
    assert "GET /onboarding -> 200" in record.getMessage()


def test_client_error_logged_at_warning(
    client: TestClient, caplog: pytest.LogCaptureFixture
) -> None:
    """4xx는 잘못된 요청이지 서버 장애가 아니다 — ERROR로 올리면 알림이 오염된다."""
    with caplog.at_level(logging.DEBUG, logger="sarils.request"):
        client.get("/users/me")  # 인증 없음 → 401

    record = next(r for r in caplog.records if r.name == "sarils.request")
    assert record.levelno == logging.WARNING
    assert "-> 401" in record.getMessage()


def test_health_check_is_quiet(client: TestClient, caplog: pytest.LogCaptureFixture) -> None:
    """헬스체크는 주기적으로 들어와 실제 요청을 묻히게 한다."""
    with caplog.at_level(logging.INFO, logger="sarils.request"):
        client.get("/health")

    assert [r for r in caplog.records if r.name == "sarils.request"] == []


def test_request_id_returned_in_header(client: TestClient) -> None:
    """로그와 응답을 이어 보기 위한 식별자. 공통 에러 포맷은 건드리지 않는다."""
    response = client.get("/onboarding")

    assert len(response.headers["X-Request-ID"]) == 8


def test_request_id_differs_per_request(client: TestClient) -> None:
    first = client.get("/onboarding").headers["X-Request-ID"]
    second = client.get("/onboarding").headers["X-Request-ID"]

    assert first != second


def test_query_string_not_logged(client: TestClient, caplog: pytest.LogCaptureFixture) -> None:
    """검색어에 개인정보가 섞일 수 있어 경로만 남긴다."""
    with caplog.at_level(logging.DEBUG, logger="sarils.request"):
        client.get("/video-formats?keyword=비밀검색어")

    messages = " ".join(r.getMessage() for r in caplog.records if r.name == "sarils.request")
    assert "비밀검색어" not in messages
    assert "/video-formats" in messages
