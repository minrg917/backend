"""AI 트렌드 클러스터를 `video_formats`에 반영한다.

`scripts/seed_video_formats.py`가 예고한 자리다 — "실제 포맷 발굴과 랭킹은 AI 서버가
담당하며, 연동되면 AI가 내려준 목록이 같은 방식으로 쌓인다". 그 연동이 여기다.

**왜 필요한가.** 지금 `video_formats`에 쌓이는 행은 R06 추천을 수락할 때 생기는
`internal://editing-template/{id}/v{version}` 뿐이다. 그건 AI 서버 내부 자산 주소라
앱에서 썸네일도 못 만들고 재생도 안 된다 — 5.1 피드가 요구하는 "따라 만들 원본
영상"과 성격이 다르다. 트렌드 클러스터가 그 원본을 갖고 있다.

**중복 기준은 `trend_challenge_id`다.** `reference_url`이 아니다 — 챌린지의 대표
영상이 교체되면 URL이 바뀌는데, URL 기준이면 같은 챌린지가 두 행이 된다.
"""

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.video_format import VideoFormat
from app.services import ai_client


def sync_trend_formats(db: Session) -> tuple[int, int, int]:
    """트렌드 클러스터를 받아 포맷 카탈로그에 반영한다.

    (추가, 갱신, 건너뜀) 개수를 돌려준다. **여러 번 돌려도 안전하다**(멱등).

    대표 영상 URL이 없는 챌린지는 건너뛴다 — 피드 카드는 영상 없이 성립하지 않고,
    빈 값으로 행을 만들면 앱에 재생 안 되는 카드가 그대로 노출된다.
    """
    challenges = ai_client.list_trend_challenges()

    added = updated = skipped = 0
    for challenge in challenges:
        reference_url = challenge.representative_youtube_url
        if not reference_url:
            skipped += 1
            continue

        video_format = db.scalar(
            select(VideoFormat).where(VideoFormat.trend_challenge_id == challenge.id)
        )
        if video_format is None:
            # 트렌드 연동 전에 같은 영상이 다른 경로로 들어와 있을 수 있다.
            # `reference_url`이 UNIQUE라 그대로 새 행을 만들면 실패한다 — 붙여서 쓴다.
            video_format = db.scalar(
                select(VideoFormat).where(VideoFormat.reference_url == reference_url)
            )

        if video_format is None:
            db.add(
                VideoFormat(
                    format_title=challenge.name,
                    reference_url=reference_url,
                    guide_video_url=challenge.guide_youtube_url,
                    source_platform="YOUTUBE",
                    trend_challenge_id=challenge.id,
                    trend_rank=challenge.rank,
                )
            )
            added += 1
            continue

        # 이름·URL·순위는 AI가 갱신하는 값이라 매번 덮어쓴다.
        # 나머지 메타데이터(유형·소요시간·난이도·얼굴노출)는 트렌드 클러스터에 없어
        # 건드리지 않는다 — 사람이 채워 둔 값을 지우지 않기 위해서다.
        video_format.format_title = challenge.name
        video_format.reference_url = reference_url
        video_format.guide_video_url = challenge.guide_youtube_url
        video_format.source_platform = "YOUTUBE"
        video_format.trend_challenge_id = challenge.id
        video_format.trend_rank = challenge.rank
        updated += 1

    db.commit()
    return added, updated, skipped
