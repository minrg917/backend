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
    NAVER_CLIENT_ID: str = ""
    NAVER_CLIENT_SECRET: str = ""
    KAKAO_REST_API_KEY: str = ""
    # 외부 API 호출 타임아웃(초). 한쪽이 느려도 검색 전체가 지연되지 않게 짧게 잡는다.
    EXTERNAL_API_TIMEOUT_SECONDS: float = 3.0

    @property
    def database_url(self) -> str:
        return (
            f"mysql+pymysql://{self.DB_USER}:{self.DB_PASSWORD}"
            f"@{self.DB_HOST}:{self.DB_PORT}/{self.DB_NAME}?charset=utf8mb4"
        )

    @property
    def naver_search_enabled(self) -> bool:
        return bool(self.NAVER_CLIENT_ID and self.NAVER_CLIENT_SECRET)

    @property
    def kakao_search_enabled(self) -> bool:
        return bool(self.KAKAO_REST_API_KEY)

    @property
    def cors_origin_list(self) -> list[str]:
        return [origin.strip() for origin in self.CORS_ORIGINS.split(",") if origin.strip()]


@lru_cache
def get_settings() -> Settings:
    """설정 객체를 반환한다. lru_cache로 프로세스당 한 번만 읽는다."""
    return Settings()


settings = get_settings()
