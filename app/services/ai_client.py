"""AI 서버 호출 어댑터.

**AI 팀에서 만드는 별도 서버를 부르는 자리다.** 아직 스펙이 나오지 않아
임시 구현(`_placeholder_plan`)이 들어 있고, 스펙이 확정되면 이 파일만 채우면 된다.
호출부(`app/services/plan.py`)와 라우터는 바뀌지 않는다.

외부 검색을 `store_search.py`로 분리한 것과 같은 이유다.

- **테스트 목킹**: CI에 AI 서버가 없으므로 경계가 없으면 테스트를 못 돌린다.
- **실패 격리**: AI가 죽어도 앱이 통째로 죽지 않게 한다.
- **교체 용이**: 동기/비동기 전환도 여기만 바꾸면 된다.

⚠️ **임시 결과는 진짜 기획이 아니다.** 포맷·가게에 상관없이 같은 뼈대를 돌려주며,
`is_placeholder=True`로 표시된다. 화면에서 "AI 준비 중"을 안내하는 데 쓸 수 있다.
"""

from dataclasses import dataclass, field

from app.core.config import settings
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
class ShootingPlan:
    """AI 기획 결과 전체 (API명세서 7.1)."""

    estimated_shooting_sec: int | None
    required_people: int | None
    props: list[str] = field(default_factory=list)
    difficulty: str | None = None
    scenes: list[PlannedScene] = field(default_factory=list)
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
    return ShootingPlan(
        # 촬영은 완성 길이보다 오래 걸린다는 가정. 실제 값은 AI가 판단한다.
        estimated_shooting_sec=duration * 10,
        required_people=1,
        props=["삼각대"],
        difficulty=video_format.shooting_difficulty,
        scenes=scenes,
        is_placeholder=True,
    )
