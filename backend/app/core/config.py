from functools import lru_cache

from pydantic import AliasChoices, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = Field(
        default="sqlite+aiosqlite:///./dev.db",
        validation_alias=AliasChoices("GENPANO_DATABASE_URL", "DATABASE_URL"),
    )
    redis_url: str = Field(
        default="redis://localhost:6379/0",
        validation_alias=AliasChoices("GENPANO_REDIS_URL", "REDIS_URL"),
    )


@lru_cache
def get_settings() -> Settings:
    return Settings()
