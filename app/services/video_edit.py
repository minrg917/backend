"""AI 자동편집 로직 (API명세서 14.1~14.3).

2026-08-26: AI팀 지침(`docs/AI_연동_입출력.md` 15~21번)에 따라 **비동기(run 생성
+ 폴링) 구조로 재설계**했다. FE가 보는 계약(14.1이 `render_status`를 즉시 돌려주고
14.2가 폴링하는 모양)은 원래도 이 모양이었어서 바뀌지 않는다 — 안쪽에서 AI를
동기 호출 한 번으로 끝내던 것을, run을 만들고 GET마다 상태를 동기화하는 방식으로
바꿨을 뿐이다.
"""

import json
import tempfile
import uuid

import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.exceptions import BadRequestError, NotFoundError
from app.models.shooting_task import ShootingTask
from app.models.shorts_project import ShortsProject
from app.models.store import Store
from app.models.storyboard_scene import StoryboardScene
from app.models.user import User
from app.models.video_format import VideoFormat
from app.models.video_output import RenderStatus, VideoOutput
from app.schemas.shorts_project import TimelineItem
from app.services import ai_client
from app.storage import StorageError, get_storage, to_public_url

# 렌더링 진행률. ⚠️ 실제 진행률이 아니라 상태에서 매핑한 근사값이다.
# 렌더러가 붙으면 실제 값을 받아 이 표를 대체한다.
_PROGRESS_BY_STATUS = {
    RenderStatus.PENDING: 0,
    RenderStatus.PROCESSING: 50,
    RenderStatus.COMPLETED: 100,
    RenderStatus.FAILED: 0,
    RenderStatus.SOURCE_GAP: 0,
}

# AI가 쓰는 상태 문자열 -> 우리 RenderStatus. 모르는 값은 안전하게 PENDING으로 본다.
_AI_STATUS_MAP = {
    "QUEUED": RenderStatus.PENDING,
    "RUNNING": RenderStatus.PROCESSING,
    "COMPLETED": RenderStatus.COMPLETED,
    "FAILED": RenderStatus.FAILED,
    "SOURCE_GAP": RenderStatus.SOURCE_GAP,
}


class OutputNotFound(NotFoundError):
    error_code = "OUTPUT_NOT_FOUND"
    message = "편집 결과를 찾을 수 없습니다."


class TasksIncomplete(BadRequestError):
    error_code = "TASKS_INCOMPLETE"
    message = "아직 촬영하지 않은 태스크가 있어 편집을 시작할 수 없습니다."


def _map_status(ai_status: str) -> RenderStatus:
    return _AI_STATUS_MAP.get(ai_status, RenderStatus.PENDING)


def _build_footage_inputs(db: Session, project: ShortsProject) -> list[ai_client.FootageInput]:
    """촬영본 목록을 AI 요청 형식으로 만든다 (`docs/AI_연동_입출력.md` 16번 `videos[]`).

    `shooting_scene_order`는 태스크가 연결된 장면의 순서다 — 장면에 연결 안 된
    태스크(`scene_id`가 `NULL`)는 `null`로 보낸다(AI 문서가 명시적으로 허용).
    """
    rows = db.execute(
        select(ShootingTask, StoryboardScene.scene_order)
        .outerjoin(StoryboardScene, StoryboardScene.id == ShootingTask.scene_id)
        .where(
            ShootingTask.shorts_project_id == project.id,
            ShootingTask.footage_url.is_not(None),
        )
        .order_by(ShootingTask.display_order, ShootingTask.id)
    ).all()
    storage = get_storage()
    return [
        ai_client.FootageInput(
            video_id=f"task_{task.id}",
            footage_url=to_public_url(storage, task.footage_url) or "",
            shooting_scene_order=scene_order or task.display_order,
        )
        for task, scene_order in rows
    ]


