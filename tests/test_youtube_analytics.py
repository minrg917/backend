"""YouTube Analytics 어댑터 테스트 (R17 성과 수집기, 2026-08-27)."""

from datetime import date
from decimal import Decimal
from typing import Any

import httpx
import pytest

from app.services import youtube_analytics


def test_fetch_video_metrics_parses_columnar_response(monkeypatch: pytest.MonkeyPatch) -> None:
    """reports.query는 Instagram과 달리 columnHeaders + rows의 컬럼형 응답이다."""

    def fake_get(
        url: str, params: dict[str, Any], headers: dict[str, str], timeout: float
    ) -> httpx.Response:
        assert url == "https://youtubeanalytics.googleapis.com/v2/reports"
        assert params["startDate"] == "2026-01-01"
        assert params["endDate"] == "2026-08-27"
        assert params["filters"] == "video==abc123"
        assert headers["Authorization"] == "Bearer token-xyz"
        return httpx.Response(
            200,
            json={
                "columnHeaders": [
                    {"name": "video"},
                    {"name": "views"},
                    {"name": "averageViewPercentage"},
                    {"name": "subscribersGained"},
                ],
                "rows": [["abc123", 15230, 42.5, 3]],
            },
            request=httpx.Request("GET", url),
        )

    monkeypatch.setattr(httpx, "get", fake_get)

    metrics = youtube_analytics.fetch_video_metrics("token-xyz", "abc123", today=date(2026, 8, 27))

    assert metrics == {
        "views": Decimal("15230"),
        "averageViewPercentage": Decimal("42.5"),
        "subscribersGained": Decimal("3"),
    }


def test_fetch_video_metrics_returns_empty_when_no_rows(monkeypatch: pytest.MonkeyPatch) -> None:
    """아직 이 채널 영상이 아니거나 지표가 하나도 없으면 rows가 비어 있다."""

    def fake_get(
        url: str, params: dict[str, Any], headers: dict[str, str], timeout: float
    ) -> httpx.Response:
        return httpx.Response(
            200, json={"columnHeaders": [], "rows": []}, request=httpx.Request("GET", url)
        )

    monkeypatch.setattr(httpx, "get", fake_get)

    assert youtube_analytics.fetch_video_metrics("token-xyz", "abc123") == {}


def test_fetch_video_metrics_returns_empty_on_http_error(monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_get(
        url: str, params: dict[str, Any], headers: dict[str, str], timeout: float
    ) -> httpx.Response:
        return httpx.Response(401, request=httpx.Request("GET", url))

    monkeypatch.setattr(httpx, "get", fake_get)

    assert youtube_analytics.fetch_video_metrics("expired-token", "abc123") == {}
