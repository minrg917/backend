"""Expo Push 발송 어댑터 테스트."""

from typing import Any

import httpx
import pytest

from app.services import push_notify


def test_send_push_posts_to_expo_api(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, Any] = {}

    def fake_post(url: str, json: dict[str, Any], timeout: httpx.Timeout) -> httpx.Response:
        captured["url"] = url
        captured["json"] = json
        return httpx.Response(
            200, json={"data": {"status": "ok"}}, request=httpx.Request("POST", url)
        )

    monkeypatch.setattr(httpx, "post", fake_post)

    result = push_notify.send_push(
        "ExponentPushToken[abc]", "완료!", "확인해보세요", {"shorts_project_id": 1}
    )

    assert result is True
    assert captured["url"] == "https://exp.host/--/api/v2/push/send"
    assert captured["json"] == {
        "to": "ExponentPushToken[abc]",
        "title": "완료!",
        "body": "확인해보세요",
        "data": {"shorts_project_id": 1},
    }


def test_send_push_returns_false_on_http_error(monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_post(url: str, json: dict[str, Any], timeout: httpx.Timeout) -> httpx.Response:
        return httpx.Response(500, request=httpx.Request("POST", url))

    monkeypatch.setattr(httpx, "post", fake_post)

    assert push_notify.send_push("ExponentPushToken[abc]", "제목", "본문") is False


def test_send_push_returns_false_on_network_error(monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_post(url: str, json: dict[str, Any], timeout: httpx.Timeout) -> httpx.Response:
        raise httpx.ConnectError("boom", request=httpx.Request("POST", url))

    monkeypatch.setattr(httpx, "post", fake_post)

    assert push_notify.send_push("ExponentPushToken[abc]", "제목", "본문") is False
