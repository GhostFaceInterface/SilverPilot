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

    collector_interval_seconds: int = Field(default=900, ge=300)
    collector_user_agent: str = "SilverPilot/0.1 public-source paper-trading collector"
    kuveyt_silver_url: str = (
        "https://www.kuveytturk.com.tr/kendim-icin/yatirim-urunleri/"
        "hazine-urunleri/canli-gumus-fiyatlari-ve-gram-gumus-hesaplama"
    )
    stooq_xag_usd_url: str = "https://stooq.com/q/l/?s=xagusd&f=sd2t2ohlcv&h&e=csv"
    tcmb_today_xml_url: str = "https://www.tcmb.gov.tr/kurlar/today.xml"
    bls_api_key: str = ""
    fred_api_key: str = ""


@lru_cache
def get_settings() -> Settings:
    return Settings()
