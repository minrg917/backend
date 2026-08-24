"""AI 서버 호출 어댑터.

**AI 팀에서 만드는 별도 서버를 부르는 자리다.** 아직 스펙이 나오지 않아
임시 구현(`_placeholder_plan`)이 들어 있고, 스펙이 확정되면 이 파일만 채우면 된다.
호출부(`app/services/plan.py`)와 라우터는 바뀌지 않는다.

외부 검색을 `store_search.py`로 분리한 것과 같은 이유다.

- **테스트 목킹**: CI에 AI 서버가 없으므로 경계가 없으면 테스트를 못 돌린다.
- **실패 격리**: AI가 죽어도 앱이 통째로 죽지 않게 한다.
- **교체 용이**: 동기/비동기 전환도 여기만 바꾸면 된다.

AI는 **콘티(`scenes`)와 촬영 태스크(`tasks`)를 함께** 내려준다(2026-08-23 확정).
태스크를 만드는 별도 API는 없고 7.1이 둘 다 생성한다.

⚠️ **임시 결과는 진짜 기획이 아니다.** 포맷·가게에 상관없이 같은 뼈대를 돌려주며,
`is_placeholder=True`로 표시된다. 화면에서 "AI 준비 중"을 안내하는 데 쓸 수 있다.
"""

import uuid
from dataclasses import dataclass, field
from typing import Any

from app.core.config import settings
from app.models.shorts_project import ShortsProject
from app.models.store import Store
from app.models.store_menu import StoreMenu
from app.models.video_format import VideoFormat


@dataclass(frozen=True)
class PlannedScene:
    """AI가 만든 장면 하나."""

    scene_order: int
    scene_description: str
    scene_dialogue: str | None = None
    scene_subtitle: str | None = None
    shot_type: str | None = None
    target_duration_sec: int | None = None


@dataclass(frozen=True)
class PlannedTask:
    """AI가 쪼갠 촬영 태스크 하나 (기능명세서 S08.1.1).

    `scene_index`는 `ShootingPlan.scenes`의 몇 번째 장면에서 나온 태스크인지를
    가리킨다. 장면이 아직 DB에 저장되기 전이라 실제 `scene_id`를 알 수 없어,
    저장 시점에 호출부가 매핑한다.
    """

    display_order: int
    task_title: str
    task_type: str | None = None
    scene_index: int | None = None
    # 촬영 안내 (9.1). guide_type / instructions / broll_shot 를 담는다.
    guide: dict[str, Any] | None = None


@dataclass(frozen=True)
class ShootingGuide:
    """영상편집템플릿에 고정된 촬영 가이드 (`docs/AI_연동_입출력.md` 13번).

    7.1(`POST /shorts-projects/{projectId}/plan`)과 6.4(추천 수락)가 둘 다
    `app/services/plan.py::generate_plan()`을 통해 이 값을 쓴다(2026-08-26 결정 —
    "기존 방식 사용 안 함"이라는 AI팀 지침에 따라 7.1의 AI 호출 자체를 이걸로
    교체했다). **매번 새로 만드는 게 아니라 템플릿에 저장된 값을 그대로 반환**하는
    조회이므로, 구 `ShootingPlan`과 달리 `project_title`이 없다 — 제목은 R06의
    추천(`accept` 시점)에서만 나온다(`docs/AI_연동_입출력.md` 23번).

    `required_people`·`props`는 **영상편집템플릿의 고정 메타데이터**다(2026-08-26
    AI팀 확인) — 사용자 입력값이 아니고, 프로젝트 생성 단계에서 따로 받지 않는다.
    """

    estimated_shooting_sec: int | None = None
    required_people: int | None = None
    props: list[str] = field(default_factory=list)
    difficulty: str | None = None
    scenes: list[PlannedScene] = field(default_factory=list)
    tasks: list[PlannedTask] = field(default_factory=list)
    # 실제 AI가 만든 결과가 아니라 임시 뼈대라는 표시
    is_placeholder: bool = False


def is_enabled() -> bool:
    """AI 서버가 설정돼 있는지."""
    return bool(settings.AI_SERVER_URL)


