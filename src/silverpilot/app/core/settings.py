from functools import lru_cache
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="SILVERPILOT_", env_file=".env", extra="ignore")

    app_name: str = "SilverPilot"
    environment: Literal["development", "test", "staging", "production"] = "development"
    database_url: str = "sqlite+pysqlite:///./silverpilot.db"
    log_level: str = Field(default="INFO", min_length=1)
    telegram_enabled: bool = False
    telegram_bot_token: str | None = None
    telegram_default_chat_id: str | None = None
    telegram_api_base_url: str = "https://api.telegram.org"


@lru_cache
def get_settings() -> Settings:
    return Settings()
