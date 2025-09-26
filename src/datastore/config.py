from pydantic_settings import BaseSettings
from functools import lru_cache


class Settings(BaseSettings):
    DATABASE_URL: str
    ADMIN_DATABASE_URL: str
    APP_PORT: int = 8081
    ALEMBIC_INI: str = "alembic.ini"

    @property
    def database_url(self) -> str:
        return self.DATABASE_URL

    class Config:
        env_file = ".env"
        case_sensitive = False


@lru_cache()
def get_settings() -> Settings:
    return Settings()
