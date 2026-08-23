"""성과분석 요청/응답 스키마 (API명세서 17.1~17.2)."""

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
