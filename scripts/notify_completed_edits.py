"""편집 완료(또는 실패)를 감시해 푸시 알림을 보낸다.

    poetry run python -m scripts.notify_completed_edits

**여러 번 돌려도 안전하다** — 이미 알림을 보낸 산출물은 다시 보내지 않는다
(`video_outputs.push_notified_at`).

AI 서버가 설정돼 있지 않으면(`AI_SERVER_URL` 비어 있음) 진행 중인 편집이
`COMPLETED`로 바뀌는 일 자체가 없어 항상 "확인 0건"으로 끝난다 — 별도 조기
종료 처리가 필요 없다.
"""

from app.db.session import SessionLocal
from app.services.edit_notify import notify_completed_edits


def main() -> None:
    with SessionLocal() as db:
        checked, notified = notify_completed_edits(db)
    print(f"편집 완료 감시 완료 — 확인 {checked}건, 알림 발송 {notified}건")


if __name__ == "__main__":
    main()
