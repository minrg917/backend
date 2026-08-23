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

from dataclasses import dataclass, field
from typing import Any

from app.core.config import settings
from app.models.shorts_project import ShortsProject
from app.models.store import Store
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
class ShootingPlan:
    """AI 기획 결과 전체 (API명세서 7.1)."""

    estimated_shooting_sec: int | None
    required_people: int | None
    props: list[str] = field(default_factory=list)
    difficulty: str | None = None
    scenes: list[PlannedScene] = field(default_factory=list)
    tasks: list[PlannedTask] = field(default_factory=list)
    # 실제 AI가 만든 결과가 아니라 임시 뼈대라는 표시
    is_placeholder: bool = False


def is_enabled() -> bool:
    """AI 서버가 설정돼 있는지."""
    return bool(settings.AI_SERVER_URL)


def generate_plan(store: Store, video_format: VideoFormat) -> ShootingPlan:
    """포맷과 가게 정보로 대본·콘티를 만든다.

    AI 서버가 설정돼 있지 않으면 임시 뼈대를 돌려준다 — 연동 전에도 화면 흐름을
    끝까지 확인할 수 있어야 하고, CI에서도 테스트가 돌아야 한다.
    """
    if not is_enabled():
        return _placeholder_plan(store, video_format)

    # AI 스펙이 나오면 여기에 httpx 호출을 넣는다.
    # 요청에 무엇을 보낼지(가게 정보·타깃 목록·포맷·홍보 목적)와 응답 형식이
    # 정해져야 하며, 응답 시간에 따라 동기/비동기도 여기서 갈린다.
    raise NotImplementedError("AI 서버 연동은 스펙 확정 후 구현합니다.")


def _placeholder_plan(store: Store, video_format: VideoFormat) -> ShootingPlan:
    """AI 연동 전 임시 기획.

    포맷의 촬영 컷 구성을 흉내 낸 뼈대만 만든다. **가게별 맞춤이 아니다** —
    대사에 가게 이름만 끼워 넣을 뿐, 실제 기획은 AI가 붙어야 나온다.
    """
    duration = video_format.expected_duration_sec or 30
    per_scene = max(duration // 4, 3)

    scenes = [
        PlannedScene(
            scene_order=1,
            scene_description="간판 클로즈업",
            scene_dialogue=f"{store.name}입니다.",
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
            scene_dialogue="지금 보러 오세요!",
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

    return ShootingPlan(
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
