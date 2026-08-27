"""YouTube Analytics API 어댑터 (API명세서 17.1, R17 성과 수집기).

`reports.query`는 Instagram과 달리 컬럼형 응답(`columnHeaders` + `rows`)이라
파싱 방식이 이 파일 안에서만 다르게 처리된다.
"""

import logging
from datetime import date
from decimal import Decimal

import httpx

from app.core.config import settings

logger = logging.getLogger("sarils.youtube_analytics")

_REPORTS_URL = "https://youtubeanalytics.googleapis.com/v2/reports"

# 채널 단위가 아니라 영상 하나의 누적값만 필요하다. 그래서 "지난 수집 이후"로
# 증분 조회하지 않고, 매번 이 고정 과거값부터 오늘까지 전체 기간을 조회해
# 최신 누적 스냅샷 하나만 저장한다(2026-08-27 확정) — 누적값이라 증분 조회와
# 결과가 같고, "지난 수집 시각"을 따로 추적할 필요가 없어 구현이 단순해진다.
_START_DATE = date(2026, 1, 1)

# API명세서 17.1에서 내려주기로 한 지표 이름과 YouTube Analytics API의 실제
# 지표 이름이 그대로 같다 — 파싱 시 이름 매핑이 필요 없다.
_REQUESTED_METRICS = (
    "views",
    "likes",
    "comments",
    "shares",
    "averageViewPercentage",
    "subscribersGained",
)


def fetch_video_metrics(
    access_token: str, video_id: str, today: date | None = None
) -> dict[str, Decimal]:
    """영상 하나의 누적 지표를 가져온다.

    **값이 없는 열은 담지 않는다** — Instagram 어댑터와 같은 이유로 0과
    "지표 없음"을 구분한다.

    호출이 실패해도 예외를 올리지 않고 빈 dict를 돌려준다.
    """
    try:
        response = httpx.get(
            _REPORTS_URL,
            params={
                "ids": "channel==MINE",
                "startDate": _START_DATE.isoformat(),
                "endDate": (today or date.today()).isoformat(),
                "metrics": ",".join(_REQUESTED_METRICS),
                "dimensions": "video",
                "filters": f"video=={video_id}",
            },
            headers={"Authorization": f"Bearer {access_token}"},
            timeout=settings.EXTERNAL_API_TIMEOUT_SECONDS,
        )
        response.raise_for_status()
        body = response.json()
    except (httpx.HTTPError, ValueError):
        logger.exception("YouTube Analytics 조회 실패 (video_id=%s)", video_id)
        return {}

    rows = body.get("rows") or []
    if not rows:
        return {}
    headers = [column["name"] for column in body.get("columnHeaders", [])]
    row = rows[0]

    metrics: dict[str, Decimal] = {}
    for name, value in zip(headers, row, strict=True):
        if name not in _REQUESTED_METRICS or value is None:
            continue
        metrics[name] = Decimal(str(value))
    return metrics
