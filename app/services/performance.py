"""성과분석 로직 (API명세서 17.1 성과지표 / 17.2 성과 비교 / 17.3 주간 총합 / 17.4 베스트 영상)."""

import random
from datetime import UTC, date, datetime, time, timedelta, timezone
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.mixins import utcnow
from app.models.shorts_project import ShortsProject
from app.models.sns import PostStatus, SnsPost, SnsPostMetric
from app.models.store import Store
from app.models.video_format import VideoFormat
from app.models.video_output import VideoOutput

# 비교·주간합산에 쓰는 지표 이름. 플랫폼마다 주는 이름이 달라도 수집 단계에서 이 이름으로 맞춘다.
METRIC_VIEWS = "views"
METRIC_LIKES = "likes"
METRIC_REACH = "reach"
METRIC_SAVES = "saves"

# 표본이 이보다 적으면 비교 자체를 신뢰할 수 없다 (기능명세서 S17.3.1 "표본<3 신뢰도 낮음").
MIN_SAMPLE_SIZE = 3

# 게시 직후에는 지표가 계속 오르는 중이라 확정된 값이 아니다.
_CONFIDENCE_DAYS = ((7, "낮음"), (30, "보통"))

# 17.3 주간 합산 대상 플랫폼·지표. 연동 자체가 이 둘만 지원된다(2026-08-24 확정).
_SUPPORTED_PLATFORMS = ("INSTAGRAM", "YOUTUBE")
_WEEKLY_METRICS = (METRIC_VIEWS, METRIC_LIKES)
_KST = timezone(timedelta(hours=9))


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


# ---------------------------------------------------------------- 17.3 주간 총합


def _week_start_utc(now: datetime) -> datetime:
    """이번 주 월요일 00:00(KST)을 naive UTC로 돌려준다.

    `collected_at`이 naive UTC로 저장돼 있어 비교 기준도 맞춰야 한다. KST로 계산하는
    이유는 "이번 주"가 사장님이 체감하는 한국 시간 기준 월요일이어야 하기 때문이다
    — UTC 그대로 쓰면 한국 시간 월요일 오전이 아직 "지난주 일요일"로 계산된다.
    """
    now_kst = now.replace(tzinfo=UTC).astimezone(_KST)
    monday_kst = (now_kst - timedelta(days=now_kst.weekday())).replace(
        hour=0, minute=0, second=0, microsecond=0
    )
    return monday_kst.astimezone(UTC).replace(tzinfo=None)


def _linked_post_ids(db: Session, store: Store, platform: str) -> list[int]:
    return list(
        db.scalars(
            select(SnsPost.id)
            .join(VideoOutput, VideoOutput.id == SnsPost.video_output_id)
            .join(ShortsProject, ShortsProject.id == VideoOutput.shorts_project_id)
            .where(
                ShortsProject.store_id == store.id,
                SnsPost.post_platform == platform,
                SnsPost.post_status == PostStatus.LINKED,
            )
        )
    )


def _values_before(
    db: Session, post_ids: list[int], before: datetime
) -> dict[int, dict[str, Decimal]]:
    """게시물별 지표의 `before` 이전 마지막 값. `latest_values`와 같은 방식에 상한만 둔다."""
    if not post_ids:
        return {}
    rows = db.scalars(
        select(SnsPostMetric)
        .where(SnsPostMetric.sns_post_id.in_(post_ids), SnsPostMetric.collected_at < before)
        .order_by(SnsPostMetric.collected_at, SnsPostMetric.id)
    )
    values: dict[int, dict[str, Decimal]] = {}
    for row in rows:
        if row.metric_value is None:
            continue
        values.setdefault(row.sns_post_id, {})[row.metric_name] = row.metric_value
    return values


def _kst_date(naive_utc: datetime) -> date:
    """naive UTC 시각을 KST 달력 날짜로 바꾼다.

    `week_start`(그리고 거기서 파생되는 요일별 경계)는 naive UTC로 저장돼 있는데,
    "월요일 00:00 KST"는 UTC로는 **일요일 15:00**이다. 여기서 `.date()`를 그냥
    부르면 하루 밀린 날짜(일요일)가 나온다 — 반드시 KST로 되돌린 뒤 날짜를 뽑아야
    한다.
    """
    return naive_utc.replace(tzinfo=UTC).astimezone(_KST).date()


def _window_total(
    db: Session, post_ids: list[int], metric: str, start: datetime, end: datetime
) -> Decimal:
    """`start` 이후 `end` 이전까지 새로 늘어난 양의 합. 17.3 본계산과 같은 델타 방식이다."""
    start_vals = _values_before(db, post_ids, start)
    end_vals = _values_before(db, post_ids, end)
    total = Decimal(0)
    for post_id in post_ids:
        v_end = end_vals.get(post_id, {}).get(metric, Decimal(0))
        v_start = start_vals.get(post_id, {}).get(metric, Decimal(0))
        total += max(v_end - v_start, Decimal(0))
    return total


