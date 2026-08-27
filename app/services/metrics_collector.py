"""SNS 게시물 성과 지표 수집 (API명세서 17.1 `sns_post_metrics` 채우기).

두 경로로 호출된다.

1. `sarils-metrics-collect.timer`가 하루 한 번 돌리는 배치(`collect_all`,
   `scripts/collect_sns_metrics.py`) — 연결 확정된 게시물 전체를 순회한다.
2. `sns.link_post()`(16.3 연결확정)가 그 자리에서 한 건만 즉시 당겨오는
   `collect_for_post` — 연결하자마자 사장님 화면에 뭔가 보이게 하려고
   2026-08-27 추가. 배치를 최대 하루 기다리지 않아도 된다.

**매번 insert이지 update가 아니다** — `SnsPostMetric`이 추이를 보려고
스냅샷을 쌓는 설계라서다.
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

    collected = sum(1 for post in posts if _collect_for_post(db, post))
    return len(posts), collected


def collect_for_post(db: Session, post: SnsPost) -> bool:
    """게시물 하나만 즉시 수집한다 (16.3 연결확정 직후 호출, 2026-08-27).

    사장님이 연결하자마자 성과 화면에 뭔가 보이게 하려는 용도라, 다음 배치를
    기다리게 하지 않는다. 실패해도 예외를 올리지 않는다 — 이건 부가 기능이고
    16.3 연결확정 자체는 이미 끝난 뒤라, 여기서 실패해도 다음 배치가 마저 채운다.
    """
    return _collect_for_post(db, post)


def _collect_for_post(db: Session, post: SnsPost) -> bool:
    if post.sns_connection_id is None or post.external_post_id is None:
        return False

    connection = db.get(SnsConnection, post.sns_connection_id)
    if connection is None or connection.sns_platform not in _FETCHERS:
        return False

    access_token = _ensure_fresh_token(db, connection)
    if access_token is None:
        return False

    fetch = _FETCHERS[connection.sns_platform]
    metrics = fetch(access_token, post.external_post_id)
    if not metrics:
        return False

    for name, value in metrics.items():
        db.add(SnsPostMetric(sns_post_id=post.id, metric_name=name, metric_value=value))
    db.commit()
    return True


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
