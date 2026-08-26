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

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.models.video_format import VideoFormat
from app.services import ai_client


def _apply_ai_metadata(video_format: VideoFormat, challenge: ai_client.TrendChallenge) -> None:
    """Apply only values the AI actually supplied; never erase curated data with null."""

    for field in (
        "format_type",
        "expected_duration_sec",
        "shooting_difficulty",
        "requires_face",
    ):
        value = getattr(challenge, field)
        if value is not None:
            setattr(video_format, field, value)


def _link_editing_template(
    db: Session, video_format: VideoFormat, challenge: ai_client.TrendChallenge
) -> None:
    """승인된 챌린지의 편집 템플릿을 연결한다.

    `editing_template_id`/`version`은 이 챌린지의 촬영가이드 템플릿이 AI 쪽에서
    승인 완료됐을 때만 채워진다(2026-08-26 확인). 이 값이 채워져야 5.1에서 고른
    포맷으로 실제 기획 생성(`get_shooting_guide`)이 가능해진다 — 그 전엔
    `editing_template_id`가 없어 `NotImplementedError`로 막힌다.

    **같은 (template_id, version) 쌍을 R06 추천이 만든 행이 이미 갖고 있을 수
    있다** — 같은 실제 챌린지가 서로 다른 두 경로(트렌드 동기화 / R06 추천 수락)로
    각각 행을 만들었기 때문이다. 이 쌍엔 UNIQUE 제약이 있어 트렌드 행에도 그대로
    쓰면 커밋이 실패한다(2026-08-26 실서버에서 실제로 발생). 이미 다른 행이 그
    쌍을 갖고 있으면, 트렌드 행엔 값을 넣지 않고 **그 다른 행을 대신 활성화**한다
    — 실제로 프로젝트가 참조하는 건 그 행이기 때문이다.
    """
    template_id = challenge.editing_template_id
    version = challenge.editing_template_version
    if template_id is None or version is None:
        return

    conditions = [
        VideoFormat.editing_template_id == template_id,
        VideoFormat.editing_template_version == version,
    ]
    if video_format.id is not None:
        conditions.append(VideoFormat.id != video_format.id)
    existing_owner = db.scalar(select(VideoFormat).where(*conditions))
    if existing_owner is not None:
        existing_owner.is_active = True
        return

    video_format.editing_template_id = template_id
    video_format.editing_template_version = version


def sync_trend_formats(db: Session) -> tuple[int, int, int]:
    """트렌드 클러스터를 받아 포맷 카탈로그에 반영한다.

    (추가, 갱신, 건너뜀) 개수를 돌려준다. **여러 번 돌려도 안전하다**(멱등).

    대표 영상 URL이 없는 챌린지는 건너뛴다 — 피드 카드는 영상 없이 성립하지 않고,
    빈 값으로 행을 만들면 앱에 재생 안 되는 카드가 그대로 노출된다.

    **AI 목록에서 완전히 빠진 챌린지는 비활성화한다.** 이 루프는 "지금 응답에
    있는 것"만 갱신하므로, AI가 목록 자체를 줄이면(예: 48건 → 3건) 빠진 챌린지의
    예전 `is_active` 값이 그대로 남는다 — 그래서 루프 뒤에 마무리 반영이 따로
    필요하다(2026-08-26 실서버에서 실제로 겪음: 응답이 48건에서 3건으로 줄었는데
    나머지 45건이 활성 상태로 남아 있었다).
    """
    challenges = ai_client.list_trend_challenges()
    seen_challenge_ids = [challenge.id for challenge in challenges]

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
            video_format = VideoFormat(
                format_title=challenge.name,
                reference_url=reference_url,
                guide_video_url=challenge.guide_youtube_url,
                source_platform="YOUTUBE",
                trend_challenge_id=challenge.id,
                trend_rank=challenge.rank,
            )
            _apply_ai_metadata(video_format, challenge)
            _link_editing_template(db, video_format, challenge)
            # 트렌드 인기 여부(challenge.active)가 아니라 "촬영가이드 템플릿이
            # 실제로 있는가"로 활성화 여부를 정한다(2026-08-26 정정). 발굴은
            # 됐지만 아직 승인 전인 챌린지는 트렌드로는 active여도 고르면
            # 기획 생성이 막힌다 — 반대로 승인은 끝났지만 트렌드 순위에서
            # 내려간 챌린지는 여전히 정상 작동한다. 그래서 판단 기준은
            # "이 포맷을 지금 골라도 되는가"인 template 존재 여부여야 한다.
            video_format.is_active = video_format.editing_template_id is not None
            db.add(video_format)
            added += 1
            continue

        # AI가 제공한 값은 매번 갱신하되, null은 사람이 채운 값을 지우지 않는다.
        video_format.format_title = challenge.name
        video_format.reference_url = reference_url
        video_format.guide_video_url = challenge.guide_youtube_url
        video_format.source_platform = "YOUTUBE"
        video_format.trend_challenge_id = challenge.id
        video_format.trend_rank = challenge.rank
        _apply_ai_metadata(video_format, challenge)
        _link_editing_template(db, video_format, challenge)
        video_format.is_active = video_format.editing_template_id is not None
        updated += 1

    # AI가 응답을 준 경우(연동 꺼짐이 아닌 경우)에만 마무리 비활성화를 한다 —
    # AI_SERVER_URL이 없어 challenges가 빈 목록일 때 트렌드 행을 전부 꺼버리면
    # 안 된다.
    if ai_client.is_enabled():
        reconcile = update(VideoFormat).where(VideoFormat.trend_challenge_id.is_not(None))
        if seen_challenge_ids:
            reconcile = reconcile.where(VideoFormat.trend_challenge_id.not_in(seen_challenge_ids))
        db.execute(reconcile.values(is_active=False))

    db.commit()
    return added, updated, skipped
