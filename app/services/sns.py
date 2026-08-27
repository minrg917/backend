"""SNS 연동·게시 로직 (API명세서 16.1 연동 / 16.2 게시 / 16.3 연결확정)."""

import logging
from datetime import datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.exceptions import BadRequestError, NotFoundError
from app.models.mixins import utcnow
from app.models.shorts_project import ShortsProject
from app.models.sns import PostStatus, SnsConnection, SnsPost
from app.models.store import Store
from app.models.user import User
from app.models.video_output import VideoOutput
from app.services import sns_oauth

logger = logging.getLogger("sarils.sns")


class ConnectionNotFound(NotFoundError):
    error_code = "SNS_CONNECTION_NOT_FOUND"
    message = "연동 정보를 찾을 수 없습니다."


class SnsPostNotFound(NotFoundError):
    error_code = "SNS_POST_NOT_FOUND"
    message = "게시물을 찾을 수 없습니다."


class OutputNotFound(NotFoundError):
    error_code = "OUTPUT_NOT_FOUND"
    message = "편집 결과를 찾을 수 없습니다."


class DirectPublishUnavailable(BadRequestError):
    """서버가 플랫폼에 대신 올리는 방식. **플랫폼 앱 검수를 통과해야 동작한다.**

    검수 전에 열어두면 사장님이 "게시하기"를 눌렀는데 아무 일도 일어나지 않고,
    본인은 올라간 줄 알게 된다. 그래서 시작 시점에 막는다.
    """

    error_code = "DIRECT_PUBLISH_UNAVAILABLE"
    message = "직접 게시는 아직 지원하지 않습니다. 영상을 내려받아 앱에서 올려주세요."


# ---------------------------------------------------------------- 16.1 연동


def list_connections(db: Session, user: User) -> list[SnsConnection]:
    return list(
        db.scalars(
            select(SnsConnection).where(SnsConnection.user_id == user.id).order_by(SnsConnection.id)
        )
    )


def get_owned_connection(db: Session, user: User, connection_id: int) -> SnsConnection:
    connection = db.get(SnsConnection, connection_id)
    if connection is None or connection.user_id != user.id:
        raise ConnectionNotFound
    return connection


def disconnect(db: Session, connection: SnsConnection) -> None:
    """연동을 지운다.

    **게시 이력(`sns_posts`)은 남긴다.** `sns_connection_id`가 `SET NULL`이라
    끊어지기만 한다 — 연동을 해제했다고 "이 영상을 올렸다"는 사실이 없어지는 건
    아니고, 성과 화면의 과거 기록도 유지돼야 한다.
    """
    db.delete(connection)
    db.commit()


def save_connection(
    db: Session, user_id: int, platform: str, tokens: sns_oauth.OAuthTokens
) -> SnsConnection:
    """콜백에서 받은 토큰을 저장한다.

    **같은 플랫폼을 다시 연동하면 기존 행을 갱신한다.** 새로 만들면 목록에 같은
    플랫폼이 여러 줄로 쌓이고, 어느 토큰을 써야 하는지 알 수 없어진다.
    (재연동은 토큰 만료·권한 철회 후 흔히 일어난다.)
    """
    connection = db.scalars(
        select(SnsConnection).where(
            SnsConnection.user_id == user_id, SnsConnection.sns_platform == platform
        )
    ).first()
    if connection is None:
        connection = SnsConnection(user_id=user_id, sns_platform=platform)
        db.add(connection)

    connection.access_token = tokens.access_token
    connection.refresh_token = tokens.refresh_token
    connection.token_expires_at = _expires_at(tokens.expires_in)
    if tokens.account_name:
        connection.sns_account_name = str(tokens.account_name)

    db.commit()
    db.refresh(connection)
    return connection


def _expires_at(expires_in: int | None) -> datetime | None:
    """만료까지 남은 초를 시각으로 바꾼다. 안 주는 플랫폼도 있어 `None`을 허용한다."""
    if not expires_in:
        return None
    return utcnow() + timedelta(seconds=expires_in)


# ---------------------------------------------------------------- 16.2 게시


def get_owned_output(db: Session, user: User, output_id: int) -> VideoOutput:
    """본인 가게의 산출물만 가져온다. 남의 것은 404."""
    output = db.scalars(
        select(VideoOutput)
        .join(ShortsProject, ShortsProject.id == VideoOutput.shorts_project_id)
        .join(Store, Store.id == ShortsProject.store_id)
        .where(VideoOutput.id == output_id, Store.user_id == user.id)
    ).first()
    if output is None:
        raise OutputNotFound
    return output