def _views_change_rate(
    db: Session, post_ids: list[int], week_start: datetime, this_week_views: Decimal
) -> Decimal | None:
    """전주 대비 조회수 증감률(분수, 0.12 = +12%) (2026-08-28 추가).

    **전주 총합이 0이면 `None`이다** — 지난주에 활동이 아예 없었으면(포스팅이
    없었거나 있었어도 조회수가 0이었으면) "몇 % 늘었다"는 계산 자체가 무의미하다.
    0으로 나누는 것도 아니고, "0에서 얼마가 늘었다"는 숫자를 만들어내는 것도
    실제로 없던 기준선을 있는 척 지어내는 것과 같다.
    """
    last_week_start = week_start - timedelta(days=7)
    last_week_views = _window_total(db, post_ids, METRIC_VIEWS, last_week_start, week_start)
    if last_week_views == 0:
        return None
    return round((this_week_views - last_week_views) / last_week_views, 4)


def _has_collection_in_range(
    db: Session, post_ids: list[int], start: datetime, end: datetime
) -> bool:
    if not post_ids:
        return False
    return (
        db.scalar(
            select(SnsPostMetric.id)
            .where(
                SnsPostMetric.sns_post_id.in_(post_ids),
                SnsPostMetric.metric_name == METRIC_VIEWS,
                SnsPostMetric.collected_at >= start,
                SnsPostMetric.collected_at < end,
            )
            .limit(1)
        )
        is not None
    )


def _daily_views(
    db: Session, post_ids: list[int], week_start: datetime
) -> list[tuple[date, Decimal | None]]:
    """이번 주(월~일, KST) 요일별 조회수 순증가 추이 (2026-08-28 추가).

    **연동된 게시물 자체가 없으면 "잴 수 없다"가 아니라 "잴 대상이 없어 0"**이다
    (17.3 총합과 같은 구분) — 전부 `0`으로 채운다.

    게시물은 있는데 **그날 수집 기록이 하나도 없으면(수집 배치 장애 등) `0`이
    아니라 `None`**이다. 값이 안 바뀐 것(진짜 0)과 아예 재지 못한 것(모름)은
    다르다. 아직 지나지 않은 요일도 수집 기록이 없기는 마찬가지라 자연히
    `None`으로 나온다 — 미래를 특별 취급할 필요가 없다.
    """
    if not post_ids:
        return [(_kst_date(week_start + timedelta(days=i)), Decimal(0)) for i in range(7)]

    cutoffs = [week_start + timedelta(days=i) for i in range(8)]
    values_at_cutoff = [_values_before(db, post_ids, cutoff) for cutoff in cutoffs]

    points: list[tuple[date, Decimal | None]] = []
    for day in range(7):
        day_start, day_end = cutoffs[day], cutoffs[day + 1]
        if not _has_collection_in_range(db, post_ids, day_start, day_end):
            points.append((_kst_date(day_start), None))
            continue

        start_vals, end_vals = values_at_cutoff[day], values_at_cutoff[day + 1]
        total = Decimal(0)
        for post_id in post_ids:
            v_end = end_vals.get(post_id, {}).get(METRIC_VIEWS, Decimal(0))
            v_start = start_vals.get(post_id, {}).get(METRIC_VIEWS, Decimal(0))
            total += max(v_end - v_start, Decimal(0))
        points.append((_kst_date(day_start), total))
    return points


