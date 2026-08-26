"""편집 완료 감시 + 푸시 알림 발송 테스트."""

from typing import Any

import pytest
from sqlalchemy.orm import Session

from app.models.push_token import PushPlatform, PushToken
from app.models.shorts_project import ShortsProject
from app.models.store import Store
from app.models.user import User
from app.models.video_output import RenderStatus, VideoOutput
from app.services import ai_client
from app.services.edit_notify import notify_completed_edits


@pytest.fixture
def store(db_session: Session) -> Store:
    user = User(
        email="owner@example.com",
        password_hash="x",
        name="김사장",
        is_active=True,
        terms_agreed=True,
    )
    db_session.add(user)
    db_session.flush()

    store = Store(user_id=user.id, name="행복분식", category="분식", address="서울 강남구")
    db_session.add(store)
    db_session.commit()
    return store


@pytest.fixture
def project(db_session: Session, store: Store) -> ShortsProject:
    project = ShortsProject(store_id=store.id, promotion_purpose="메뉴소개")
    db_session.add(project)
    db_session.commit()
    return project


def _stub_editing_run(
    monkeypatch: pytest.MonkeyPatch, status: str, result: ai_client.EditingRunResult | None = None
) -> None:
    monkeypatch.setattr(
        ai_client,
        "get_editing_run",
        lambda run_id: ai_client.EditingRun(run_id=run_id, status=status),
    )
    if result is not None:
        monkeypatch.setattr(ai_client, "get_editing_run_result", lambda run_id: result)


def test_notify_sends_push_on_completion(
    db_session: Session, project: ShortsProject, store: Store, monkeypatch: pytest.MonkeyPatch
) -> None:
    output = VideoOutput(
        shorts_project_id=project.id,
        ai_run_id="run1",
        target_platform="INSTAGRAM",
        render_status=RenderStatus.PENDING,
    )
    db_session.add(output)
    db_session.add(
        PushToken(
            user_id=store.user_id,
            push_token="ExponentPushToken[abc]",
            platform=PushPlatform.ANDROID,
        )
    )
    db_session.commit()

    _stub_editing_run(
        monkeypatch, "COMPLETED", ai_client.EditingRunResult(recipe={}, video_url=None)
    )
    sent: list[Any] = []
    monkeypatch.setattr(
        "app.services.edit_notify.push_notify.send_push",
        lambda token, title, body, data=None: sent.append((token, title, body, data)) or True,
    )

    checked, notified = notify_completed_edits(db_session)

    assert (checked, notified) == (1, 1)
    assert sent == [
        (
            "ExponentPushToken[abc]",
            "영상이 완성됐어요!",
            "지금 확인하러 가볼까요?",
            {"shorts_project_id": output.id},
        )
    ]
    db_session.refresh(output)
    assert output.push_notified_at is not None


def test_notify_marks_handled_without_push_token(
    db_session: Session, project: ShortsProject, monkeypatch: pytest.MonkeyPatch
) -> None:
    """토큰 등록 안 한 사용자면 알림은 못 보내도 다시 확인하지 않도록 표시해둔다."""
    output = VideoOutput(
        shorts_project_id=project.id,
        ai_run_id="run1",
        target_platform="INSTAGRAM",
        render_status=RenderStatus.PENDING,
    )
    db_session.add(output)
    db_session.commit()

    _stub_editing_run(monkeypatch, "FAILED")
    monkeypatch.setattr(
        "app.services.edit_notify.push_notify.send_push",
        lambda *args, **kwargs: pytest.fail("토큰이 없으면 발송을 시도하면 안 된다"),
    )

    checked, notified = notify_completed_edits(db_session)

    assert (checked, notified) == (1, 0)
    db_session.refresh(output)
    assert output.push_notified_at is not None


def test_notify_leaves_in_progress_output_alone(
    db_session: Session, project: ShortsProject, monkeypatch: pytest.MonkeyPatch
) -> None:
    output = VideoOutput(
        shorts_project_id=project.id,
        ai_run_id="run1",
        target_platform="INSTAGRAM",
        render_status=RenderStatus.PROCESSING,
    )
    db_session.add(output)
    db_session.commit()

    _stub_editing_run(monkeypatch, "RUNNING")

    checked, notified = notify_completed_edits(db_session)

    assert (checked, notified) == (1, 0)
    db_session.refresh(output)
    assert output.push_notified_at is None
    assert output.render_status == RenderStatus.PROCESSING


def test_notify_is_idempotent(
    db_session: Session, project: ShortsProject, monkeypatch: pytest.MonkeyPatch
) -> None:
    """이미 완료+알림 발송된 건 다음 실행에서 다시 잡히지 않는다."""
    output = VideoOutput(
        shorts_project_id=project.id,
        ai_run_id="run1",
        target_platform="INSTAGRAM",
        render_status=RenderStatus.PENDING,
    )
    db_session.add(output)
    db_session.commit()

    _stub_editing_run(monkeypatch, "FAILED")
    checked, notified = notify_completed_edits(db_session)
    assert checked == 1

    # 이번엔 COMPLETED/PROCESSING인 다른 행이 하나도 없으니 확인 대상 자체가 없다.
    checked_again, notified_again = notify_completed_edits(db_session)
    assert (checked_again, notified_again) == (0, 0)
