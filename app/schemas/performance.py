"""성과분석 요청/응답 스키마 (API명세서 17.1~17.3)."""

from app.schemas.common import BaseSchema, MetricValue, UtcDatetime


class MetricItem(BaseSchema):
    metric_name: str
    metric_value: MetricValue | None
    collected_at: UtcDatetime


class MetricListResponse(BaseSchema):
    sns_post_id: int
    # 아직 수집된 게 없으면 빈 배열이다. 없는 지표를 0으로 채우지 않는다 —
    # 0은 "실제로 0이었다"는 주장이라 "아직 모른다"와 구분돼야 한다.
    metrics: list[MetricItem]


class ComparisonItem(BaseSchema):
    sns_post_id: int
    # 분모가 되는 지표(reach/views)가 없으면 null이다. 0이 아니다.
    view_rate: MetricValue | None
    save_rate: MetricValue | None
    days_since_posted: int
    # 낮음 / 보통 / 높음
    confidence: str


class ComparisonResponse(BaseSchema):
    comparison: list[ComparisonItem]


class PlatformWeeklyTotal(BaseSchema):
    platform: str
    # "이번 주 신규 증가분"의 합산이다 — 지금 시점 누적 총합이 아니다. 연결된
    # 게시물이 없어도 0이다(측정 불가라 N/A인 다른 지표들과 달리, 합산은 대상이
    # 없으면 진짜 0이 맞다).
    weekly_views: MetricValue
    weekly_likes: MetricValue


class WeeklySummaryResponse(BaseSchema):
    # 이번 주 시작(월요일 00:00 KST)
    week_start: UtcDatetime
    platforms: list[PlatformWeeklyTotal]