def publish(
    db: Session,
    user: User,
    output: VideoOutput,
    platform: str,
    publish_mode: str,
    connection_id: int | None,
    caption: str | None,
    hashtags: str | None,
) -> SnsPost:
    """게시 기록을 남긴다 (API명세서 16.2).

    **`HANDOFF`는 실제로 플랫폼에 올리지 않는다.** 사장님이 영상을 내려받아 인스타
    앱에서 직접 올리고, 서버는 "올렸다"는 사실만 기록한다. 그래서 상태가 항상
    `PENDING_LINK`로 시작한다 — 서버는 실제로 올라갔는지 확인할 방법이 없고,
    사장님이 16.3으로 게시물을 연결해줘야 `LINKED`가 된다.

    이 기록이 필요한 이유는 **성과 조회(17.x)의 출발점**이기 때문이다. 어떤 산출물이
    어느 플랫폼에 올라갔는지 알아야 그 게시물의 지표를 가져올 수 있다.
    """
    if publish_mode.upper() != "HANDOFF":
        raise DirectPublishUnavailable

    connection = (
        get_owned_connection(db, user, connection_id) if connection_id is not None else None
    )

    post = SnsPost(
        video_output_id=output.id,
        sns_connection_id=connection.id if connection else None,
        post_platform=platform,
        post_caption=caption,
        post_hashtags=hashtags,
        post_status=PostStatus.PENDING_LINK,
    )
    db.add(post)
    db.commit()
    db.refresh(post)
    return post


# ---------------------------------------------------------------- 16.3 연결확정


def get_owned_post(db: Session, user: User, post_id: int) -> SnsPost:
    """본인 가게의 게시물만 가져온다. 남의 것은 404(존재 자체를 숨긴다).

    소유권이 `sns_posts → video_outputs → store_shorts_projects → stores → users`로
    네 단계 떨어져 있어 조인으로 한 번에 확인한다.
    """
    post = db.scalars(
        select(SnsPost)
        .join(VideoOutput, VideoOutput.id == SnsPost.video_output_id)
        .join(ShortsProject, ShortsProject.id == VideoOutput.shorts_project_id)
        .join(Store, Store.id == ShortsProject.store_id)
        .where(SnsPost.id == post_id, Store.user_id == user.id)
    ).first()
    if post is None:
        raise SnsPostNotFound
    return post


def link_post(
    db: Session, post: SnsPost, external_post_id: str, posted_at: datetime | None
) -> SnsPost:
    """사장님이 알려준 실제 게시물과 연결한다 (API명세서 16.3).

    **이 연결이 성과 조회의 열쇠다.** 플랫폼 API로 지표를 가져오려면 "플랫폼상의
    게시물 ID"가 필요한데, 공유 핸드오프 방식에서는 서버가 그 값을 알 수 없다.
    사장님이 직접 알려줘야 한다.

    `posted_at`은 선택이다 — 안 주면 연결한 시각으로 둔다. 성과 비교(17.2)의
    "게시 후 경과일"에 쓰이므로 비워두면 신뢰도가 실제보다 낮게 잡힌다.

    **연결하자마자 지표를 한 번 즉시 당겨온다**(2026-08-27). 원래는 하루 한 번
    도는 배치(`sarils-metrics-collect.timer`)만 채웠는데, 그러면 연결 직후
    성과 화면이 최대 24시간 비어 보인다. 실패해도 무시한다 — 이건 부가 기능이고
    16.3 자체는 이미 성공했으니, 못 가져온 지표는 다음 배치가 채운다. 순환
    import(`sns.py` ↔ `metrics_collector.py`, 후자가 토큰 갱신에 `save_connection`을
    쓴다) 때문에 여기서 지연 임포트한다.
    """
    post.external_post_id = external_post_id
    post.posted_at = posted_at or utcnow()
    post.post_status = PostStatus.LINKED
    db.commit()
    db.refresh(post)

    from app.services import metrics_collector

    try:
        metrics_collector.collect_for_post(db, post)
    except Exception:
        logger.exception("연결확정 직후 즉시 지표 수집 실패 (post_id=%s)", post.id)

    return post
