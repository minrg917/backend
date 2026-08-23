"""애플리케이션 설정.

값은 환경변수 또는 프로젝트 루트의 `.env` 파일에서 읽는다.
새 설정을 추가할 때는 `.env.example`에도 함께 추가한다.
"""

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # 애플리케이션
    APP_NAME: str = "사릴스(SARILS) API"
    DEBUG: bool = False

    # 데이터베이스
    DB_HOST: str = "localhost"
    DB_PORT: int = 3306
    DB_USER: str = "sarils"
    DB_PASSWORD: str = "sarils"
    DB_NAME: str = "sarils"

    # CORS — 프론트 개발 서버 주소를 쉼표로 구분해 넣는다
    CORS_ORIGINS: str = "http://localhost:3000,http://localhost:5173"

    # JWT — 운영 환경에서는 반드시 .env 로 덮어쓴다
    JWT_SECRET_KEY: str = "dev-only-secret-do-not-use-in-production"
    JWT_ALGORITHM: str = "HS256"
    # 액세스 토큰 만료(분). API명세서 1.3의 expires_in(3600초)과 맞춰 60분.
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60
    # 리프레시 토큰 만료(일)
    REFRESH_TOKEN_EXPIRE_DAYS: int = 14

    # 외부 장소 검색 API (2.1 가게 통합검색)
    # 키가 비어 있으면 해당 출처는 검색에서 조용히 제외된다 — 로컬/CI에서 키 없이도 서버가 뜬다.
    #
    # NAVER 지역검색은 2026-06-25 NAVER API HUB(NCP)로 이관됐고 2026-07-31부로
    # developers.naver.com 신규 발급이 종료됐다. 그래서 구방식(openapi.naver.com +
    # X-Naver-Client-Id/Secret)이 아니라 NCP API Gateway 방식을 쓴다.
    # 엔드포인트는 NCP 콘솔에서 확인한 값을 넣는다(서비스별 경로가 달라 하드코딩하지 않는다).
    NAVER_SEARCH_LOCAL_URL: str = ""
    NAVER_API_KEY_ID: str = ""  # X-NCP-APIGW-API-KEY-ID
    NAVER_API_KEY: str = ""  # X-NCP-APIGW-API-KEY
    KAKAO_REST_API_KEY: str = ""
    # 외부 API 호출 타임아웃(초). 한쪽이 느려도 검색 전체가 지연되지 않게 짧게 잡는다.
    EXTERNAL_API_TIMEOUT_SECONDS: float = 3.0

    # AI 서버 — 스펙 미확정. 비어 있으면 기획 생성이 임시 뼈대를 돌려준다.
    AI_SERVER_URL: str = ""
    AI_SERVER_API_KEY: str = ""
    AI_REQUEST_TIMEOUT_SECONDS: float = 30.0

    # 파일 저장소 — 배포 시 "s3" 구현을 추가하고 이 값만 바꾼다
    STORAGE_BACKEND: str = "local"
    # 로컬 저장 루트(.gitignore에 포함). 상대 경로면 프로젝트 루트 기준.
    MEDIA_ROOT: str = "media"
    # 정적 서빙 경로와, 응답 URL을 만들 때 앞에 붙일 주소.
    # 배포 시 MEDIA_BASE_URL을 실제 도메인(또는 S3/CDN 주소)으로 바꾼다.
    MEDIA_URL_PATH: str = "/media"
    MEDIA_BASE_URL: str = "http://localhost:8000"

    # 업로드 제한 — 사진은 원본을 그대로 받되 상식적인 상한을 둔다
    MAX_UPLOAD_SIZE_MB: int = 10
    ALLOWED_IMAGE_TYPES: str = "image/jpeg,image/png,image/webp,image/heic"
    # 촬영본(영상)은 사진보다 훨씬 크다. 사진 제한을 그대로 쓰면 정상 촬영분도 막힌다.
    MAX_VIDEO_UPLOAD_SIZE_MB: int = 200
    ALLOWED_VIDEO_TYPES: str = "video/mp4,video/quicktime,video/x-m4v,video/webm"

    @property
    def database_url(self) -> str:
        return (
            f"mysql+pymysql://{self.DB_USER}:{self.DB_PASSWORD}"
            f"@{self.DB_HOST}:{self.DB_PORT}/{self.DB_NAME}?charset=utf8mb4"
        )

    @property
    def naver_search_enabled(self) -> bool:
        return bool(self.NAVER_SEARCH_LOCAL_URL and self.NAVER_API_KEY_ID and self.NAVER_API_KEY)

    @property
    def kakao_search_enabled(self) -> bool:
        return bool(self.KAKAO_REST_API_KEY)

    @property
    def max_upload_size_bytes(self) -> int:
        return self.MAX_UPLOAD_SIZE_MB * 1024 * 1024

    @property
    def allowed_image_type_set(self) -> set[str]:
        return {
            item.strip().lower() for item in self.ALLOWED_IMAGE_TYPES.split(",") if item.strip()
        }

    @property
    def max_video_upload_size_bytes(self) -> int:
        return self.MAX_VIDEO_UPLOAD_SIZE_MB * 1024 * 1024

    @property
    def allowed_video_type_set(self) -> set[str]:
        return {
            item.strip().lower() for item in self.ALLOWED_VIDEO_TYPES.split(",") if item.strip()
        }

    @property
    def cors_origin_list(self) -> list[str]:
        return [origin.strip() for origin in self.CORS_ORIGINS.split(",") if origin.strip()]


@lru_cache
def get_settings() -> Settings:
    """설정 객체를 반환한다. lru_cache로 프로세스당 한 번만 읽는다."""
    return Settings()


settings = get_settings()
