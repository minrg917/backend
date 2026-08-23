"""성과분석 로직 (API명세서 17.1 지표 조회 / 17.2 성과 비교)."""

from datetime import date, datetime, time
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.exceptions import NotFoundError
from app.models.mixins import utcnow
from app.models.shorts_project import ShortsProject
from app.models.sns import SnsPost, SnsPostMetric
from app.models.store import Store
from app.models.user import User
from app.models.video_output import VideoOutput

# 비교에 쓰는 지표 이름. 플랫폼마다 주는 이름이 달라도 수집 단계에서 이 이름으로 맞춘다.
METRIC_VIEWS = "views"
METRIC_REACH = "reach"
METRIC_SAVES = "saves"

# 표본이 이보다 적으면 비교 자체를 신뢰할 수 없다 (기능명세서 S17.3.1 "표본<3 신뢰도 낮음").
MIN_SAMPLE_SIZE = 3

# 게시 직후에는 지표가 계속 오르는 중이라 확정된 값이 아니다.
_CONFIDENCE_DAYS = ((7, "낮음"), (30, "보통"))


class SnsPostNotFound(NotFoundError):
    error_code = "SNS_POST_NOT_FOUND"
    message = "게시물을 찾을 수 없습니다."


def get_owned_post(db: Session, owner: User, post_id: int) -> SnsPost:
    """본인 가게의 게시물만 가져온다. 남의 것은 404(존재 자체를 숨긴다).

    소유권이 `sns_posts → video_outputs → store_shorts_projects → stores → users`로
    네 단계 떨어져 있어 조인으로 한 번에 확인한다.
    """
    post = db.scalars(
        select(SnsPost)
        .join(VideoOutput, VideoOutput.id == SnsPost.video_output_id)
        .join(ShortsProject, ShortsProject.id == VideoOutput.shorts_project_id)
        .join(Store, Store.id == ShortsProject.store_id)
        .where(SnsPost.id == post_id, Store.user_id == owner.id)
    ).first()
    if post is None:
        raise SnsPostNotFound
    return post


# ---------------------------------------------------------------- 17.1 지표 조회


def list_metrics(
    db: Session, post: SnsPost, date_from: date | None, date_to: date | None
) -> list[SnsPostMetric]:
    """수집된 지표 스냅샷을 시간순으로 돌려준다 (API명세서 17.1).

    **없는 지표는 행 자체가 없다**(기능명세서 S17.2.1 "플랫폼마다 없는 지표는 N/A").
    `0`으로 채우지 않는 이유는 `0`이 "실제로 0이었다"는 주장이기 때문이다.

    `to`는 그날 하루를 포함한다 — 사용자가 날짜로 고르는 값이라 `2026-08-26`이
    "26일까지"로 읽히는 게 자연스럽다.
    """
    statement = select(SnsPostMetric).where(SnsPostMetric.sns_post_id == post.id)
    if date_from is not None:
        statement = statement.where(
            SnsPostMetric.collected_at >= datetime.combine(date_from, time.min)
        )
    if date_to is not None:
        statement = statement.where(
            SnsPostMetric.collected_at <= datetime.combine(date_to, time.max)
        )
    return list(db.scalars(statement.order_by(SnsPostMetric.collected_at, SnsPostMetric.id)))


def latest_values(db: Session, post_ids: list[int]) -> dict[int, dict[str, Decimal]]:
    """게시물별 지표의 **가장 최근 값**을 모아 돌려준다.

    스냅샷이 여러 번 쌓이므로 비교에는 마지막 값을 쓴다. 게시물마다 따로 조회하면
    비교 대상 수만큼 쿼리가 늘어나 한 번에 가져온 뒤 메모리에서 접는다.
    """
    if not post_ids:
        return {}

    rows = db.scalars(
        select(SnsPostMetric)
        .where(SnsPostMetric.sns_post_id.in_(post_ids))
        .order_by(SnsPostMetric.collected_at, SnsPostMetric.id)
    )

    latest: dict[int, dict[str, Decimal]] = {}
    for row in rows:
        if row.metric_value is None:
            continue
        # 시간순이라 뒤에 오는 값이 최신이다 — 그대로 덮어쓴다.
        latest.setdefault(row.sns_post_id, {})[row.metric_name] = row.metric_value
    return latest


