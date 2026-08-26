"""Expo Push 발송 어댑터.

편집 완료를 감시하는 배치(`app/services/edit_notify.py`)가 완료를 감지하면
이 모듈로 실제 알림을 보낸다. Firebase(FCM)/APNs 자격증명은 전부 Expo/EAS
쪽에 등록해두면 되고(`docs/FE_NOTICE_2026-08-26-03.md` 참고), 이 코드는
Expo의 공개 발송 API에 HTTP 요청 하나만 보내면 된다 — Firebase 키를 백엔드가
직접 다루지 않는다.
"""

import logging
from typing import Any

import httpx

logger = logging.getLogger("sarils.push_notify")

_EXPO_PUSH_URL = "https://exp.host/--/api/v2/push/send"


def send_push(push_token: str, title: str, body: str, data: dict[str, Any] | None = None) -> bool:
    """Expo Push API로 알림 하나를 보낸다.

    **실패해도 예외를 올리지 않고 `False`를 돌려준다.** 완료 감시 배치가 여러
    사용자를 순회하며 보내는데, 한 명에게 실패했다고(예: 토큰 만료) 나머지까지
    막으면 안 된다 — 로깅만 하고 계속 진행한다.
    """
    try:
        response = httpx.post(
            _EXPO_PUSH_URL,
            json={"to": push_token, "title": title, "body": body, "data": data or {}},
            timeout=httpx.Timeout(10.0, connect=5.0),
        )
        response.raise_for_status()
    except httpx.HTTPError:
        logger.exception("Expo push 발송 실패")
        return False
    return True
