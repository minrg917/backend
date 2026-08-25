"""AI 트렌드 클러스터를 포맷 카탈로그에 반영한다.

    poetry run python -m scripts.sync_trend_formats

`scripts/seed_video_formats.py`(개발용 가짜 시드)를 대체하는 실제 경로다.
**여러 번 돌려도 안전하다** — 챌린지 id 기준으로 없으면 넣고 있으면 갱신한다.

AI 서버가 설정돼 있지 않으면(`AI_SERVER_URL` 비어 있음) 아무것도 하지 않는다.
"""

from app.core.config import settings
from app.db.session import SessionLocal
from app.services.trend_format import sync_trend_formats


def main() -> None:
    if not settings.AI_SERVER_URL:
        print("AI_SERVER_URL이 비어 있어 동기화할 것이 없습니다.")
        return

    with SessionLocal() as db:
        added, updated, skipped = sync_trend_formats(db)
    print(f"트렌드 포맷 동기화 완료 — 추가 {added}건, 갱신 {updated}건, 건너뜀 {skipped}건")


if __name__ == "__main__":
    main()
