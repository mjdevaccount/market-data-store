from pydantic import BaseSettings
from functools import lru_cache
import os


class Settings(BaseSettings):
    database_url: str = os.getenv(
        "DATABASE_URL", "postgresql+psycopg://postgres:postgres@localhost:5432/marketdata"
    )
    admin_database_url: str = os.getenv(
        "ADMIN_DATABASE_URL", "postgresql+psycopg://postgres:postgres@localhost:5432/marketdata"
    )
    app_port: int = int(os.getenv("APP_PORT", "8081"))
    admin_token: str = os.getenv("ADMIN_TOKEN", "dev-token-change-in-production")


@lru_cache
def get_settings() -> Settings:
    return Settings()
