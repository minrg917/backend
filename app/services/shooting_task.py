"""촬영 태스크 보드 로직 (API명세서 8.1, 8.2)."""

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.exceptions import NotFoundError
from app.models.shooting_task import COMPLETED_STATUSES, ShootingTask, TaskStatus
from app.models.shorts_project import ShortsProject
from app.models.store import Store
from app.models.user import User


class TaskNotFound(NotFoundError):
    error_code = "TASK_NOT_FOUND"
    message = "촬영 태스크를 찾을 수 없습니다."


def list_tasks(db: Session, project: ShortsProject) -> list[ShootingTask]:
    """보드 노출 순서대로 돌려준다."""
    return list(
        db.scalars(
            select(ShootingTask)
            .where(ShootingTask.shorts_project_id == project.id)
            .order_by(ShootingTask.display_order, ShootingTask.id)
        )
    )


def get_owned_task(db: Session, owner: User, task_id: int) -> ShootingTask:
    """본인 소유 태스크를 가져온다.

    태스크에는 사용자 정보가 없어 **태스크 → 프로젝트 → 가게 → 사용자**로 거슬러
    확인한다. 남의 것은 404다(존재 자체를 숨긴다).
    """
    task = db.get(ShootingTask, task_id)
    if task is None:
        raise TaskNotFound

    project = db.get(ShortsProject, task.shorts_project_id)
    store = db.get(Store, project.store_id) if project else None
    if store is None or store.user_id != owner.id:
        raise TaskNotFound
    return task


def update_status(db: Session, task: ShootingTask, status: TaskStatus) -> ShootingTask:
    task.task_status = status
    db.commit()
    db.refresh(task)
    return task


def calculate_progress_rate(tasks: list[ShootingTask]) -> int:
    """진행률(%). 2026-08-21 확정 공식.

    `DONE`과 `RETAKE_NEEDED`를 완료로 센다 — `RETAKE_NEEDED`는 촬영본 자체는 있고
    AI 평가로 품질 경고만 붙은 상태라 "찍긴 찍은" 것이다. 태스크가 없으면 0이다.
    """
    if not tasks:
        return 0
    done = sum(1 for task in tasks if task.task_status in COMPLETED_STATUSES)
    return round(done / len(tasks) * 100)


def estimate_remaining_min(project: ShortsProject, tasks: list[ShootingTask]) -> int | None:
    """남은 촬영 예상 시간(분).

    ⚠️ **근사값이다.** 전체 예상 촬영시간을 남은 태스크 비율만큼 곱한 것이라
    **모든 태스크가 같은 시간이 걸린다고 가정**한다. "간판 한 컷"과 "제조 과정 전체"가
    같은 시간으로 계산된다.

    `shooting_tasks`에 태스크별 예상 시간 컬럼이 없어서다. **AI가 태스크 분해 결과에
    태스크별 시간을 함께 주면**(확인 대기 중) 컬럼을 추가하고 남은 것만 합산하는
    방식으로 이 함수만 바꾸면 된다 — 호출부는 그대로다.

    전체 예상 시간이 없거나(7.1 미호출) 태스크가 없으면 None이다.
    """
    total_sec = project.estimated_shooting_sec
    if not total_sec or not tasks:
        return None

    remaining = sum(1 for task in tasks if task.task_status not in COMPLETED_STATUSES)
    return round(total_sec * (remaining / len(tasks)) / 60)
