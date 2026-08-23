"""요청/응답 스키마 공통 요소."""

from datetime import UTC, datetime
from decimal import Decimal
from typing import Annotated

from pydantic import BaseModel, ConfigDict, PlainSerializer


def _to_utc_iso(value: datetime) -> str:
    """API명세서의 시각 포맷(`YYYY-MM-DDTHH:mm:ssZ`)으로 직렬화한다.

    DB에는 naive UTC로 저장하므로(`app.models.mixins.utcnow`), 타임존이 없으면
    UTC로 간주한다.
    """
    if value.tzinfo is None:
        value = value.replace(tzinfo=UTC)
    return value.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


# 응답 스키마의 datetime 필드에 사용한다. 예: `created_at: UtcDatetime`
UtcDatetime = Annotated[datetime, PlainSerializer(_to_utc_iso, return_type=str)]

# 위경도 응답 필드에 사용한다. 예: `latitude: Coordinate | None`
#
# DB(`DECIMAL(10,7)`)와 계산은 Decimal로 하되 JSON에는 숫자로 내보낸다.
# Pydantic은 Decimal을 기본적으로 문자열("37.4995")로 직렬화하는데, API명세서 예시는
# 숫자(37.4995)이고 프론트도 그대로 지도 SDK에 넘기므로 float으로 바꿔서 내려준다.
# 소수점 7자리는 float64가 오차 없이 표현할 수 있는 범위다.
Coordinate = Annotated[Decimal, PlainSerializer(float, return_type=float)]


class BaseSchema(BaseModel):
    """모든 요청/응답 스키마의 부모.

    `from_attributes=True`라서 SQLAlchemy 모델 객체를 그대로 넘겨
    `Schema.model_validate(user)`로 변환할 수 있다.
    """

    model_config = ConfigDict(from_attributes=True)


class MessageResponse(BaseSchema):
    """성공 메시지만 돌려주는 응답(예: 로그아웃)."""

    message: str
