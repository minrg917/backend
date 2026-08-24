"""온보딩/약관 콘텐츠 (API명세서 1.1).

DB 테이블이 따로 없는 정적 콘텐츠라 코드 상수로 관리한다.
온보딩 4단계 구성은 PM 결정(2026-08-21, `docs/PM_DECISIONS.md`)으로 확정된 값이다.
약관 문구가 바뀌면 `TERMS_VERSION`을 함께 올린다.
"""

from app.schemas.onboarding import OnboardingResponse, OnboardingStep, TermsInfo

TERMS_VERSION = "2026.03"

_ONBOARDING_STEPS = [
    OnboardingStep(order=1, title="숏폼 탐색", description="우리 가게에 맞는 숏폼 포맷을 탐색해요"),
    OnboardingStep(order=2, title="태스크 촬영", description="가이드를 보며 하나씩 촬영해요"),
    OnboardingStep(order=3, title="편집 결과", description="AI가 자동으로 편집한 결과를 확인해요"),
    OnboardingStep(order=4, title="데이터 분석", description="게시 후 성과를 확인해요"),
]

_TERMS = TermsInfo(
    version=TERMS_VERSION,
    required=["이용약관", "개인정보 처리방침"],
    optional=["마케팅 수신 동의"],
)


def get_onboarding_content() -> OnboardingResponse:
    return OnboardingResponse(onboarding_steps=_ONBOARDING_STEPS, terms=_TERMS)
