"""온보딩 콘텐츠 조회 테스트 (API명세서 1.1)."""

from fastapi.testclient import TestClient


def test_onboarding_returns_four_steps_and_terms(client: TestClient) -> None:
    response = client.get("/onboarding")

    assert response.status_code == 200
    body = response.json()

    # PM 결정(2026-08-21)으로 확정된 4단계
    assert [step["title"] for step in body["onboarding_steps"]] == [
        "숏폼 탐색",
        "태스크 촬영",
        "편집 결과",
        "데이터 분석",
    ]
    assert [step["order"] for step in body["onboarding_steps"]] == [1, 2, 3, 4]
    assert body["terms"]["required"] == ["이용약관", "개인정보 처리방침"]
    assert body["terms"]["optional"] == ["마케팅 수신 동의"]


def test_onboarding_does_not_require_authentication(client: TestClient) -> None:
    assert client.get("/onboarding").status_code == 200
