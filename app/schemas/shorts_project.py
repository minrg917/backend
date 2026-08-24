"""숏폼 프로젝트 스키마 (API명세서 4.1~4.3).

**`promotion_detail`의 구조는 `promotion_purpose`에 따라 4갈래로 갈린다.**
그런데 판별자인 `promotion_purpose`는 4.1(생성) 때 정해지고 4.2 요청에는 들어오지
않는다. 그래서 Pydantic의 discriminated union을 쓸 수 없고, 저장된 프로젝트를 읽어
그 목적에 맞는 스키마로 검증한다(`app/services/shorts_project.py`).

**목적은 생성 후 바꿀 수 없다**(2026-08-23 확정). 다른 목적으로 만들고 싶으면
프로젝트를 새로 만든다.

목적별 값 목록은 기획 확정 대기 중이다(`docs/PM_DECISIONS.md` 「확인 대기 중」).
확정되면 **값만 바뀌고 구조는 그대로**이므로, 값 정의를 이 파일 한곳에 모아둔다.
"""

from enum import StrEnum
from typing import Any

from pydantic import ConfigDict, Field

from app.models.shooting_task import FootageType, TaskStatus
from app.models.shorts_project import PromotionPurpose, ShortsStatus
from app.models.video_output import RenderStatus
from app.schemas.common import BaseSchema, UtcDatetime


class MenuDetailTag(StrEnum):
    """메뉴소개 세부 태그."""

    SIGNATURE = "대표메뉴"
    NEW = "신메뉴"
    COMPARE = "비교"
    PROCESS = "제조과정"
    HIDDEN = "숨은메뉴"


class StoreIntroElement(StrEnum):
    """가게소개 요소 (복수 선택)."""

    SPACE = "공간"
    LOCATION = "위치"
    SERVICE = "서비스경험"
    PEOPLE = "사장님/직원"
    VLOG = "하루브이로그"


class CustomerGoal(StrEnum):
    """고객늘리기 목표."""

    NEW = "신규고객"
    RETURN = "재방문"
    TIME_SLOT = "특정시간"
    RESERVATION = "예약공석"
    TRUST = "신뢰형성"


class _DetailBase(BaseSchema):
    """목적별 상세 스키마의 공통 설정.

    `extra="forbid"` — 명세서 4.2가 "목적에 맞지 않는 키를 보내면 400"이라고
    규정한다. 예컨대 가게소개 프로젝트에 `event_name`을 보내면 거부된다.
    """

    model_config = ConfigDict(from_attributes=True, extra="forbid")


class MenuPromotionDetail(_DetailBase):
    detail_tag: MenuDetailTag


class EventPromotionDetail(_DetailBase):
    event_name: str = Field(min_length=1, max_length=200)
    benefit: str | None = Field(default=None, max_length=200)
    period: str | None = Field(default=None, max_length=100)
    condition: str | None = Field(default=None, max_length=200)
    limit: str | None = Field(default=None, max_length=200)
    cta: str | None = Field(default=None, max_length=100)


class StorePromotionDetail(_DetailBase):
    elements: list[StoreIntroElement] = Field(min_length=1)


class CustomerPromotionDetail(_DetailBase):
    goal: CustomerGoal
    # 자유 입력으로 뒀으나 기획 의도가 선택지(enum)일 가능성이 있다
    # (`docs/PM_DECISIONS.md` 「확인 대기 중」). 확정되면 이 필드만 바꾸면 된다.
    success_metric: str | None = Field(default=None, max_length=200)


# 목적 → 상세 스키마. 서비스 계층이 이 표를 보고 검증할 스키마를 고른다.
PROMOTION_DETAIL_SCHEMAS: dict[PromotionPurpose, type[_DetailBase]] = {
    PromotionPurpose.MENU: MenuPromotionDetail,
    PromotionPurpose.EVENT: EventPromotionDetail,
    PromotionPurpose.STORE: StorePromotionDetail,
    PromotionPurpose.CUSTOMER: CustomerPromotionDetail,
}


