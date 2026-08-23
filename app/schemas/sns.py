"""SNS 연동·게시 스키마 (API명세서 16.1~16.3)."""

from datetime import datetime
from enum import StrEnum

from pydantic import Field

from app.models.sns import PostStatus
from app.schemas.common import BaseSchema, UtcDatetime


class SnsPlatform(StrEnum):
    """**연동** 가능한 플랫폼 (2026-08-24 확정).

    게시(16.2)는 NAVER Clip·TikTok도 지원하지만, 그 둘은 성과 지표를 가져올 API
    경로가 없어 연동 대상에서 제외했다.
    """

    INSTAGRAM = "INSTAGRAM"
    YOUTUBE = "YOUTUBE"


class PublishMode(StrEnum):
    # 사장님이 영상을 내려받아 앱에서 직접 올린다. 서버는 기록만 남긴다.
    HANDOFF = "HANDOFF"
    # 서버가 플랫폼 API로 대신 올린다. **플랫폼 앱 검수 통과 후에만 동작한다.**
    DIRECT = "DIRECT"


# ---------------------------------------------------------------- 16.1 연동


class ConnectionItem(BaseSchema):
    id: int
    sns_platform: str | None
    sns_account_name: str | None
    # 플랫폼이 만료를 안 알려주는 경우가 있어 null일 수 있다.
    token_expires_at: UtcDatetime | None


class ConnectionListResponse(BaseSchema):
    connections: list[ConnectionItem]


class AuthorizeResponse(BaseSchema):
    # 앱은 이 URL을 브라우저로 열기만 하면 된다. 내용을 알 필요가 없다.
    authorize_url: str


# ---------------------------------------------------------------- 16.2 게시


class PublishRequest(BaseSchema):
    # 게시는 연동보다 넓다 — NAVER Clip·TikTok도 기록할 수 있어야 해서 자유 문자열이다.
    platform: str = Field(min_length=1, max_length=30)
    publish_mode: PublishMode = PublishMode.HANDOFF
    sns_connection_id: int | None = None
    post_caption: str | None = None
    post_hashtags: str | None = Field(default=None, max_length=500)


class PublishResponse(BaseSchema):
    sns_post_id: int
    post_platform: str | None
    post_status: PostStatus
    created_at: UtcDatetime


# ---------------------------------------------------------------- 16.3 연결확정


class SnsPostResponse(BaseSchema):
    id: int
    post_platform: str | None
    post_status: PostStatus
    created_at: UtcDatetime


class SnsPostLinkRequest(BaseSchema):
    external_post_id: str = Field(min_length=1, max_length=100)
    # 생략하면 연결한 시각으로 둔다. 17.2의 "게시 후 경과일" 계산에 쓰인다.
    posted_at: datetime | None = None


class SnsPostLinkResponse(BaseSchema):
    id: int
    post_status: PostStatus
    external_post_id: str | None
    posted_at: UtcDatetime | None
