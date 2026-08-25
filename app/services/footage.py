"""촬영 가이드·촬영본 로직 (API명세서 9.1, 9.2)."""

import uuid

from fastapi import UploadFile
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.shooting_task import ShootingTask, TaskStatus
from app.models.shorts_project import ShortsProject
from app.models.storyboard_scene import StoryboardScene
from app.models.video_format import VideoFormat
from app.schemas.shorts_project import (
    BrollShot,
    GuideType,
    OverlayGuide,
    ReferenceVideo,
    TaskGuideResponse,
)
from app.services.store_photo import validate_upload
from app.storage import Storage

# content_type → 저장할 확장자. 원본 파일명을 믿지 않고 여기서 결정한다.
_VIDEO_EXTENSIONS = {
    "video/mp4": ".mp4",
    "video/quicktime": ".mov",
    "video/x-m4v": ".m4v",
    "video/webm": ".webm",
}


def build_guide(db: Session, task: ShootingTask) -> TaskGuideResponse:
    """촬영 안내를 조립한다 (API명세서 9.1).

    값이 세 곳에 흩어져 있다 — 태스크의 `guide`(AI 생성), 콘티의 `shot_type`,
    포맷의 `reference_url`. 중복 저장하지 않고 필요할 때 모은다.

    `guide_type`에 따라 채우는 블록이 다르다. 명세서가 쓰지 않는 블록을 `null`로
    내리도록 정의하고 있어, 키는 항상 있고 값만 비운다.
    """
    guide = task.guide or {}
    guide_type = GuideType(guide.get("guide_type", GuideType.OVERLAY))

    reference_video = None
    if guide_type is GuideType.DANCE:
        reference_video = _reference_video(db, task)

    overlay = None
    if guide_type is GuideType.OVERLAY:
        # AI 연동 전까지 비어 있다. 지어내면 가짜 안내가 진짜처럼 보인다.
        overlay = OverlayGuide(instructions=guide.get("instructions") or [])

    broll_shot = None
    if guide_type in (GuideType.OVERLAY, GuideType.BROLL):
        shot = guide.get("broll_shot") or {}
        broll_shot = BrollShot(
            # shot_type은 태스크가 아니라 콘티에 있다(중복 저장하지 않는다)
            shot_type=_scene_shot_type(db, task),
            distance=shot.get("distance"),
            angle=shot.get("angle"),
        )

    return TaskGuideResponse(
        guide_type=guide_type,
        overlay=overlay,
        reference_video=reference_video,
        broll_shot=broll_shot,
    )


def _scene_shot_type(db: Session, task: ShootingTask) -> str | None:
    if task.scene_id is None:
        return None
    scene = db.get(StoryboardScene, task.scene_id)
    return scene.shot_type if scene else None


def _reference_video(db: Session, task: ShootingTask) -> ReferenceVideo | None:
    """안무 영상은 포맷 하나당 하나다 — 프로젝트가 고른 포맷에서 가져온다.

    태스크별 컬럼을 두지 않기로 한 결정(`docs/PM_DECISIONS.md` 2026-08-21 R10).

    **가이드 영상을 준다.** 촬영 중에 사장님이 따라 추는 영상이라서다 — 대표 영상은
    "이 유행이 어떤 건지" 보여주는 것이라 여기 오면 따라 출 안무 대신 유행 소개
    영상이 재생된다. 명세 9.1이 "`video_formats.reference_url`을 그대로 재사용"이라고
    적힌 것은 포맷에 영상 주소가 하나뿐이던 시절 문구다.

    가이드 영상이 없으면 대표 영상으로 떨어진다 — 트렌드 연동 전에 들어온 포맷과
    R06 추천으로 적재된 포맷에는 아직 이 값이 없다.
    """
    project = db.get(ShortsProject, task.shorts_project_id)
    if project is None or project.video_format_id is None:
        return None
    video_format = db.get(VideoFormat, project.video_format_id)
    if video_format is None:
        return None
    return ReferenceVideo(
        reference_url=video_format.guide_video_url or video_format.reference_url,
        source_platform=video_format.source_platform,
    )


def upload_footage(
    db: Session,
    storage: Storage,
    task: ShootingTask,
    upload: UploadFile,
    footage_type: str,
    footage_duration_sec: int | None,
) -> ShootingTask:
    """촬영본을 저장하고 태스크를 완료 처리한다 (API명세서 9.2).

    **재촬영은 덮어쓴다** — ERD 코멘트가 "재촬영 시 덮어씀, 테이크 이력 없음"이다.
    기존 파일을 저장소에서 지우고 새로 올린다. 파일명이 매번 달라지므로 지우지
    않으면 아무도 참조하지 않는 파일이 계속 쌓인다.

    업로드 성공이 `task_status`를 `DONE`으로 만드는 **유일한 정상 경로**다
    (2026-08-21 확정).
    """
    extension = validate_upload(
        upload,
        allowed_types=settings.allowed_video_type_set,
        extensions=_VIDEO_EXTENSIONS,
        max_bytes=settings.max_video_upload_size_bytes,
        limit_mb=settings.MAX_VIDEO_UPLOAD_SIZE_MB,
        unsupported_message="지원하지 않는 파일 형식입니다. 영상 파일만 업로드할 수 있습니다.",
    )

    previous_key = task.footage_url
    key = f"projects/{task.shorts_project_id}/footage/{uuid.uuid4().hex}{extension}"
    storage.save(key, upload.file, upload.content_type)

    task.footage_url = key
    task.footage_type = footage_type
    task.footage_duration_sec = footage_duration_sec
    task.task_status = TaskStatus.DONE
    db.commit()
    db.refresh(task)

    # DB를 먼저 갱신하고 옛 파일을 지운다. 반대 순서면 저장 실패 시 파일만 사라진다.
    if previous_key and previous_key != key:
        storage.delete(previous_key)

    return task
