"""Instagram Graph API media insights 어댑터 (API명세서 17.1, R17 성과 수집기).

`sns_oauth.py`와 같은 이유로 플랫폼 전용 호출을 이 파일에만 모은다 — Instagram이
지표 이름을 바꾸거나(2025-04 `impressions`/`plays` → `views` 통합) 엔드포인트
버전을 올려도 이 파일만 고치면 된다.
"""

import logging
from decimal import Decimal

import httpx

from app.core.config import settings

logger = logging.getLogger("sarils.instagram_insights")

_INSIGHTS_URL_TEMPLATE = "https://graph.instagram.com/v22.0/{media_id}/insights"

# API명세서 17.1에서 내려주기로 한 지표 이름 그대로 요청한다. `saved`만 API 응답
# 필드명이 우리 스펙(`saves`)과 달라 파싱할 때 이름을 바꿔준다.
_REQUESTED_METRICS = ("views", "likes", "comments", "shares", "saved", "reach")
_METRIC_NAME_MAP = {"saved": "saves"}


def fetch_media_insights(access_token: str, media_id: str) -> dict[str, Decimal]:
    """게시물 하나의 최신 누적 지표를 가져온다.

    **요청했지만 값이 없는 지표는 응답 배열 자체에서 빠진다**(플랫폼 쪽 사양).
    있는 것만 돌려준다 — `SnsPostMetric`이 "없는 지표는 행 자체가 없다"로 설계돼
    있어(0과 구분하기 위해) 그대로 맞아떨어진다.

    호출이 실패해도 예외를 올리지 않고 빈 dict를 돌려준다. 수집기가 게시물
    여러 개를 순회하는데, 하나 실패했다고(토큰 만료 등) 나머지까지 멈추면 안 된다.
    """
    try:
        response = httpx.get(
            _INSIGHTS_URL_TEMPLATE.format(media_id=media_id),
            params={"metric": ",".join(_REQUESTED_METRICS), "access_token": access_token},
            timeout=settings.EXTERNAL_API_TIMEOUT_SECONDS,
        )
        response.raise_for_status()
        body = response.json()
    except (httpx.HTTPError, ValueError):
        logger.exception("Instagram insights 조회 실패 (media_id=%s)", media_id)
        return {}

    metrics: dict[str, Decimal] = {}
    for item in body.get("data", []):
        name = _METRIC_NAME_MAP.get(item["name"], item["name"])
        values = item.get("values") or []
        if not values or values[0].get("value") is None:
            continue
        metrics[name] = Decimal(str(values[0]["value"]))
    return metrics
