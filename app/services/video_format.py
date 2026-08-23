"""숏폼 포맷 조회 로직 (API명세서 5.1~5.2)."""

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.exceptions import NotFoundError
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

    **정렬은 현재 전부 최신순이다.** 인기·급상승 랭킹은 AI 서버가 포맷 목록과 함께
    내려줄 예정이라 우리 DB에는 조회수 데이터가 없다. 파라미터는 계약대로 받아두고
    AI 연동 시 순서만 교체한다.
    """
    del sort  # 랭킹 데이터가 생기기 전까지는 정렬 기준을 구분하지 않는다

    statement = select(VideoFormat)
    if format_type:
        statement = statement.where(VideoFormat.format_type == format_type)
    if face_exposure_level:
        statement = statement.where(VideoFormat.face_exposure_level == face_exposure_level)
    if keyword:
        statement = statement.where(VideoFormat.format_title.contains(keyword))

    size = min(max(size, 1), MAX_PAGE_SIZE)
    offset = max(page - 1, 0) * size
    statement = statement.order_by(VideoFormat.created_at.desc(), VideoFormat.id.desc())
    return list(db.scalars(statement.offset(offset).limit(size)))


def get_format(db: Session, format_id: int) -> VideoFormat:
    video_format = db.get(VideoFormat, format_id)
    if video_format is None:
        raise FormatNotFound
    return video_format


def build_recommendations(
    formats: list[VideoFormat], project_id: int | None = None
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

    return [
        VideoFormatSummary.model_validate(video_format).model_copy(
            update={"recommend_reasons": reasons.get(video_format.id, [])}
        )
        for video_format in formats
    ]
