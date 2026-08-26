"""편집 완료 푸시 알림용 디바이스 토큰 등록 스키마."""

from pydantic import Field

from app.models.push_token import PushPlatform
from app.schemas.common import BaseSchema


class PushTokenRegisterRequest(BaseSchema):
    push_token: str = Field(min_length=1, max_length=255)
    platform: PushPlatform