def start_edit(db: Session, project: ShortsProject, target_platform: str) -> VideoOutput:
    """편집을 시작한다 (API명세서 14.1).

    **모든 태스크가 촬영본을 가져야 시작할 수 있다**(2026-08-21 확정). 필수/선택을
    구분하지 않는 이유는 건너뛰기·교체 기능이 스코프에서 빠져 "선택 태스크"를
    구분해도 할 수 있는 게 없기 때문이다.

    검증 기준은 `task_status`가 아니라 **`footage_url` 존재 여부**다 — 8.2로 상태만
    `DONE`으로 바꿔도 촬영본이 없으면 편집할 재료가 없다.
    """
    _require_all_footage(db, project)
    store = db.get(Store, project.store_id)
    assert store is not None  # 프로젝트가 있으면 가게도 있다(FK)
    video_format = db.get(VideoFormat, project.video_format_id)
    assert video_format is not None

    run = ai_client.start_editing_run(
        store,
        project,
        video_format,
        _build_footage_inputs(db, project),
    )
    output = VideoOutput(
        shorts_project_id=project.id,
        ai_run_id=run.run_id,
        target_platform=target_platform,
        render_status=_map_status(run.status),
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


def sync_output(db: Session, output: VideoOutput) -> VideoOutput:
    """AI 쪽 편집 실행 상태를 우리 산출물에 반영한다.

    14.2(`GET .../edit/result`)를 부를 때마다, 그리고 15.1이 최신 산출물을
    참조하기 직전에 호출한다 — 렌더링이 비동기라 우리가 먼저 알 방법이 없고,
    폴링 요청이 올 때 AI 쪽 상태를 확인하는 수밖에 없다("poll-through").

    이미 끝난 상태(`COMPLETED`/`FAILED`/`SOURCE_GAP`)거나 `ai_run_id`가 없으면
    (레거시 데이터) 그대로 돌려준다 — 끝난 편집은 다시 진행되지 않는다.
    """
    still_in_progress = output.render_status in (RenderStatus.PENDING, RenderStatus.PROCESSING)
    if not still_in_progress or not output.ai_run_id:
        return output

    run = ai_client.get_editing_run(output.ai_run_id)
    new_status = _map_status(run.status)
    if new_status == output.render_status:
        return output

    output.render_status = new_status
    if new_status is RenderStatus.COMPLETED:
        result = ai_client.get_editing_run_result(output.ai_run_id)
        output.edit_recipe = json.dumps(result.recipe or {}, ensure_ascii=False)
        output.video_url = _persist_rendered_video(output.shorts_project_id, result.video_url)
        output.cover_image_url = result.cover_image_url
        output.resolution = result.resolution
        # 배경음악을 직접 입히지 않기로 확정돼 항상 false다(2026-08-24 결정,
        # `docs/AI_연동_입출력.md` 19번).
        output.has_licensed_audio = False
        if result.publishing is not None:
            project = db.get(ShortsProject, output.shorts_project_id)
            assert project is not None
            project.publish_kit = {
                "caption": result.publishing.caption,
                "hashtags": result.publishing.hashtags,
                "post_note": result.publishing.post_note,
                "track": result.publishing.track,
            }
    elif new_status is RenderStatus.SOURCE_GAP:
        result = ai_client.get_editing_run_result(output.ai_run_id)
        output.missing_scene_roles = result.missing_scene_roles or []
        output.available_options = result.available_options or []

    db.commit()
    db.refresh(output)
    return output


def _persist_rendered_video(project_id: int, source_url: str | None) -> str | None:
    """AI 렌더러의 사설 URL을 메인 저장소로 스트리밍 복사하고 DB용 키를 반환한다."""
    if not source_url:
        return None

    key = f"projects/{project_id}/outputs/{uuid.uuid4().hex}.mp4"
    try:
        with httpx.stream(
            "GET",
            source_url,
            timeout=httpx.Timeout(180.0, connect=5.0),
        ) as response:
            response.raise_for_status()
            content_type = response.headers.get("content-type", "video/mp4").split(";", 1)[0]
            with tempfile.SpooledTemporaryFile(max_size=16 * 1024 * 1024) as stream:
                for chunk in response.iter_bytes():
                    stream.write(chunk)
                stream.seek(0)
                get_storage().save(key, stream, content_type)
    except (httpx.HTTPError, StorageError) as exc:
        raise ai_client.AIServiceUnavailable from exc
    return key


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
    return sync_output(db, output)


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

    AI 쪽도 **새 run**을 만든다(`docs/AI_연동_입출력.md` 20번) — 기존 EditRecipe는
    immutable하게 유지된다.
    """
    del request_type  # AI 연동 시 프롬프트 구성에 사용한다

    project = db.get(ShortsProject, output.shorts_project_id)
    assert project is not None
    run = ai_client.request_revision(
        output.ai_run_id or "",
        action,
        _build_footage_inputs(db, project),
    )
    revised = VideoOutput(
        shorts_project_id=output.shorts_project_id,
        ai_run_id=run.run_id,
        target_platform=output.target_platform,
        render_status=_map_status(run.status),
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
