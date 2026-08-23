"""AI 자동편집 로직 (API명세서 14.1~14.3)."""

import json

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.exceptions import BadRequestError, NotFoundError
from app.models.shooting_task import ShootingTask
from app.models.shorts_project import ShortsProject
from app.models.store import Store
from app.models.storyboard_scene import StoryboardScene
from app.models.user import User
from app.models.video_output import RenderStatus, VideoOutput
from app.schemas.shorts_project import TimelineItem
from app.services import ai_client

# 렌더링 진행률. ⚠️ 실제 진행률이 아니라 상태에서 매핑한 근사값이다.
# 렌더러가 붙으면 실제 값을 받아 이 표를 대체한다.
_PROGRESS_BY_STATUS = {
    RenderStatus.PENDING: 0,
    RenderStatus.PROCESSING: 50,
    RenderStatus.COMPLETED: 100,
    RenderStatus.FAILED: 0,
}


class OutputNotFound(NotFoundError):
    error_code = "OUTPUT_NOT_FOUND"
    message = "편집 결과를 찾을 수 없습니다."


class TasksIncomplete(BadRequestError):
    error_code = "TASKS_INCOMPLETE"
    message = "아직 촬영하지 않은 태스크가 있어 편집을 시작할 수 없습니다."


def start_edit(db: Session, project: ShortsProject, target_platform: str) -> VideoOutput:
    """편집을 시작한다 (API명세서 14.1).

    **모든 태스크가 촬영본을 가져야 시작할 수 있다**(2026-08-21 확정). 필수/선택을
    구분하지 않는 이유는 건너뛰기·교체 기능이 스코프에서 빠져 "선택 태스크"를
    구분해도 할 수 있는 게 없기 때문이다.

    검증 기준은 `task_status`가 아니라 **`footage_url` 존재 여부**다 — 8.2로 상태만
    `DONE`으로 바꿔도 촬영본이 없으면 편집할 재료가 없다.
    """
    _require_all_footage(db, project)

    recipe = ai_client.generate_edit_recipe(target_platform)
    output = VideoOutput(
        shorts_project_id=project.id,
        edit_recipe=json.dumps(recipe.recipe, ensure_ascii=False),
        target_platform=target_platform,
        resolution=recipe.resolution,
        has_licensed_audio=recipe.has_licensed_audio,
        render_status=RenderStatus.PENDING,
    )
    db.add(output)
    db.commit()
    db.refresh(output)
    return output


def _require_all_footage(db: Session, project: ShortsProject) -> None:
    tasks = list(
        db.scalars(
            select(ShootingTask)
            .where(ShootingTask.shorts_project_id == project.id)
            .order_by(ShootingTask.display_order, ShootingTask.id)
        )
    )
    if not tasks:
        # 7.1을 호출한 적 없어 태스크 자체가 없는 경우. 편집할 재료가 없다.
        raise TasksIncomplete(
            "촬영 태스크가 없습니다. 기획을 먼저 생성해주세요.", extra={"incomplete_tasks": []}
        )

    incomplete = [task for task in tasks if not task.footage_url]
    if incomplete:
        # 어떤 태스크가 비었는지 알려줘야 프론트가 태스크 보드로 안내할 수 있다.
        raise TasksIncomplete(
            extra={
                "incomplete_tasks": [
                    {"id": task.id, "task_title": task.task_title} for task in incomplete
                ]
            }
        )


def latest_output(db: Session, project: ShortsProject) -> VideoOutput:
    """가장 최근 산출물. 프로젝트당 여러 개(플랫폼별·수정 이력)가 쌓인다."""
    output = db.scalar(
        select(VideoOutput)
        .where(VideoOutput.shorts_project_id == project.id)
        .order_by(VideoOutput.created_at.desc(), VideoOutput.id.desc())
        .limit(1)
    )
    if output is None:
        raise OutputNotFound
    return output


def progress_percent(output: VideoOutput) -> int:
    """렌더링 진행률.

    ⚠️ **실제 진행률이 아니다.** 렌더러가 없어 상태에서 매핑한 근사값이며,
    `PROCESSING`은 항상 50을 돌려준다. 렌더러가 붙으면 여기만 바꾼다.
    """
    return _PROGRESS_BY_STATUS.get(RenderStatus(output.render_status), 0)


def build_timeline(db: Session, project: ShortsProject) -> list[TimelineItem]:
    """타임라인 요약을 콘티에서 만든다.

    `effect`(전환 효과)는 AI 편집 레시피에서 나오는 값이라 연동 전까지 `null`이다.
    지어내면 실제로 적용되지 않은 효과가 화면에 표시된다.
    """
    scenes = db.scalars(
        select(StoryboardScene)
        .where(StoryboardScene.shorts_project_id == project.id)
        .order_by(StoryboardScene.scene_order, StoryboardScene.id)
    )
    return [
        TimelineItem(
            scene_order=scene.scene_order,
            duration_sec=scene.target_duration_sec,
            effect=None,
        )
        for scene in scenes
    ]


def get_owned_output(db: Session, owner: User, output_id: int) -> VideoOutput:
    """본인 소유 산출물. 산출물 → 프로젝트 → 가게 → 사용자로 거슬러 확인한다."""
    output = db.get(VideoOutput, output_id)
    if output is None:
        raise OutputNotFound

    project = db.get(ShortsProject, output.shorts_project_id)
    store = db.get(Store, project.store_id) if project else None
    if store is None or store.user_id != owner.id:
        raise OutputNotFound
    return output


def revise(db: Session, output: VideoOutput, request_type: str, action: str) -> VideoOutput:
    """편집 수정을 요청한다 (API명세서 14.3).

    **기존 산출물을 고치지 않고 새 행을 만든다** — ERD의 `created_at` 코멘트가
    "수정 요청마다 새 행이 쌓여 자연스럽게 버전 이력이 됨"이다. 이전 버전으로
    돌아갈 수 있고, 어떤 지시로 만들어졌는지도 레시피에 남는다.
    """
    del request_type  # AI 연동 시 프롬프트 구성에 사용한다

    recipe = ai_client.generate_edit_recipe(output.target_platform or "", revision_action=action)
    revised = VideoOutput(
        shorts_project_id=output.shorts_project_id,
        edit_recipe=json.dumps(recipe.recipe, ensure_ascii=False),
        target_platform=output.target_platform,
        resolution=recipe.resolution,
        has_licensed_audio=recipe.has_licensed_audio,
        render_status=RenderStatus.PROCESSING,
    )
    db.add(revised)
    db.commit()
    db.refresh(revised)
    return revised


def revision_number(db: Session, output: VideoOutput) -> int:
    """프로젝트 내 산출물 순번(1부터).

    저장 컬럼을 만들지 않고 계산한다 — 산출물이 시간순으로 쌓이므로 순서가 곧
    버전이다. 컬럼을 두면 행 삭제 시 어긋날 수 있다.
    """
    ids = list(
        db.scalars(
            select(VideoOutput.id)
            .where(VideoOutput.shorts_project_id == output.shorts_project_id)
            .order_by(VideoOutput.created_at, VideoOutput.id)
        )
    )
    return ids.index(output.id) + 1
