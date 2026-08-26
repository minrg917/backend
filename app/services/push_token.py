"""편집 완료 푸시 알림용 디바이스 토큰 저장.

R14 자동편집이 완료되기까지 최대 10분 넘게 걸릴 수 있어, 앱을 꺼둔 사장님에게도
완료를 알릴 방법이 필요해서 만들었다(2026-08-26, `docs/FE_NOTICE_2026-08-26-02.md`
`docs/FE_NOTICE_2026-08-26-03.md` 참고). 실제 발송은 `app/services/push_notify.py`가
맡고, 여기는 "누구에게 보낼지"를 위한 토큰 저장만 담당한다.
"""

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.push_token import PushPlatform, PushToken
from app.models.user import User


def upsert_token(db: Session, user: User, push_token: str, platform: PushPlatform) -> PushToken:
    """푸시 토큰을 등록한다.

    **사용자당 하나만 유지한다.** 재설치·재로그인으로 토큰이 바뀌면 새 값이
    이전 값을 덮어쓴다 — 여러 기기를 동시에 추적하는 건 지금 스코프가 아니다.
    """
    existing = db.scalar(select(PushToken).where(PushToken.user_id == user.id))
    if existing is not None:
        existing.push_token = push_token
        existing.platform = platform
        db.commit()
        db.refresh(existing)
        return existing

    token = PushToken(user_id=user.id, push_token=push_token, platform=platform)
    db.add(token)
    db.commit()
    db.refresh(token)
    return token