# ---------------------------------------------------------------- 17.2 성과 비교


def compare(
    db: Session, store: Store, platform: str | None, goal: str | None
) -> list[tuple[SnsPost, Decimal | None, Decimal | None, int, str]]:
    """같은 조건의 게시물들을 비율 지표로 비교한다 (API명세서 17.2).

    **누적 조회수를 그대로 비교하면 오래된 영상이 항상 이긴다**(기능명세서 S17.3.1).
    그래서 절대값이 아니라 비율(`view_rate`·`save_rate`)로 줄을 세운다.

    `platform`으로 거르는 것도 같은 이유다 — 플랫폼마다 조회수 집계 기준이 달라
    Instagram 1만 회와 YouTube 1만 회는 같은 값이 아니다. 서로 다른 플랫폼을
    한 표에 섞지 않는다.

    (게시물, view_rate, save_rate, 경과일, 신뢰도) 튜플 목록을 돌려준다.
    """
    statement = (
        select(SnsPost)
        .join(VideoOutput, VideoOutput.id == SnsPost.video_output_id)
        .join(ShortsProject, ShortsProject.id == VideoOutput.shorts_project_id)
        .where(ShortsProject.store_id == store.id)
    )
    if platform:
        statement = statement.where(SnsPost.post_platform == platform)
    if goal:
        statement = statement.where(ShortsProject.promotion_purpose == goal)

    posts = list(db.scalars(statement.order_by(SnsPost.id.desc())))
    if not posts:
        return []

    values = latest_values(db, [post.id for post in posts])
    sample_size = len(posts)

    rows = []
    for post in posts:
        metrics = values.get(post.id, {})
        views = metrics.get(METRIC_VIEWS)
        days = days_since_posted(post)
        rows.append(
            (
                post,
                _rate(views, metrics.get(METRIC_REACH)),
                _rate(metrics.get(METRIC_SAVES), views),
                days,
                confidence_of(days, sample_size),
            )
        )
    # 비교 화면이므로 성과가 좋은 것부터 보여준다. 값이 없는 건 뒤로 민다.
    rows.sort(key=lambda row: (row[1] is None, -(row[1] or 0)))
    return rows


def _rate(numerator: Decimal | None, denominator: Decimal | None) -> Decimal | None:
    """비율을 계산한다. **분모가 없거나 0이면 `None`** — 0으로 채우지 않는다.

    `0.0`은 "비율이 0이었다"는 주장이고 `None`은 "계산할 수 없다"는 뜻이라 화면에서
    달리 표시돼야 한다(기능명세서 S17.2.1 "없는 지표는 N/A").
    """
    if numerator is None or not denominator:
        return None
    return round(numerator / denominator, 4)


def days_since_posted(post: SnsPost) -> int:
    """게시 후 경과일. `posted_at`이 아직 없으면 공유 시각(`created_at`)으로 센다.

    `posted_at`은 사장님이 게시물을 연결 확정(16.3)해야 채워지는데, 그전에도 성과
    화면은 열린다.
    """
    reference = post.posted_at or post.created_at
    return max((utcnow() - reference).days, 0)


def confidence_of(days: int, sample_size: int) -> str:
    """비교 결과를 얼마나 믿을 수 있는지.

    두 가지가 신뢰도를 떨어뜨린다.

    1. **표본이 적을 때** — 게시물이 3개 미만이면 무엇과 비교해도 의미가 없다
       (기능명세서 S17.3.1 "표본<3 신뢰도 낮음"). 이때는 경과일과 무관하게 전부 낮음이다.
    2. **게시한 지 얼마 안 됐을 때** — 지표가 아직 오르는 중이라 확정된 값이 아니다.
       일주일 된 영상과 한 달 된 영상을 같은 확신으로 비교할 수 없다.

    ⚠️ 경과일 구간(7일/30일)은 **백엔드가 정한 값**이다. 실제 데이터가 쌓이면
    조정이 필요할 수 있다.
    """
    if sample_size < MIN_SAMPLE_SIZE:
        return "낮음"
    for threshold, label in _CONFIDENCE_DAYS:
        if days < threshold:
            return label
    return "높음"