def get_shooting_guide(
    video_format: VideoFormat, store: Store, project: ShortsProject
) -> ShootingGuide:
    """포맷(영상편집템플릿)에 고정된 촬영 가이드를 가져온다.

    2026-08-26 AI팀 확인: **세션 없이 `template_id`+`version`만으로 호출 가능**하되,
    "가게/프로젝트에 필요한 컨텍스트"도 함께 넘기는 구조로 설계하라고 했다 — 그래서
    `store`·`project`를 받는다. 다만 가이드 **내용 자체는 템플릿에 고정**돼 있어
    (`docs/AI_연동_입출력.md` 13번 "LLM이 매 요청마다 생성하지 않는다") 이 컨텍스트가
    응답을 바꾸지는 않을 것으로 보인다 — 로깅/권한 확인 등에 쓰일 가능성이 높지만
    확정은 아니다.

    AI 서버가 설정돼 있지 않으면 임시 뼈대를 돌려준다 — 연동 전에도 화면 흐름을
    끝까지 확인할 수 있어야 하고, CI에서도 테스트가 돌아야 한다.
    """
    if not is_enabled():
        return _placeholder_shooting_guide(video_format)

    del store, project  # 실제 연동 시 요청 컨텍스트로 쓴다 — 정확한 용도는 미확정
    if video_format.editing_template_id is None or video_format.editing_template_version is None:
        # 5.1과 R06은 같은 템플릿 카탈로그를 쓰기로 확인됐다(2026-08-26). 그런데도
        # 이 값이 없다면 5.1이 옛(레거시) 방식으로 적재된 행이라는 뜻이다.
        raise NotImplementedError(
            "이 포맷은 영상편집템플릿과 연결되어 있지 않습니다(editing_template_id 없음)."
        )

    # AI 스펙 확정 후: GET /api/v1/editing-templates/{id}/versions/{version}/shooting-guide
    raise NotImplementedError("AI 서버 연동은 스펙 확정 후 구현합니다.")