def weekly_summary(
    db: Session, store: Store
) -> tuple[
    datetime,
    list[tuple[str, Decimal, Decimal, Decimal | None, list[tuple[date, Decimal | None]]]],
]:
    """가게의 플랫폼별 "이번 주(월~일, KST) 신규 조회수·좋아요 합산"을 계산한다 (API명세서 17.3).

    **플랫폼 API는 영상 하나짜리 누적 총합만 준다** — "이번 주에 새로 늘어난 양"은
    직접 안 준다. 그래서 영상마다 (지금 누적 − 이번 주 시작 전 마지막 누적)으로
    이번 주 증가분을 구하고, 그 가게의 그 플랫폼 영상 전부를 더한다. 이번 주에
    새로 연결된 영상은 시작 전 값이 없으니 0으로 보고, 지금 누적값 전부가 그대로
    이번 주 증가분이 된다.

    단순히 지금 시점 누적 총합을 다 더하지 않는 이유는, 그러면 "이번 주"라는
    이름과 달리 오래된 영상의 평생 누적치까지 다 섞여 들어가기 때문이다.

    (이번 주 시작 시각, [플랫폼별 (플랫폼, 이번 주 총 조회수, 이번 주 총 좋아요,
    전주 대비 조회수 증감률, 요일별 조회수 추이)])를 돌려준다 — 연결된 게시물이
    없어도 총합은 0으로 채워 항상 두 플랫폼 다 나온다.
    """
    week_start = _week_start_utc(utcnow())
    results: list[
        tuple[str, Decimal, Decimal, Decimal | None, list[tuple[date, Decimal | None]]]
    ] = []
    for platform in _SUPPORTED_PLATFORMS:
        post_ids = _linked_post_ids(db, store, platform)
        latest = latest_values(db, post_ids)
        baseline = _values_before(db, post_ids, week_start)

        totals = dict.fromkeys(_WEEKLY_METRICS, Decimal(0))
        for post_id in post_ids:
            for metric in _WEEKLY_METRICS:
                latest_v = latest.get(post_id, {}).get(metric, Decimal(0))
                baseline_v = baseline.get(post_id, {}).get(metric, Decimal(0))
                totals[metric] += max(latest_v - baseline_v, Decimal(0))

        change_rate = _views_change_rate(db, post_ids, week_start, totals[METRIC_VIEWS])
        daily_views = _daily_views(db, post_ids, week_start)
        results.append(
            (platform, totals[METRIC_VIEWS], totals[METRIC_LIKES], change_rate, daily_views)
        )
    return week_start, results


# ---------------------------------------------------------------- 17.4 베스트 영상 · 다음 추천


def best_performing_post(db: Session, store: Store) -> tuple[SnsPost, Decimal, Decimal] | None:
    """가게가 지금까지 올린 영상 중 조회수가 가장 높은 것 하나를 고른다 (API명세서 17.4).

    17.2와 달리 플랫폼별 비율 정규화를 하지 않는다 — 이건 "가장 잘된 영상"을
    보여주는 하이라이트 카드지, 서로 다른 조건의 영상을 공정하게 줄 세우는
    비교가 아니다. 인스타/유튜브를 합쳐 조회수 절대값으로만 고른다.

    지표가 하나도 없으면(연동 전이거나 아직 수집 전) `None`이다 — 없는 걸
    있는 척 고를 수는 없다.

    (게시물, 조회수, 좋아요) 튜플을 돌려준다. 좋아요가 없는 플랫폼/영상이면 0이다.
    """
    post_ids: list[int] = []
    for platform in _SUPPORTED_PLATFORMS:
        post_ids.extend(_linked_post_ids(db, store, platform))
    if not post_ids:
        return None

    values = latest_values(db, post_ids)
    best_id: int | None = None
    best_views: Decimal | None = None
    for post_id, metrics in values.items():
        views = metrics.get(METRIC_VIEWS)
        if views is None:
            continue
        if best_views is None or views > best_views:
            best_id, best_views = post_id, views
    if best_id is None or best_views is None:
        return None

    post = db.get(SnsPost, best_id)
    assert post is not None
    likes = values[best_id].get(METRIC_LIKES, Decimal(0))
    return post, best_views, likes


def recommend_next_format(db: Session, store: Store, best_post: SnsPost) -> VideoFormat | None:
    """베스트 영상을 근거로 다음에 찍을 포맷 하나를 추천한다 (API명세서 17.4).

    **실제로는 데이터 기반 분석이 아니라 무작위 선택이다** — 기능명세서 F17.5가
    의도한 "성공 확장/약점 보완/새 실험" 3종 분석은 시간상 만들지 않기로
    했다(2026-08-28 결정). `best_post`가 있을 때만 부르는 게 전제다 — 근거
    영상이 없는데 "이 영상 기반 추천"이라는 문구만 붙일 수는 없어서다.

    **가게마다 고정된 시드로 고른다.** 매 조회마다 다른 게 나오면 추천처럼
    보이지 않는다 — 베스트 영상이 바뀌기 전까지는 같은 가게에 같은 값을 준다.
    베스트 영상을 만든 포맷 자체는 후보에서 뺀다 — "방금 그 영상 또 만드세요"가
    추천이 되진 않는다.
    """
    used_format_id = db.scalar(
        select(ShortsProject.video_format_id)
        .join(VideoOutput, VideoOutput.shorts_project_id == ShortsProject.id)
        .where(VideoOutput.id == best_post.video_output_id)
    )
    candidates = list(
        db.scalars(
            select(VideoFormat).where(VideoFormat.is_active.is_(True)).order_by(VideoFormat.id)
        )
    )
    pool = [f for f in candidates if f.id != used_format_id] or candidates
    if not pool:
        return None
    return random.Random(store.id).choice(pool)
