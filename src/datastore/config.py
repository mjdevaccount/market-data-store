from pydantic import BaseSettings, Field
from functools import lru_cache


class Settings(BaseSettings):
    DATABASE_URL: str = Field(
        default="postgresql+psycopg2://postgres:postgres@localhost:5432/market_data"
    )
    ALEMBIC_INI: str = Field(default="alembic.ini")

    class Config:
        env_file = ".env"
        case_sensitive = False


@lru_cache()
def get_settings() -> Settings:
    return Settings()