# ---------------------------------------------------------------- 4.1 생성 / 목록


class ProjectCreateRequest(BaseSchema):
    store_id: int
    # 필수. 홈 피드 진입에도 목적 선택 화면을 두기로 확정(2026-08-23) — 잠시 선택으로
    # 풀었다가 되돌린 것이다. 응답·DB는 NULL을 허용한 채로 두는데, 완화 기간에 만들어진
    # 기존 row가 남아 있기 때문이다. 새로 만드는 것만 여기서 막는다.
    promotion_purpose: PromotionPurpose


class ProjectCreateResponse(BaseSchema):
    id: int
    store_id: int
    promotion_purpose: PromotionPurpose | None
    shorts_status: ShortsStatus
    created_at: UtcDatetime


class ProjectSummary(BaseSchema):
    id: int
    # 7.1 AI 기획 전에는 null이다. 이때 화면은 promotion_purpose를 라벨로 쓴다.
    project_title: str | None
    promotion_purpose: PromotionPurpose | None
    shorts_status: ShortsStatus
    updated_at: UtcDatetime


class ProjectListResponse(BaseSchema):
    projects: list[ProjectSummary]


# ---------------------------------------------------------------- 4.2 설정 수정


class ProjectUpdateRequest(BaseSchema):
    """프로젝트 설정 부분 수정.

    `promotion_detail`은 여기서 `dict`로만 받고, 실제 구조 검증은 서비스 계층이
    저장된 `promotion_purpose`를 보고 수행한다 — 이 스키마 시점에는 어떤 목적인지
    알 수 없기 때문이다.
    """

    menu_id: int | None = None
    promotion_detail: dict[str, Any] | None = None
    store_target_customer_id: int | None = None
    face_exposure_mode: str | None = Field(default=None, max_length=20)
    shooting_condition: str | None = None


class ProjectSettingsResponse(BaseSchema):
    """4.2 응답 — 바꾼 필드만이 아니라 **설정 필드 전체**를 돌려준다.

    3.1/3.2/3.4의 PATCH와 다르다. 명세서 4.2 응답 예시가 요청에 없던
    `promotion_purpose`까지 포함하고 있어 전체 설정을 보여주는 형태다.
    """

    id: int
    menu_id: int | None
    promotion_purpose: PromotionPurpose | None
    promotion_detail: dict[str, Any] | None
    store_target_customer_id: int | None
    face_exposure_mode: str | None
    shooting_condition: str | None
    updated_at: UtcDatetime


# ---------------------------------------------------------------- 4.3 단건 조회


class ProjectDetailResponse(BaseSchema):
    id: int
    store_id: int
    project_title: str | None
    video_format_id: int | None
    store_target_customer_id: int | None
    menu_id: int | None
    promotion_purpose: PromotionPurpose | None
    promotion_detail: dict[str, Any] | None
    face_exposure_mode: str | None
    shooting_condition: str | None
    shorts_status: ShortsStatus
    created_at: UtcDatetime
    updated_at: UtcDatetime


# ---------------------------------------------------------------- 7.1 기획 생성


class PlanCreateRequest(BaseSchema):
    video_format_id: int


class ShootingSummary(BaseSchema):
    """촬영 준비 요약 (기능명세서 S07.5.1, `#/project/:id/prep` 화면).

    ⚠️ `expected_duration_sec`은 **예상 촬영 소요시간**이다. 5.1·5.2의 같은 이름
    필드(**완성 영상 길이**)와 뜻이 다르다. DB에는 `estimated_shooting_sec`으로
    구분해 저장하며 여기서만 명세서 필드명에 맞춘다.
    """

    expected_duration_sec: int | None
    required_people: int | None
    props: list[str]
    difficulty: str | None


class ScenePreview(BaseSchema):
    """7.1 응답의 장면 미리보기.

    `#/project/:id/plan`에서 대사를 바로 확인·수정할 수 있어야 해서 `id`와
    `scene_dialogue`를 포함한다. 자막은 콘티 화면(7.2) 몫이라 제외한다.
    """

    id: int
    scene_order: int
    scene_description: str | None
    scene_dialogue: str | None
    target_duration_sec: int | None


