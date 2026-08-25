"""AI 트렌드 클러스터 → `video_formats` 동기화 테스트."""

from typing import Any

import httpx
import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.video_format import VideoFormat
from app.services import ai_client
from app.services.trend_format import sync_trend_formats

# AI 레포 `exports/trendcluster.json` 원문 형태 그대로.
TRENDCLUSTER: dict[str, Any] = {
    "generated_at": "2026-08-24T22:00:00.000Z",
    "count": 3,
    "results": [
        {
            "id": "jujutsu_transition",
            "rank": 1,
            "name": "주술회전 트랜지션",
            "representative_youtube_url": "https://www.youtube.com/shorts/Yc7ZjC0n7oY?si=abc",
            "guide_youtube_url": "https://www.youtube.com/shorts/Yc7ZjC0n7oY?si=abc",
        },
        {
            "id": "cafe_recommendation_reels",
            "rank": 2,
            "name": "카페 추천 리뷰 릴스",
            "representative_youtube_url": "https://www.youtube.com/shorts/OWnLiuJU8Ks",
            "guide_youtube_url": "https://www.youtube.com/shorts/OWnLiuJU8Ks",
        },
        {
            "id": "otsukare_summer_challenge",
            "rank": 3,
            "name": "오츠카레 썸머 챌린지",
            "representative_youtube_url": "https://www.youtube.com/shorts/e-dU9yQfmik",
            "guide_youtube_url": "https://www.youtube.com/shorts/e-dU9yQfmik",
        },
    ],
}


def _stub_ai(monkeypatch: pytest.MonkeyPatch, payload: dict[str, Any]) -> None:
    def fake_request(method: str, url: str, **kwargs: Any) -> httpx.Response:
        del kwargs
        return httpx.Response(200, json=payload, request=httpx.Request(method, url))

    monkeypatch.setattr(settings, "AI_SERVER_URL", "http://ai.internal")
    monkeypatch.setattr(settings, "AI_SERVER_API_KEY", "shared-secret")
    monkeypatch.setattr(httpx, "request", fake_request)


def test_returns_empty_without_ai_server(monkeypatch: pytest.MonkeyPatch) -> None:
    """가짜 URL을 만들지 않는다 — 재생되지 않는 카드가 피드에 나가면 안 된다."""
    monkeypatch.setattr(settings, "AI_SERVER_URL", "")
    assert ai_client.list_trend_challenges() == []


def test_sync_loads_trend_cluster(db_session: Session, monkeypatch: pytest.MonkeyPatch) -> None:
    _stub_ai(monkeypatch, TRENDCLUSTER)

    added, updated, skipped = sync_trend_formats(db_session)
    assert (added, updated, skipped) == (3, 0, 0)

    formats = list(db_session.scalars(select(VideoFormat).order_by(VideoFormat.trend_rank)))
    assert [f.format_title for f in formats] == [
        "주술회전 트랜지션",
        "카페 추천 리뷰 릴스",
        "오츠카레 썸머 챌린지",
    ]
    first = formats[0]
    assert first.reference_url == "https://www.youtube.com/shorts/Yc7ZjC0n7oY?si=abc"
    assert first.guide_video_url == "https://www.youtube.com/shorts/Yc7ZjC0n7oY?si=abc"
    assert first.source_platform == "YOUTUBE"
    assert first.trend_challenge_id == "jujutsu_transition"
    assert first.is_active is True


def test_sync_is_idempotent_and_updates(
    db_session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    _stub_ai(monkeypatch, TRENDCLUSTER)
    sync_trend_formats(db_session)

    moved = {
        **TRENDCLUSTER,
        "results": [
            {
                **TRENDCLUSTER["results"][0],
                "rank": 5,
                "name": "주술회전 트랜지션 (개정)",
                "representative_youtube_url": "https://www.youtube.com/shorts/NEWvideoid1",
            },
            *TRENDCLUSTER["results"][1:],
        ],
    }
    _stub_ai(monkeypatch, moved)
    added, updated, skipped = sync_trend_formats(db_session)
    assert (added, updated, skipped) == (0, 3, 0)

    changed = db_session.scalar(
        select(VideoFormat).where(VideoFormat.trend_challenge_id == "jujutsu_transition")
    )
    assert changed is not None
    # 대표 영상이 교체돼도 같은 행이 갱신된다(URL 기준이면 새 행이 생긴다).
    assert changed.reference_url == "https://www.youtube.com/shorts/NEWvideoid1"
    assert changed.format_title == "주술회전 트랜지션 (개정)"
    assert changed.trend_rank == 5
    assert len(list(db_session.scalars(select(VideoFormat)))) == 3


def test_sync_skips_challenge_without_video(
    db_session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    _stub_ai(
        monkeypatch,
        {
            "generated_at": None,
            "count": 1,
            "results": [
                {
                    "id": "no_video",
                    "rank": 1,
                    "name": "영상 없는 챌린지",
                    "representative_youtube_url": None,
                    "guide_youtube_url": None,
                }
            ],
        },
    )

    added, updated, skipped = sync_trend_formats(db_session)
    assert (added, updated, skipped) == (0, 0, 1)
    assert list(db_session.scalars(select(VideoFormat))) == []


def test_sync_adopts_existing_row_with_same_url(
    db_session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`reference_url`이 UNIQUE라 새 행을 만들면 실패한다. 기존 행을 이어받는다."""
    existing = VideoFormat(
        format_title="예전 이름",
        reference_url="https://www.youtube.com/shorts/OWnLiuJU8Ks",
        source_platform="YOUTUBE",
        expected_duration_sec=25,
        shooting_difficulty="하",
    )
    db_session.add(existing)
    db_session.commit()

    _stub_ai(monkeypatch, TRENDCLUSTER)
    added, updated, skipped = sync_trend_formats(db_session)

    assert (added, updated, skipped) == (2, 1, 0)
    db_session.refresh(existing)
    assert existing.trend_challenge_id == "cafe_recommendation_reels"
    assert existing.format_title == "카페 추천 리뷰 릴스"
    # 트렌드 클러스터에 없는 메타데이터는 지우지 않는다.
    assert existing.expected_duration_sec == 25
    assert existing.shooting_difficulty == "하"


def test_trending_sort_uses_trend_rank(db_session: Session) -> None:
    """`sort=trending`이 트렌드 순위를 따르고, 순위 없는 포맷은 뒤로 간다."""
    from app.schemas.video_format import FormatSort
    from app.services.video_format import list_formats

    db_session.add_all(
        [
            VideoFormat(
                format_title="순위 없음(R06 템플릿)",
                reference_url="internal://editing-template/tpl/v1",
                editing_template_id="tpl",
                editing_template_version=1,
            ),
            VideoFormat(
                format_title="2위",
                reference_url="https://youtu.be/rank2",
                trend_challenge_id="rank2",
                trend_rank=2,
            ),
            VideoFormat(
                format_title="1위",
                reference_url="https://youtu.be/rank1",
                trend_challenge_id="rank1",
                trend_rank=1,
            ),
        ]
    )
    db_session.commit()

    trending = list_formats(db_session, sort=FormatSort.TRENDING)
    assert [f.format_title for f in trending] == ["1위", "2위", "순위 없음(R06 템플릿)"]

    # 최신순은 기존 동작 그대로 — 트렌드 순위를 보지 않는다.
    latest = list_formats(db_session, sort=FormatSort.LATEST)
    assert latest[0].format_title == "1위"  # 가장 마지막에 추가된 행
