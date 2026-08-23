"""프로젝트 자동저장·이어하기 (API명세서 9.3).

앱이 "어디까지 진행했는지"를 서버에 맡겨두는 곳이다. **서버는 `client_state`의
내용을 해석하지 않는다** — 받은 JSON을 그대로 보관했다 돌려준다. 앱이 담는 내용이
바뀌어도 서버는 영향받지 않는다.

실제 데이터(촬영본·대사·설정·태스크 상태)는 각각의 API로 이미 저장되므로, 여기서
다루는 건 진행 위치뿐이다.
"""

from sqlalchemy.orm import Session

from app.models.mixins import utcnow
from app.models.shorts_project import ShortsProject
from app.schemas.shorts_project import DraftSaveRequest


def save_draft(db: Session, project: ShortsProject, payload: DraftSaveRequest) -> ShortsProject:
    """임시저장한다. 보낸 필드만 반영한다."""
    changes = payload.model_dump(exclude_unset=True)
    for field, value in changes.items():
        setattr(project, field, value)

    # `updated_at`은 태스크 상태 변경 등으로도 갱신되므로 별도로 찍는다.
    project.last_saved_at = utcnow()
    db.commit()
    db.refresh(project)
    return project