def _placeholder_shooting_guide(video_format: VideoFormat) -> ShootingGuide:
    """AI 연동 전 임시 촬영 가이드.

    포맷의 촬영 컷 구성을 흉내 낸 뼈대만 만든다. **가게별 맞춤이 아니다** — 실제
    응답도 템플릿 고정값이라 가게별로 다르지 않으므로, 이 부분은 실제 동작과
    형태가 같다(내용만 가짜).
    """
    duration = video_format.expected_duration_sec or 30
    per_scene = max(duration // 4, 3)

    scenes = [
        PlannedScene(
            scene_order=1,
            scene_description="간판 클로즈업",
            scene_subtitle="이 가게만의 특별한 순간",
            shot_type="클로즈업",
            target_duration_sec=per_scene,
        ),
        PlannedScene(
            scene_order=2,
            scene_description="대상 준비 장면",
            shot_type="미디엄샷",
            target_duration_sec=per_scene,
        ),
        PlannedScene(
            scene_order=3,
            scene_description="핵심 장면",
            shot_type="클로즈업",
            target_duration_sec=per_scene,
        ),
        PlannedScene(
            scene_order=4,
            scene_description="마무리 리액션",
            scene_subtitle="지금 보러 오세요!",
            shot_type="풀샷",
            target_duration_sec=duration - per_scene * 3,
        ),
    ]
    # 임시 태스크는 장면 하나당 하나로 만든다. 실제로는 AI가 "영상촬영 / 대사 /
    # B-roll / 텍스트 확인" 같은 유형으로 쪼갠다(기능명세서 S08.1.1).
    tasks = [
        PlannedTask(
            display_order=scene.scene_order,
            task_title=f"{scene.scene_description} 촬영",
            task_type="영상촬영",
            scene_index=index,
            guide={
                "guide_type": "OVERLAY",
                # ⚠️ 비워둔다. AI 없이 지어내면 가짜 안내가 진짜처럼 보인다.
                "instructions": [],
                "broll_shot": {"distance": None, "angle": None},
            },
        )
        for index, scene in enumerate(scenes)
    ]

    return ShootingGuide(
        # 촬영은 완성 길이보다 오래 걸린다는 가정. 실제 값은 AI가 판단한다.
        estimated_shooting_sec=duration * 10,
        required_people=1,
        props=["삼각대"],
        difficulty=video_format.shooting_difficulty,
        scenes=scenes,
        tasks=tasks,
        is_placeholder=True,
    )


@dataclass(frozen=True)
class PublishKit:
    """게시자료 (API명세서 15.1).

    사장님이 SNS에 올릴 때 그대로 붙여넣을 캡션·해시태그와, 음원 선택 같은
    플랫폼 안내 문구를 담는다. `EditingRunResult.publishing`도 같은 모양을
    쓰므로 여기(먼저 나오는 자리)에 정의한다 — placeholder 전용이 된 경위는
    `generate_publish_kit()` 독스트링 참고.
    """

    caption: str
    hashtags: list[str]
    post_note: str | None = None
    # 음원 가이드. 저작권 때문에 배경음악을 직접 입히지 않고, 사장님이 플랫폼에서
    # 붙이도록 "무슨 곡을 어디부터" 알려준다(2026-08-24 결정).
    # 값의 출처는 미정이다 — 포맷에 고정해둘지 AI가 영상을 보고 채울지 확인 중이라
    # 지금은 항상 None이며, 정해지면 이 자리에 담는다.
    track: dict[str, Any] | None = None
    is_placeholder: bool = False


@dataclass(frozen=True)
class FootageInput:
    """편집 Agent에 보낼 촬영본 하나 (`docs/AI_연동_입출력.md` 16번 `videos[]`)."""

    video_id: str
    footage_url: str
    shooting_scene_order: int | None = None


@dataclass(frozen=True)
class EditingRun:
    """편집 실행(run) 식별자와 상태 (16·17·20번).

    `status`는 AI가 쓰는 문자열(`QUEUED`/`RUNNING`/`COMPLETED`/`FAILED`/
    `SOURCE_GAP`)을 그대로 담는다 — `app/services/video_edit.py`가 우리
    `RenderStatus`로 옮긴다.
    """

    run_id: str
    status: str


@dataclass(frozen=True)
class EditingRunResult:
    """완료된 편집 결과 (18번 `GET /editing-runs/{run_id}/result`).

    `recipe`는 자유 형식 JSON이라 그대로 보관한다(기능명세서 S14.x가 요구하는
    컷 순서·전환·자막·오디오 큐가 여기 들어있다). `SOURCE_GAP`이면 `recipe`·
    `video_url` 등은 비고 `missing_scene_roles`·`available_options`만 채워진다.

    `publishing`은 22번("게시자료는 편집 결과에 포함된다")에 대응한다 — 15.1
    전용 AI 호출이 따로 없다. `PublishKit`과 같은 필드를 쓰지만 이름을 분리했다
    (`PublishKit`은 placeholder 전용으로 남았다).
    """

    recipe: dict[str, Any] | None = None
    video_url: str | None = None
    resolution: str | None = None
    cover_image_url: str | None = None
    publishing: PublishKit | None = None
    missing_scene_roles: list[str] | None = None
    available_options: list[str] | None = None
    is_placeholder: bool = False


def start_editing_run(
    store: Store, project: ShortsProject, footages: list[FootageInput]
) -> EditingRun:
    """편집을 시작한다 (`docs/AI_연동_입출력.md` 16번, `POST /editing-runs`).

    **비동기다.** 실제 연동 후에는 이 호출이 `run_id`만 즉시 돌려주고, 진행 상태는
    `get_editing_run()`으로 폴링한다(17번). placeholder는 **영원히 `QUEUED`에
    머문다** — 렌더러가 없어 실제 영상이 생기지 않는데 `COMPLETED`로 표시하면
    재생되지 않는 가짜 영상 링크를 사장님이 보게 된다. 다른 placeholder(캡션·
    콘티 등, 텍스트/구조만 있는 값)와 달리 **영상 파일은 지어낼 수 없는 종류의
    값**이라 여기서는 원칙이 다르다.
    """
    if not is_enabled():
        return _placeholder_editing_run()

    # 실제 연동 시 요청 본문(project/selected_shortform/videos)을 구성하는 데 쓴다
    del store, project, footages
    # AI 스펙 확정 후: POST /api/v1/editing-runs
    raise NotImplementedError("AI 서버 연동은 스펙 확정 후 구현합니다.")


def _placeholder_editing_run() -> EditingRun:
    return EditingRun(run_id=f"edit_placeholder_{uuid.uuid4().hex}", status="QUEUED")


def get_editing_run(run_id: str) -> EditingRun:
    """편집 진행 상태를 폴링한다 (17번, `GET /editing-runs/{run_id}`).

    placeholder는 **처음 만들어졌을 때 상태에 계속 머문다** — 진행이 없어서다.
    수정 요청(`request_revision`)이 만든 run인지는 `run_id` 접두어로 구분한다 —
    별도 상태 저장소가 없는 placeholder 안에서 "이 run이 어떤 종류였는지"를
    유지하는 유일한 방법이다.
    """
    if not is_enabled():
        status = "RUNNING" if run_id.startswith("edit_revision_placeholder_") else "QUEUED"
        return EditingRun(run_id=run_id, status=status)

    # AI 스펙 확정 후: GET /api/v1/editing-runs/{run_id}
    raise NotImplementedError("AI 서버 연동은 스펙 확정 후 구현합니다.")


def get_editing_run_result(run_id: str) -> EditingRunResult:
    """완료된 편집 결과를 가져온다 (18번).

    placeholder는 절대 `COMPLETED`가 되지 않으므로(`get_editing_run` 참고) 이
    함수가 호출될 일이 없다 — 호출되면 프로그래밍 오류다.
    """
    if not is_enabled():
        raise NotImplementedError("AI 연동 전에는 편집이 완료되지 않아 결과를 조회할 수 없습니다.")

    del run_id
    # AI 스펙 확정 후: GET /api/v1/editing-runs/{run_id}/result
    raise NotImplementedError("AI 서버 연동은 스펙 확정 후 구현합니다.")


def request_revision(run_id: str, revision_action: str) -> EditingRun:
    """수정을 요청한다 (20번, `POST /editing-runs/{run_id}/revisions`).

    **새 run을 만든다** — 기존 EditRecipe는 immutable하게 유지된다. placeholder는
    바로 `RUNNING`으로 표시한다(기존 동작 유지 — 수정 요청은 "처리 중"으로 보여야
    사장님이 재요청 중임을 알 수 있다). 완료되진 않는다(위와 같은 이유).
    """
    if not is_enabled():
        del run_id, revision_action
        return EditingRun(run_id=f"edit_revision_placeholder_{uuid.uuid4().hex}", status="RUNNING")

    # AI 스펙 확정 후: POST /api/v1/editing-runs/{run_id}/revisions
    raise NotImplementedError("AI 서버 연동은 스펙 확정 후 구현합니다.")


def generate_publish_kit(store: Store, project: ShortsProject) -> PublishKit:
    """게시자료를 만든다. **placeholder 전용**이다.

    ⚠️ **2026-08-26부터 실제 연동 시에는 이 함수를 쓰지 않는다.** AI 문서 22번이
    "게시자료는 별도 LLM 호출이 없고, 편집 결과(`get_editing_run_result`)의
    `publishing`에 포함된다"고 확정해서다. `is_enabled()`가 `true`면
    `app/services/video_output.py`가 이 함수를 아예 부르지 않고
    `project.publish_kit`(편집 완료 시 채워짐)을 그대로 돌려줘야 한다 — 그래도
    부르면 아래에서 프로그래밍 오류로 막는다.

    **placeholder 모드에서는 계속 이 함수를 쓴다** — 렌더링이 영원히 끝나지
    않는 placeholder 편집(`start_editing_run` 참고)과 달리, 캡션·해시태그는
    문구일 뿐이라 안전하게 지어낼 수 있다. 렌더링 완료를 기다리지 않고도
    프론트가 15.1 화면 흐름을 확인할 수 있게 하려는 의도적인 예외다.
    """
    if not is_enabled():
        return _placeholder_publish_kit(store)

    raise NotImplementedError(
        "AI 연동 후에는 게시자료를 여기서 만들지 않습니다 — "
        "get_editing_run_result().publishing을 쓰세요."
    )


def _placeholder_publish_kit(store: Store) -> PublishKit:
    """AI 연동 전 임시 게시자료.

    **문구를 지어내지 않는다.** 가게 이름·업종처럼 DB에 실제로 있는 값만 쓴다 —
    사장님이 그대로 게시할 수 있는 화면에 나가는 값이라, 사실이 아닌 문장을
    넣으면 잘못된 정보가 그대로 올라갈 수 있다.
    """
    hashtags = [f"#{store.name.replace(' ', '')}"]
    if store.category:
        hashtags.append(f"#{store.category.replace(' ', '')}")

    return PublishKit(
        caption=f"{store.name}",
        hashtags=hashtags,
        post_note="AI 연동 전 임시 게시자료입니다. 캡션을 직접 수정해주세요.",
        is_placeholder=True,
    )


# ------------------------------------------------------------- 숏폼 Agent (R06)
#
# `docs/AI_연동_입출력.md` 5~12번 기준(2026-08-26). 기존 "포맷 선택 → 질문형 →
# AI 기획" 구조는 폐기되고, 대화형 세션이 ACTIVE 영상편집템플릿 중 1개를
# 추천하는 구조로 바뀌었다. 추천을 받아들이면(11번) 그 결과로 프로젝트를 만든다
# (`app/services/shortform_session.py`).


@dataclass(frozen=True)
class SessionOption:
    """대화 turn에서 사용자에게 보여줄 선택지."""

    id: str
    label: str


@dataclass(frozen=True)
class Recommendation:
    """숏폼 Agent가 추천한 영상편집템플릿 1개 (API명세서 AI_연동_입출력.md 9·10번).

    `editing_template_id`·`editing_template_version`은 우리 `video_formats`가 아니라
    **AI 서버 쪽 템플릿 카탈로그**를 가리킨다. 세션이 끝나 프로젝트로 확정될 때
    (`accept`) `video_formats`에 없으면 새로 적재한다 — 5.1이 `reference_url` 기준으로
    하는 것과 같은 방식이다.
    """

    recommendation_id: str
    project_title: str
    title: str
    concept: str
    editing_template_id: str
    editing_template_version: int


@dataclass(frozen=True)
class SessionGreeting:
    """세션을 막 만들었을 때의 첫 응답."""

    session_token: str
    assistant_message: str
    options: list[SessionOption]
    project_state: dict[str, Any]
    is_placeholder: bool = False


@dataclass(frozen=True)
class TurnResult:
    """대화 turn 하나의 응답 (API명세서 AI_연동_입출력.md 8번)."""

    action: str
    assistant_message: str | None
    project_state: dict[str, Any]
    options: list[SessionOption]
    recommendation: Recommendation | None = None
    is_placeholder: bool = False


def start_shortform_session(
    store: Store, menus: list[StoreMenu], trade_area_insight: str | None
) -> SessionGreeting:
    """숏폼 Agent 세션을 시작한다.

    `menus`(대표메뉴 전체)·`trade_area_insight`(상권분석 인사이트 원문)는 AI 서버의
    `store_context`(`docs/AI_연동_입출력.md` 6번: `store`+`representative_menus`+
    `trade_area`)를 채우는 데 필요하다. placeholder는 참고하지 않지만, 연동 시점에
    호출부(`app/services/shortform_session.py`) 시그니처를 다시 바꾸지 않아도 되도록
    지금부터 받아둔다.

    ⚠️ `trade_area_insight`는 `store_insights.insight_content`(자유 텍스트)를 그대로
    넘긴 것이다. AI가 원하는 `{characteristics: [...], target_age_ranges: [...]}` 구조로
    바꾸는 방법은 아직 없다 — 연동 시점에 정해야 한다.

    AI 서버가 설정돼 있지 않으면 임시 인사말을 돌려준다.
    """
    if not is_enabled():
        return _placeholder_greeting(store)

    # AI 스펙 확정 후: POST /api/v1/shortform-sessions에 store_context를 실어 보낸다.
    raise NotImplementedError("AI 서버 연동은 스펙 확정 후 구현합니다.")


def _placeholder_greeting(store: Store) -> SessionGreeting:
    return SessionGreeting(
        session_token=f"sf_placeholder_{uuid.uuid4().hex}",
        assistant_message=f"{store.name}, 오늘 어떤 영상을 찍을까요? (AI 연동 전 임시 응답입니다)",
        options=[
            SessionOption(id="PROMOTION_GUIDE", label="홍보하고 싶은 게 있어요"),
            SessionOption(id="FREE_INPUT", label="직접 입력하기"),
        ],
        project_state={
            "promotion_subject": None,
            "promotion_objective": None,
            "filming_time": None,
            "face_exposure": None,
            "ready_for_confirmation": False,
        },
        is_placeholder=True,
    )


def submit_shortform_turn(
    store: Store,
    session_token: str,
    project_state: dict[str, Any],
    turn_input: dict[str, Any],
    representative_menu: StoreMenu | None,
) -> TurnResult:
    """대화 turn을 처리한다.

    `session_token`(AI 쪽 세션 식별자)과 `turn_input`(사용자가 실제로 입력한
    내용 — `{"type": "TEXT"/"OPTION"/"CONFIRM", ...}`)은 실제 연동 시
    `POST /api/v1/shortform-sessions/{session_id}/turns`에 그대로 실어 보낼 값이다.
    placeholder는 지금 이 값들을 해석하지 않는다 — 지어내면 실제로 나눈 적 없는
    대화가 있었던 것처럼 보인다. 대신 turn이 오면 **곧바로 추천 단계로 진행**해,
    AI 연동 전에도 "대화 → 추천 → 수락" 전체 화면 흐름을 끝까지 확인할 수 있게 한다.

    AI 서버가 설정돼 있지 않으면 임시 결과를 돌려준다.
    """
    if not is_enabled():
        return _placeholder_turn(store, project_state, representative_menu)

    del session_token, turn_input  # 실제 연동 시 AI 요청 본문을 구성하는 데 쓴다
    # AI 스펙 확정 후: POST /api/v1/shortform-sessions/{session_id}/turns
    raise NotImplementedError("AI 서버 연동은 스펙 확정 후 구현합니다.")


def _placeholder_turn(
    store: Store, project_state: dict[str, Any], representative_menu: StoreMenu | None
) -> TurnResult:
    recommendation = _placeholder_recommendation(store, representative_menu)
    new_state = dict(project_state)
    new_state["ready_for_confirmation"] = True
    if representative_menu is not None:
        new_state["promotion_subject"] = {
            "type": "MENU",
            "name": representative_menu.name,
            "menu_id": representative_menu.id,
        }
    return TurnResult(
        action="RECOMMEND",
        assistant_message=None,
        project_state=new_state,
        options=[],
        recommendation=recommendation,
        is_placeholder=True,
    )


def get_next_shortform_recommendation(
    store: Store,
    session_token: str,
    representative_menu: StoreMenu | None,
    shown_template_ids: list[str],
) -> Recommendation:
    """다시 추천 받기. 이미 보여준 템플릿은 제외한다.

    AI 서버가 설정돼 있지 않으면 매번 새 임시 템플릿을 만들어 돌려준다 — 실제로는
    같은 후보를 반복해 추천하지 않는다는 것만 흉내 낸다.
    """
    del shown_template_ids  # placeholder는 항상 새 템플릿을 만들어 자동으로 안 겹친다
    if not is_enabled():
        return _placeholder_recommendation(store, representative_menu)

    del session_token
    # AI 스펙 확정 후: POST /api/v1/shortform-sessions/{session_id}/recommendations/next
    raise NotImplementedError("AI 서버 연동은 스펙 확정 후 구현합니다.")


def _placeholder_recommendation(
    store: Store, representative_menu: StoreMenu | None
) -> Recommendation:
    """AI 연동 전 임시 추천.

    **실제 템플릿 매칭이 아니다.** `editing_template_id`를 매번 새로 만들어, 이
    추천을 수락(accept)하면 `video_formats`에 새 행으로 적재된다(5.1이 `reference_url`
    기준으로 적재하는 것과 같은 자리에서, 이건 `editing_template_id` 기준).
    """
    template_id = f"placeholder-template-{uuid.uuid4().hex[:12]}"
    subject = representative_menu.name if representative_menu else store.name
    return Recommendation(
        recommendation_id=f"placeholder-rec-{uuid.uuid4().hex[:12]}",
        project_title=f"{subject} 소개 숏폼",
        title=f"{subject}을(를) 보여주는 숏폼 (AI 연동 전 임시 추천)",
        concept="AI 연동 전이라 실제 컨셉이 아닙니다. 연동 후 매장·메뉴에 맞춰 추천됩니다.",
        editing_template_id=template_id,
        editing_template_version=1,
    )
