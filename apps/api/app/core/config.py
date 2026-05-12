from functools import lru_cache
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_env: Literal["local", "test", "production"] = "local"
    app_name: str = "SilverPilot"
    app_debug: bool = False
    initial_balance_usd: float = Field(default=600, gt=0)
    real_money_enabled: bool = False

    postgres_db: str = "silverpilot"
    postgres_user: str = "silverpilot"
    postgres_password: str = "change_me"
    database_url: str = "postgresql+psycopg://silverpilot:change_me@postgres:5432/silverpilot"


@lru_cache
def get_settings() -> Settings:
    return Settings()