class PlanResponse(BaseSchema):
    shooting_summary: ShootingSummary
    scenes_preview: list[ScenePreview]


# ---------------------------------------------------------------- 7.2 콘티


class SceneResponse(BaseSchema):
    id: int
    scene_order: int
    scene_description: str | None
    scene_dialogue: str | None
    scene_subtitle: str | None
    shot_type: str | None
    target_duration_sec: int | None


class SceneListResponse(BaseSchema):
    # 7.1을 호출한 적 없으면 null이다
    shooting_summary: ShootingSummary | None
    scenes: list[SceneResponse]


class SceneUpdateItem(BaseSchema):
    """수정할 장면 하나. `id` 외에는 보낸 필드만 반영된다."""

    id: int
    scene_description: str | None = None
    scene_dialogue: str | None = None
    scene_subtitle: str | None = None
    shot_type: str | None = Field(default=None, max_length=50)
    target_duration_sec: int | None = Field(default=None, ge=0)


class SceneUpdateRequest(BaseSchema):
    scenes: list[SceneUpdateItem] = Field(min_length=1)


class SceneUpdateResponse(BaseSchema):
    message: str
    updated_count: int


# ---------------------------------------------------------------- 8.1 / 8.2 촬영 태스크


class TaskSummary(BaseSchema):
    id: int
    scene_id: int | None
    task_type: str | None
    task_title: str | None
    task_status: TaskStatus
    display_order: int


class TaskBoardResponse(BaseSchema):
    """태스크 보드 (API명세서 8.1)."""

    progress_rate: int
    # 7.1을 호출한 적 없거나 태스크가 없으면 null
    estimated_remaining_min: int | None
    tasks: list[TaskSummary]


class TaskStatusUpdateRequest(BaseSchema):
    task_status: TaskStatus


class TaskStatusUpdateResponse(BaseSchema):
    id: int
    task_status: TaskStatus
    updated_at: UtcDatetime


# ---------------------------------------------------------------- 9.1 촬영 가이드


class GuideType(StrEnum):
    OVERLAY = "OVERLAY"
    DANCE = "DANCE"
    BROLL = "BROLL"


class OverlayGuide(BaseSchema):
    # AI 연동 전까지 빈 배열이다 — 지어내면 가짜 안내가 진짜처럼 보인다
    instructions: list[str]


class ReferenceVideo(BaseSchema):
    """댄스·안무 가이드용 원본 영상.

    포맷 하나당 하나이므로 태스크별로 저장하지 않고 `video_formats`에서 가져온다
    (`docs/PM_DECISIONS.md` 2026-08-21 R10 항목).
    """

    reference_url: str
    source_platform: str | None


class BrollShot(BaseSchema):
    # shot_type은 storyboard_scenes에서 가져온다(태스크에 중복 저장하지 않는다)
    shot_type: str | None
    distance: str | None
    angle: str | None


class TaskGuideResponse(BaseSchema):
    guide_type: GuideType
    overlay: OverlayGuide | None
    reference_video: ReferenceVideo | None
    broll_shot: BrollShot | None


# ---------------------------------------------------------------- 9.2 촬영본 업로드


class FootageUploadResponse(BaseSchema):
    task_id: int
    file_url: str
    footage_type: FootageType
    footage_duration_sec: int | None
    task_status: TaskStatus


# ---------------------------------------------------------------- 9.3 자동저장


class DraftResponse(BaseSchema):
    project_id: int
    # 한 번도 저장한 적 없으면 둘 다 null
    last_saved_at: UtcDatetime | None
    current_step: str | None


class DraftSaveRequest(BaseSchema):
    current_step: str | None = Field(default=None, max_length=30)
    # 서버는 내용을 해석하지 않고 그대로 보관했다 돌려준다
    client_state: dict[str, Any] | None = None


class DraftSaveResponse(BaseSchema):
    message: str
    last_saved_at: UtcDatetime


# ---------------------------------------------------------------- 14. AI 자동편집


