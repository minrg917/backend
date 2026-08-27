"""SNS 게시물 성과 지표 수집 배치 (API명세서 17.1 `sns_post_metrics` 채우기).

`sarils-metrics-collect.timer`가 하루 한 번 돌린다(`scripts/collect_sns_metrics.py`).
연결 확정(16.3, `LINKED`)된 게시물만 대상으로 플랫폼별 어댑터(`instagram_insights.py`
/ `youtube_analytics.py`)를 호출해 지표를 쌓는다. **매번 insert이지 update가
아니다** — `SnsPostMetric`이 추이를 보려고 스냅샷을 쌓는 설계라서다.
"""

import logging
from datetime import timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.mixins import utcnow
from app.models.sns import PostStatus, SnsConnection, SnsPost, SnsPostMetric
from app.services import instagram_insights, sns_oauth, youtube_analytics
from app.services import sns as sns_service

logger = logging.getLogger("sarils.metrics_collector")

# 이 안에 만료가 들어오면 미리 갱신한다. YouTube 액세스 토큰은 1시간짜리라 매
# 회차 걸리고, Instagram 장기토큰(60일)은 이 여유 안에 들어와야만 걸린다.
_REFRESH_BEFORE = timedelta(days=2)

_FETCHERS = {
    "INSTAGRAM": instagram_insights.fetch_media_insights,
    "YOUTUBE": youtube_analytics.fetch_video_metrics,
}


def collect_all(db: Session) -> tuple[int, int]:
    """연결 확정된 게시물을 전부 순회해 지표를 쌓는다.

    (확인한 게시물 수, 지표를 하나라도 얻은 게시물 수)를 돌려준다.
    """
    posts = list(
        db.scalars(
            select(SnsPost).where(
                SnsPost.post_status == PostStatus.LINKED,
                SnsPost.sns_connection_id.is_not(None),
                SnsPost.external_post_id.is_not(None),
            )
        )
    )

    collected = 0
    for post in posts:
        connection = db.get(SnsConnection, post.sns_connection_id)
        if connection is None or connection.sns_platform not in _FETCHERS:
            continue

        access_token = _ensure_fresh_token(db, connection)
        if access_token is None:
            continue

        fetch = _FETCHERS[connection.sns_platform]
        metrics = fetch(access_token, post.external_post_id)
        if not metrics:
            continue

        for name, value in metrics.items():
            db.add(SnsPostMetric(sns_post_id=post.id, metric_name=name, metric_value=value))
        db.commit()
        collected += 1

    return len(posts), collected


def _ensure_fresh_token(db: Session, connection: SnsConnection) -> str | None:
    """만료가 임박했으면 갱신하고 최신 액세스 토큰을 돌려준다.

    갱신 실패(리프레시 토큰 만료·연동 해제·플랫폼 키 미설정 등)는 이 연결만
    건너뛴다 — 한 사장님 계정 문제로 전체 배치가 멎으면 안 된다.
    """
    needs_refresh = (
        connection.token_expires_at is None
        or connection.token_expires_at <= utcnow() + _REFRESH_BEFORE
    )
    if not needs_refresh:
        return connection.access_token

    try:
        platform = sns_oauth.get_platform(connection.sns_platform)
        tokens = sns_oauth.refresh_access_token(platform, connection)
    except (sns_oauth.SnsAuthFailed, sns_oauth.SnsNotConfigured, sns_oauth.UnsupportedPlatform):
        logger.warning(
            "SNS 토큰 갱신 실패 (connection_id=%s) — 이번 회차는 건너뜁니다.", connection.id
        )
        return None

    updated = sns_service.save_connection(db, connection.user_id, connection.sns_platform, tokens)
    return updated.access_token
