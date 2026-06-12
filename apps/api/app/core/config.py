from functools import lru_cache
from decimal import Decimal
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
    risk_data_stale_after_minutes: int = Field(default=60, ge=1)
    risk_max_spread_percent: Decimal = Field(default=Decimal("5.0"), gt=0)
    risk_max_24h_volatility_percent: Decimal = Field(default=Decimal("12.0"), gt=0)
    risk_max_7d_volatility_percent: Decimal = Field(default=Decimal("25.0"), gt=0)
    risk_fomo_lookback_minutes: int = Field(default=180, ge=1)
    risk_fomo_rise_percent: Decimal = Field(default=Decimal("6.0"), gt=0)
    risk_max_daily_loss_usd: Decimal = Field(default=Decimal("30.0"), gt=0)
    risk_max_weekly_loss_usd: Decimal = Field(default=Decimal("60.0"), gt=0)
    risk_min_expected_net_gain_percent: Decimal = Field(default=Decimal("0.0"), ge=0)
    risk_ml_model_enabled: bool = True
    risk_ml_decision_mode: Literal["advisory", "hard_veto"] = "advisory"
    risk_ml_min_probability: float = Field(default=0.50, ge=0.0, le=1.0)
    risk_ml_model_path: str = "data/models/champion_model.pkl"

    strategy_name: str = "strategy_v2"
    auto_trading_enabled: bool = True
    auto_trading_mode: Literal["diagnostic", "paper"] = "diagnostic"
    hold_notification_cooldown_minutes: int = Field(default=360, ge=0)

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
    global_xag_source_priority: str = "yahoo-si-f,gold-api-xag-usd,metals-dev"
    global_xag_freshness_minutes: int = Field(default=90, ge=1)

    # Yahoo Finance Settings
    yahoo_chart_base_url: str = "https://query1.finance.yahoo.com/v8/finance/chart"
    yahoo_xag_usd_timeout_seconds: float = Field(default=10, gt=0)
    yahoo_xag_usd_retries: int = Field(default=2, ge=0)
    yahoo_xag_usd_backoff_seconds: float = Field(default=1, ge=0)

    # Gold API Settings
    gold_api_xag_usd_enabled: bool = True
    gold_api_xag_usd_url: str = "https://api.gold-api.com/price/XAG"
    gold_api_xag_usd_timeout_seconds: float = Field(default=10, gt=0)

    metals_dev_api_key: str = ""
    metals_dev_spot_url: str = "https://api.metals.dev/v1/metal/spot"
    metals_dev_timeout_seconds: float = Field(default=10, gt=0)
    tcmb_today_xml_url: str = "https://www.tcmb.gov.tr/kurlar/today.xml"
    fed_rss_enabled: bool = True
    fed_rss_url: str = "https://www.federalreserve.gov/feeds/press_monetary.xml"
    bls_api_key: str = ""
    fred_api_key: str = ""
    fred_api_base_url: str = "https://api.stlouisfed.org/fred"
    fred_series_ids: str = "CPIAUCSL,PPIACO,UNRATE,FEDFUNDS,DGS10,DTWEXBGS"

    # DeepSeek API Settings
    deepseek_api_key: str = ""
    deepseek_base_url: str = "https://api.deepseek.com/v1"
    deepseek_daily_budget_usd: Decimal = Field(default=Decimal("1.00"), gt=0)

    # Agent Security Settings
    agent_api_token: str = ""

    # Telegram Bot Settings
    telegram_bot_token: str = ""
    telegram_chat_id: int = 0
    telegram_bot_mode: str = "webhook"
    telegram_webhook_url: str = ""

    agent_news_model: str = "deepseek-v4-flash"
    agent_report_model: str = "deepseek-v4-flash"
    agent_risk_model: str = "deepseek-v4-pro"
    agent_hermes_model: str = "deepseek-v4-pro"

    hermes_veto_threshold: Decimal = Field(default=Decimal("-0.45"))
    hermes_boost_threshold: Decimal = Field(default=Decimal("0.40"))
    weight_global_authority: Decimal = Field(default=Decimal("0.5"))
    weight_local_expert: Decimal = Field(default=Decimal("0.3"))
    weight_local_forum: Decimal = Field(default=Decimal("0.2"))


@lru_cache
def get_settings() -> Settings:
    return Settings()
