"""온보딩/약관 콘텐츠 스키마 (API명세서 1.1)."""

from app.schemas.common import BaseSchema


class OnboardingStep(BaseSchema):
    order: int
    title: str
    description: str


class TermsInfo(BaseSchema):
    version: str
    required: list[str]
    optional: list[str]


class OnboardingResponse(BaseSchema):
    onboarding_steps: list[OnboardingStep]
    terms: TermsInfo
