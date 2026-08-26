"""편집 완료(또는 실패)를 감시해 사장님에게 푸시 알림을 보낸다.

`sarils-edit-notify.timer`가 주기적으로 돌리는 배치다(`scripts/notify_completed_edits.py`).
14.2가 쓰는 poll-through 함수(`video_edit.sync_output`)를 그대로 재사용해 AI
쪽 상태를 확인한다 — 상태를 매기는 기준을 두 곳에 따로 두지 않기 위함이다.

R14 자동편집이 최대 10분 넘게 걸릴 수 있어, 앱을 꺼둔 사장님에게도 완료를
알리려고 만들었다(`docs/FE_NOTICE_2026-08-26-02/03.md`). 지금은 Android만
대상이다 — iOS는 Apple Developer Program이 필요해 스코프에서 잠시 제외했다.
"""

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.mixins import utcnow
from app.models.push_token import PushToken
from app.models.shorts_project import ShortsProject
from app.models.store import Store
from app.models.video_output import RenderStatus, VideoOutput
from app.services import push_notify
from app.services.video_edit import sync_output

_TERMINAL_STATUSES = (RenderStatus.COMPLETED, RenderStatus.FAILED, RenderStatus.SOURCE_GAP)

_MESSAGE_BY_STATUS = {
    RenderStatus.COMPLETED: ("영상이 완성됐어요!", "지금 확인하러 가볼까요?"),
    RenderStatus.FAILED: ("편집에 실패했어요", "다시 시도해주세요."),
    RenderStatus.SOURCE_GAP: (
        "촬영본을 다시 확인해주세요",
        "몇몇 장면이 부족해서 편집을 끝내지 못했어요.",
    ),
}


def _push_token_for_output(db: Session, output: VideoOutput) -> PushToken | None:
    return db.scalar(
        select(PushToken)
        .join(Store, Store.user_id == PushToken.user_id)
        .join(ShortsProject, ShortsProject.store_id == Store.id)
        .where(ShortsProject.id == output.shorts_project_id)
    )


def notify_completed_edits(db: Session) -> tuple[int, int]:
    """진행 중인 편집을 전부 동기화하고, 방금 끝난 것이 있으면 푸시를 보낸다.

    **여러 번 돌려도 안전하다** — `push_notified_at`이 이미 있으면 같은
    산출물에 다시 알림을 보내지 않는다.

    돌려주는 값은 (확인한 진행 중 건수, 알림을 보낸 건수)다.
    """
    outputs = list(
        db.scalars(
            select(VideoOutput).where(
                VideoOutput.render_status.in_((RenderStatus.PENDING, RenderStatus.PROCESSING))
            )
        )
    )

    notified = 0
    for output in outputs:
        sync_output(db, output)
        if output.render_status not in _TERMINAL_STATUSES or output.push_notified_at is not None:
            continue

        token = _push_token_for_output(db, output)
        if token is not None:
            title, body = _MESSAGE_BY_STATUS[output.render_status]
            if push_notify.send_push(
                token.push_token, title, body, {"shorts_project_id": output.shorts_project_id}
            ):
                notified += 1

        output.push_notified_at = utcnow()
        db.commit()

    return len(outputs), notified
