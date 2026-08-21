"""온보딩/약관 콘텐츠 (API명세서 1.1)."""

from fastapi import APIRouter

from app.schemas.onboarding import OnboardingResponse
from app.services import onboarding as onboarding_service

router = APIRouter(tags=["onboarding"])


@router.get("/onboarding", response_model=OnboardingResponse)
def get_onboarding() -> OnboardingResponse:
    """온보딩 4단계와 약관 목록을 돌려준다. 로그인 전 화면이라 인증 불필요."""
    return onboarding_service.get_onboarding_content()
