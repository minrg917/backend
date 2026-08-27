"""Instagram insights 어댑터 테스트 (R17 성과 수집기, 2026-08-27)."""

from decimal import Decimal
from typing import Any

import httpx
import pytest

from app.services import instagram_insights


def test_fetch_media_insights_parses_only_present_metrics(monkeypatch: pytest.MonkeyPatch) -> None:
    """요청했지만 값이 없는 지표는 응답 배열에서 빠진다 — 있는 것만 담아야 한다."""

    def fake_get(url: str, params: dict[str, Any], timeout: float) -> httpx.Response:
        assert url == "https://graph.instagram.com/v22.0/17998877/insights"
        assert params["access_token"] == "token-abc"
        return httpx.Response(
            200,
            json={
                "data": [
                    {"name": "views", "values": [{"value": 15230}]},
                    {"name": "likes", "values": [{"value": 842}]},
                    {"name": "saved", "values": [{"value": 120}]},
                ]
            },
            request=httpx.Request("GET", url),
        )

    monkeypatch.setattr(httpx, "get", fake_get)

    metrics = instagram_insights.fetch_media_insights("token-abc", "17998877")

    assert metrics == {
        "views": Decimal("15230"),
        "likes": Decimal("842"),
        "saves": Decimal("120"),  # saved -> saves 이름 매핑
    }


def test_fetch_media_insights_returns_empty_on_http_error(monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_get(url: str, params: dict[str, Any], timeout: float) -> httpx.Response:
        return httpx.Response(401, request=httpx.Request("GET", url))

    monkeypatch.setattr(httpx, "get", fake_get)

    assert instagram_insights.fetch_media_insights("expired-token", "17998877") == {}


def test_fetch_media_insights_returns_empty_on_network_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fake_get(url: str, params: dict[str, Any], timeout: float) -> httpx.Response:
        raise httpx.ConnectError("boom", request=httpx.Request("GET", url))

    monkeypatch.setattr(httpx, "get", fake_get)

    assert instagram_insights.fetch_media_insights("token-abc", "17998877") == {}
