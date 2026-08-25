"""숏폼 포맷 조회 로직 (API명세서 5.1~5.2)."""

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.exceptions import NotFoundError
from app.models.format_favorite import FormatFavorite
from app.models.user import User
from app.models.video_format import VideoFormat
from app.schemas.video_format import FormatSort, VideoFormatSummary

DEFAULT_PAGE_SIZE = 20
MAX_PAGE_SIZE = 100


class FormatNotFound(NotFoundError):
    error_code = "FORMAT_NOT_FOUND"
    message = "숏폼 포맷을 찾을 수 없습니다."


def list_formats(
    db: Session,
    format_type: str | None = None,
    face_exposure_level: str | None = None,
    keyword: str | None = None,
    sort: FormatSort = FormatSort.TRENDING,
    page: int = 1,
    size: int = DEFAULT_PAGE_SIZE,
) -> list[VideoFormat]:
    """포맷 목록을 조건에 맞춰 돌려준다.

    **`trending`은 AI 트렌드 클러스터 순위를 따른다**(`trend_rank`, 1이 가장 높음).
    순위가 없는 포맷(R06 추천으로 적재된 편집 템플릿 등)은 순위가 있는 것들 뒤로
    밀고 그 안에서는 최신순이다. `views`는 조회수 데이터가 아직 없어 최신순이다.

    **`is_active`인 것만 보여준다** — R06(숏폼 Agent)과 같은 카탈로그를 쓰기로
    확인됐고(2026-08-26), Agent 추천이 ACTIVE 템플릿으로 한정되므로 피드도 같은
    기준으로 맞춘다.
    """
    statement = select(VideoFormat).where(VideoFormat.is_active.is_(True))
    if format_type:
        statement = statement.where(VideoFormat.format_type == format_type)
    if face_exposure_level:
        statement = statement.where(VideoFormat.face_exposure_level == face_exposure_level)
    if keyword:
        statement = statement.where(VideoFormat.format_title.contains(keyword))

    size = min(max(size, 1), MAX_PAGE_SIZE)
    offset = max(page - 1, 0) * size
    latest = (VideoFormat.created_at.desc(), VideoFormat.id.desc())
    if sort is FormatSort.TRENDING:
        # `nulls_last()`는 MySQL 8이 지원하지 않는다. "NULL이냐"를 먼저 정렬하면
        # False(0)가 앞서므로 MySQL·SQLite 어디서나 같은 순서가 나온다.
        statement = statement.order_by(
            VideoFormat.trend_rank.is_(None), VideoFormat.trend_rank.asc(), *latest
        )
    else:
        statement = statement.order_by(*latest)
    return list(db.scalars(statement.offset(offset).limit(size)))


def get_format(db: Session, format_id: int) -> VideoFormat:
    video_format = db.get(VideoFormat, format_id)
    if video_format is None:
        raise FormatNotFound
    return video_format


def list_favorites(
    db: Session, user: User, page: int = 1, size: int = DEFAULT_PAGE_SIZE
) -> list[VideoFormat]:
    """찜한 포맷 목록. 최근 찜한 순으로 돌려준다 (API명세서 5.3)."""
    size = min(max(size, 1), MAX_PAGE_SIZE)
    offset = max(page - 1, 0) * size
    statement = (
        select(VideoFormat)
        .join(FormatFavorite, FormatFavorite.video_format_id == VideoFormat.id)
        .where(FormatFavorite.user_id == user.id)
        .order_by(FormatFavorite.created_at.desc(), FormatFavorite.id.desc())
    )
    return list(db.scalars(statement.offset(offset).limit(size)))


def add_favorite(db: Session, user: User, format_id: int) -> FormatFavorite:
    """포맷을 찜한다.

    **멱등이다** — 이미 찜한 포맷이면 기존 기록을 그대로 돌려준다. 하트를 빠르게
    여러 번 누르거나 네트워크가 재시도해도 409를 던지지 않는다. 이미 원하는 상태인
    요청을 에러로 볼 이유가 없다.
    """
    get_format(db, format_id)  # 없는 포맷이면 404

    existing = db.scalar(
        select(FormatFavorite).where(
            FormatFavorite.user_id == user.id, FormatFavorite.video_format_id == format_id
        )
    )
    if existing is not None:
        return existing

    favorite = FormatFavorite(user_id=user.id, video_format_id=format_id)
    db.add(favorite)
    db.commit()
    db.refresh(favorite)
    return favorite


def remove_favorite(db: Session, user: User, format_id: int) -> None:
    """찜을 해제한다. **찜하지 않은 포맷이어도 조용히 통과한다**(멱등)."""
    get_format(db, format_id)  # 없는 포맷이면 404

    favorite = db.scalar(
        select(FormatFavorite).where(
            FormatFavorite.user_id == user.id, FormatFavorite.video_format_id == format_id
        )
    )
    if favorite is not None:
        db.delete(favorite)
        db.commit()


def _favorite_ids(db: Session, user: User, formats: list[VideoFormat]) -> set[int]:
    """이 목록 중 사용자가 찜한 포맷 id들을 **한 번의 쿼리로** 가져온다.

    포맷마다 개별 조회하면 목록 크기만큼 쿼리가 나간다(N+1). 피드는 스크롤로
    계속 불리는 화면이라 여기서 새면 그대로 부하가 된다.
    """
    if not formats:
        return set()
    return set(
        db.scalars(
            select(FormatFavorite.video_format_id).where(
                FormatFavorite.user_id == user.id,
                FormatFavorite.video_format_id.in_([f.id for f in formats]),
            )
        )
    )


def build_recommendations(
    db: Session,
    user: User,
    formats: list[VideoFormat],
    project_id: int | None = None,
    favorites_only: bool = False,
) -> list[VideoFormatSummary]:
    """목록에 AI 추천 이유를 붙여 응답 형태로 만든다.

    **AI 연동 자리다.** 지금은 `recommend_reasons`를 빈 배열로 둔다. AI 서버가
    붙으면 이 함수만 바꾸면 되고 라우터·스키마는 그대로다 — 프로젝트 정보를
    AI에 넘겨 포맷별 추천 이유(기능명세서 S05.1.2는 최소 2개 요구)를 받아 채운다.

    `project_id`가 없을 수도 있다 — 홈 피드를 프로젝트 생성 전에 볼 수 있기 때문이며,
    그 경우 개인화 없이 일반 목록이 나간다(`docs/PM_DECISIONS.md` 「확인 대기 중」).
    """
    del project_id  # AI 연동 시 개인화 추천의 입력으로 사용한다

    # AI 연동 시 여기를 {format_id: ["이유1", "이유2"]}로 채우면 된다.
    reasons: dict[int, list[str]] = {}

    # 찜 목록(5.3)에서는 전부 찜한 것이므로 다시 조회하지 않는다.
    favorite_ids = {f.id for f in formats} if favorites_only else _favorite_ids(db, user, formats)

    return [
        VideoFormatSummary.model_validate(video_format).model_copy(
            update={
                "is_favorite": video_format.id in favorite_ids,
                "recommend_reasons": reasons.get(video_format.id, []),
            }
        )
        for video_format in formats
    ]


def is_favorite(db: Session, user: User, format_id: int) -> bool:
    """단건 조회(5.2)용 찜 여부."""
    return (
        db.scalar(
            select(FormatFavorite.id).where(
                FormatFavorite.user_id == user.id, FormatFavorite.video_format_id == format_id
            )
        )
        is not None
    )
