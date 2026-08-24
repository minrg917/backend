"""개발·데모용 숏폼 포맷 시드.

    poetry run python -m scripts.seed_video_formats

**마이그레이션에 심지 않는 이유**: 포맷은 스키마가 아니라 콘텐츠다. 포맷을 추가할
때마다 마이그레이션 파일이 쌓이면 스키마 변경 이력과 섞여 읽기 어려워진다.

**이 데이터는 임시다.** 실제 포맷 발굴과 랭킹은 AI 서버가 담당하며, 연동되면
AI가 내려준 목록이 같은 방식(`reference_url` 기준 중복 제거)으로 쌓인다.
`reference_url`이 UNIQUE라 여러 번 실행해도 중복이 생기지 않는다.
"""

import json
from pathlib import Path

from sqlalchemy import select

from app.db.session import SessionLocal
from app.models.video_format import VideoFormat

SEED_FILE = Path(__file__).resolve().parent.parent / "data" / "video_formats.json"


def seed() -> tuple[int, int]:
    """시드 파일을 읽어 없는 포맷만 넣는다. (추가, 건너뜀) 개수를 돌려준다."""
    records = json.loads(SEED_FILE.read_text(encoding="utf-8"))

    added = skipped = 0
    with SessionLocal() as db:
        for record in records:
            exists = db.scalar(
                select(VideoFormat.id).where(VideoFormat.reference_url == record["reference_url"])
            )
            if exists:
                skipped += 1
                continue
            db.add(VideoFormat(**record))
            added += 1
        db.commit()
    return added, skipped


if __name__ == "__main__":
    added, skipped = seed()
    print(f"포맷 시드 완료 — 추가 {added}건, 이미 있어 건너뜀 {skipped}건")