class EditStartRequest(BaseSchema):
    target_platform: str = Field(min_length=1, max_length=50)


class EditStartResponse(BaseSchema):
    video_output_id: int
    render_status: RenderStatus


class TimelineItem(BaseSchema):
    scene_order: int
    duration_sec: int | None
    # 전환 효과는 AI 편집 레시피에서 나온다 — 연동 전까지 null
    effect: str | None


class EditResultResponse(BaseSchema):
    video_output_id: int
    render_status: RenderStatus
    # ⚠️ 실제 렌더링 진행률이 아니라 상태에서 매핑한 근사값이다
    progress_percent: int
    preview_video_url: str | None
    timeline_summary: list[TimelineItem]
    # render_status가 SOURCE_GAP일 때만 채워진다(`docs/AI_연동_입출력.md` 21번).
    # 그 외에는 항상 null이다.
    missing_scene_roles: list[str] | None = None
    available_options: list[str] | None = None


class ReviseRequestType(StrEnum):
    QUICK_BUTTON = "quick_button"
    NATURAL_LANGUAGE = "natural_language"


class EditReviseRequest(BaseSchema):
    request_type: ReviseRequestType
    action: str = Field(min_length=1, max_length=500)


class EditReviseResponse(BaseSchema):
    video_output_id: int
    render_status: RenderStatus
    # 프로젝트 내 산출물 순번 — 저장하지 않고 계산한다
    revision_id: int


# ---------------------------------------------------------------- 15.1 최종 출력·게시자료


class OutputCreateRequest(BaseSchema):
    target_platforms: list[str] = Field(min_length=1)


class OutputItem(BaseSchema):
    id: int
    target_platform: str | None
    resolution: str | None
    has_licensed_audio: bool | None
    render_status: RenderStatus
    video_url: str | None
    cover_image_url: str | None


class AudioMode(StrEnum):
    """음원이 포맷에 고정돼 있는지 여부.

    챌린지형(`FIXED`)은 그 곡이 곧 챌린지의 정체성이라 바꾸면 안 된다.
    일반형(`SUGGESTED`)은 분위기만 맞으면 사장님이 자유롭게 고른다.
    """

    FIXED = "FIXED"
    SUGGESTED = "SUGGESTED"


class TrackInfo(BaseSchema):
    """음원 가이드 (API명세서 15.1).

    **저작권 때문에 배경음악을 영상에 직접 입히지 않는다**(2026-08-24 결정). 플랫폼
    음원 라이선스는 그 플랫폼 안에서만 유효하기 때문이다. 대신 사장님이 인스타그램·
    틱톡에서 직접 붙이도록 "무슨 곡을, 어디부터" 알려주는 게 이 필드다.

    `start_sec`은 **원곡에서의 위치**다. 원곡 3분 중 챌린지가 쓰는 건 후렴 15초라,
    사장님이 슬라이더를 그 지점으로 밀지 않으면 인트로만 깔려 전혀 다른 영상이 된다.
    """

    mode: AudioMode
    # FIXED에서만 채워진다. 사장님이 플랫폼에서 검색할 값이라 지어내면 안 된다.
    title: str | None = None
    artist: str | None = None
    start_sec: int | None = None
    # 저장하지 않고 start_sec + 포맷의 완성 영상 길이로 계산한다 —
    # 두 값을 따로 저장하면 어긋났을 때 어느 쪽이 맞는지 알 수 없다.
    end_sec: int | None = None
    # SUGGESTED에서만 채워진다. 예: "잔잔하고 따뜻한 어쿠스틱"
    mood: str | None = None


class PublishKit(BaseSchema):
    caption: str
    hashtags: list[str]
    post_note: str | None = None
    # 포맷에 음원 정보가 없으면 null이다. 프론트는 이때 음원 카드를 숨긴다.
    track: TrackInfo | None = None


class OutputListResponse(BaseSchema):
    outputs: list[OutputItem]
    # 아직 15.1 POST를 호출하지 않았으면 null이다
    publish_kit: PublishKit | None
