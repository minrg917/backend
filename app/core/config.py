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

    @property
    def database_url(self) -> str:
        return (
            f"mysql+pymysql://{self.DB_USER}:{self.DB_PASSWORD}"
            f"@{self.DB_HOST}:{self.DB_PORT}/{self.DB_NAME}?charset=utf8mb4"
        )

    @property
    def cors_origin_list(self) -> list[str]:
        return [origin.strip() for origin in self.CORS_ORIGINS.split(",") if origin.strip()]


@lru_cache
def get_settings() -> Settings:
    """설정 객체를 반환한다. lru_cache로 프로세스당 한 번만 읽는다."""
    return Settings()


settings = get_settings()
