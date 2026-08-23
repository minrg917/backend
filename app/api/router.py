"""전체 라우터를 한곳에 모은다.

새 도메인 라우터를 추가할 때는 여기에 include_router를 한 줄 추가한다.
"""

from fastapi import APIRouter

from app.api.routers import auth, health, onboarding, stores, users

api_router = APIRouter()
api_router.include_router(health.router)
api_router.include_router(onboarding.router)
api_router.include_router(auth.router)
api_router.include_router(stores.router)
api_router.include_router(users.router)
