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
class EditRecipe:
    """AI가 만든 편집 명령 (API명세서 14.1).

    컷 순서·전환·자막·오디오 큐를 담는다(기능명세서 S14.x). 실제 구조는 AI 스펙이
    확정되면 정해지며, 지금은 JSON으로 그대로 보관한다.
    """

    recipe: dict[str, Any]
    resolution: str | None = None
    has_licensed_audio: bool = False
    is_placeholder: bool = False


def generate_edit_recipe(target_platform: str, revision_action: str | None = None) -> EditRecipe:
    """편집 레시피를 만든다.

    `revision_action`이 있으면 수정 요청(14.3)이다 — "자막 크게" 같은 지시를
    반영한 새 레시피를 만든다.

    AI 서버가 설정돼 있지 않으면 임시 레시피를 돌려준다.
    """
    if not is_enabled():
        return _placeholder_recipe(target_platform, revision_action)

    raise NotImplementedError("AI 서버 연동은 스펙 확정 후 구현합니다.")


def _placeholder_recipe(target_platform: str, revision_action: str | None) -> EditRecipe:
    """AI 연동 전 임시 레시피.

    **실제 편집 명령이 아니다.** 어떤 요청이 있었는지만 기록해두고, 렌더링도
    일어나지 않는다(`render_status`가 진행되지 않음).
    """
    return EditRecipe(
        recipe={
            "target_platform": target_platform,
            "revision_action": revision_action,
            "note": "AI 연동 전 임시 레시피 — 실제 편집 명령이 아님",
        },
        # 플랫폼별 규격. 숏폼은 9:16이 표준이다.
        resolution="1080x1920",
        has_licensed_audio=False,
        is_placeholder=True,
    )


@dataclass(frozen=True)
class PublishKit:
    """게시자료 (API명세서 15.1).

    사장님이 SNS에 올릴 때 그대로 붙여넣을 캡션·해시태그와, 음원 선택 같은
    플랫폼 안내 문구를 담는다.
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


def generate_publish_kit(store: Store, project: ShortsProject) -> PublishKit:
    """게시자료를 만든다.

    가게 정보와 프로젝트의 홍보 목적을 근거로 캡션·해시태그를 생성한다.
    AI 서버가 설정돼 있지 않으면 임시 게시자료를 돌려준다.
    """
    if not is_enabled():
        return _placeholder_publish_kit(store)

    raise NotImplementedError("AI 서버 연동은 스펙 확정 후 구현합니다.")


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
