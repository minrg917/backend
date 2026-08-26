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
            "format_type": "밈",
            "expected_duration_sec": 10,
            "shooting_difficulty": "중",
            "requires_face": False,
        },
        {
            "id": "cafe_recommendation_reels",
            "rank": 2,
            "name": "카페 추천 리뷰 릴스",
            "representative_youtube_url": "https://www.youtube.com/shorts/OWnLiuJU8Ks",
            "guide_youtube_url": "https://www.youtube.com/shorts/OWnLiuJU8Ks",
            "format_type": "정보형",
            "expected_duration_sec": 13,
            "shooting_difficulty": "중",
            "requires_face": False,
        },
        {
            "id": "otsukare_summer_challenge",
            "rank": 3,
            "name": "오츠카레 썸머 챌린지",
            "representative_youtube_url": "https://www.youtube.com/shorts/e-dU9yQfmik",
            "guide_youtube_url": "https://www.youtube.com/shorts/e-dU9yQfmik",
            "format_type": "챌린지",
            "expected_duration_sec": 12,
            "shooting_difficulty": "중",
            "requires_face": True,
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
    # 아직 컷 분해 템플릿이 없는 챌린지라 비활성이다 — 트렌드 자체는 인기여도
    # 골랐을 때 기획 생성이 안 되면 피드에 노출하면 안 된다.
    assert first.is_active is False
    assert (
        first.format_type,
        first.expected_duration_sec,
        first.shooting_difficulty,
        first.requires_face,
    ) == ("밈", 10, "중", False)


def test_sync_links_editing_template_when_approved(
    db_session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    """승인 완료된 챌린지는 editing_template_id/version이 그대로 연결된다."""
    payload = {
        "results": [
            {
                **TRENDCLUSTER["results"][0],
                "editing_template_id": "gt_jujutsu_transition",
                "editing_template_version": 4,
            }
        ]
    }
    _stub_ai(monkeypatch, payload)

    sync_trend_formats(db_session)

    linked = db_session.scalar(
        select(VideoFormat).where(VideoFormat.trend_challenge_id == "jujutsu_transition")
    )
    assert linked is not None
    assert linked.editing_template_id == "gt_jujutsu_transition"
    assert linked.editing_template_version == 4
    # 템플릿이 있으니 트렌드 인기 여부와 무관하게 활성화된다.
    assert linked.is_active is True


def test_sync_leaves_editing_template_unlinked_when_not_yet_approved(
    db_session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    """승인 전(필드 없음)이면 editing_template_id를 비워둔다 — 지어내지 않는다."""
    _stub_ai(monkeypatch, TRENDCLUSTER)

    sync_trend_formats(db_session)

    linked = db_session.scalar(
        select(VideoFormat).where(VideoFormat.trend_challenge_id == "jujutsu_transition")
    )
    assert linked is not None
    assert linked.editing_template_id is None
    assert linked.editing_template_version is None
    # 발굴은 됐지만 아직 승인 전이라 비활성 — 골라도 기획 생성이 막히는 카드를
    # 피드에 보여주면 안 된다.
    assert linked.is_active is False


def test_sync_activation_follows_template_not_ai_trend_flag(
    db_session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    """활성화 기준은 AI의 트렌드 인기 여부(`active`)가 아니라 템플릿 존재 여부다.

    실측 사례(2026-08-26): 새로 발굴된 챌린지는 트렌드로는 `active: true`인데
    아직 컷 분해 승인 전이고, 반대로 예전에 승인된 챌린지는 트렌드 순위에서는
    `active: false`로 빠졌는데도 템플릿은 여전히 유효했다. `active` 값만 보고
    켜고 끄면 정확히 거꾸로 된 결과가 나온다.
    """
    payload = {
        "results": [
            {
                # 트렌드로는 인기 있음(active=true)이지만 아직 템플릿 없음.
                "id": "trending_not_approved",
                "rank": 1,
                "name": "새로 뜨는 챌린지",
                "representative_youtube_url": "https://youtu.be/trending",
                "active": True,
            },
            {
                # 트렌드 순위에서는 빠졌지만(active=false) 템플릿은 있음.
                "id": "old_but_approved",
                "rank": 99,
                "name": "예전 챌린지",
                "representative_youtube_url": "https://youtu.be/old",
                "active": False,
                "editing_template_id": "gt_old_but_approved",
                "editing_template_version": 4,
            },
        ]
    }
    _stub_ai(monkeypatch, payload)

    sync_trend_formats(db_session)

    trending = db_session.scalar(
        select(VideoFormat).where(VideoFormat.trend_challenge_id == "trending_not_approved")
    )
    old = db_session.scalar(
        select(VideoFormat).where(VideoFormat.trend_challenge_id == "old_but_approved")
    )
    assert trending is not None and trending.is_active is False
    assert old is not None and old.is_active is True


def test_list_trend_challenges_requests_inactive_too(monkeypatch: pytest.MonkeyPatch) -> None:
    """비활성 챌린지도 받아와야 is_active 동기화가 가능하다."""
    captured: dict[str, Any] = {}

    def fake_request(method: str, url: str, **kwargs: Any) -> httpx.Response:
        captured["url"] = url
        return httpx.Response(200, json={"results": []}, request=httpx.Request(method, url))

    monkeypatch.setattr(settings, "AI_SERVER_URL", "http://ai.internal")
    monkeypatch.setattr(httpx, "request", fake_request)

    ai_client.list_trend_challenges()

    assert "include_inactive=true" in captured["url"]


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
    # AI 분석 메타데이터가 기존 행에도 반영된다.
    assert existing.expected_duration_sec == 13
    assert existing.shooting_difficulty == "중"


def test_sync_does_not_erase_curated_metadata_when_ai_omits_it(
    db_session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    existing = VideoFormat(
        format_title="기존 포맷",
        reference_url="https://youtu.be/existing",
        trend_challenge_id="existing",
        format_type="직접 입력",
        expected_duration_sec=25,
        shooting_difficulty="하",
        requires_face=False,
    )
    db_session.add(existing)
    db_session.commit()
    payload = {
        "results": [
            {
                "id": "existing",
                "rank": 1,
                "name": "기존 포맷 갱신",
                "representative_youtube_url": "https://youtu.be/existing",
            }
        ]
    }
    _stub_ai(monkeypatch, payload)

    sync_trend_formats(db_session)
    db_session.refresh(existing)
    assert existing.format_type == "직접 입력"
    assert existing.expected_duration_sec == 25
    assert existing.shooting_difficulty == "하"
    assert existing.requires_face is False


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
