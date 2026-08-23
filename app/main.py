"""FastAPI 애플리케이션 진입점."""

from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.api.router import api_router
from app.core.config import settings
from app.core.error_handlers import register_error_handlers
from app.core.logging import configure_logging, register_request_logging

configure_logging()

app = FastAPI(
    title=settings.APP_NAME,
    debug=settings.DEBUG,
    docs_url="/docs",
    redoc_url="/redoc",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

register_request_logging(app)
register_error_handlers(app)
app.include_router(api_router)

# 로컬 저장소에 올라간 파일을 서빙한다. S3로 전환하면 이 마운트는 필요 없어진다
# (파일 URL이 S3/CDN을 직접 가리키게 되므로).
if settings.STORAGE_BACKEND == "local":
    media_root = Path(settings.MEDIA_ROOT)
    media_root.mkdir(parents=True, exist_ok=True)
    app.mount(settings.MEDIA_URL_PATH, StaticFiles(directory=media_root), name="media")
