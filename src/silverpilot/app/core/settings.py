from functools import lru_cache
from typing import Literal
from uuid import UUID

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from silverpilot.app.domain.enums import (
    DelayPolicy,
    ExecutionQuoteSelectionPolicy,
    ExecutionSourcePolicy,
    IndicatorSourcePolicy,
)


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
    deployed_sha: str | None = None

    runtime_enabled: bool = False
    runtime_account_id: UUID | None = None
    runtime_bank_instrument_id: UUID | None = None
    runtime_execution_instrument_id: UUID | None = None
    runtime_reference_instrument_id: UUID | None = None
    runtime_strategy_id: UUID | None = None
    runtime_reference_source: str | None = None
    runtime_fx_source: str | None = None
    runtime_fx_pair: str | None = None
    runtime_reference_timeframe: str = "4h"
    indicator_source_policy: IndicatorSourcePolicy = IndicatorSourcePolicy.REFERENCE_MARKET_FIRST
    execution_source_policy: ExecutionSourcePolicy = ExecutionSourcePolicy.ACCOUNT_BOUND_BANK_QUOTE
    reference_delay_policy: DelayPolicy = DelayPolicy.PROVIDER_DELAYED
    reference_ingestion_delay_seconds: int = Field(default=60, ge=0)
    execution_quote_selection_policy: ExecutionQuoteSelectionPolicy = (
        ExecutionQuoteSelectionPolicy.LATEST_BEFORE_OR_AT_DECISION
    )
    max_quote_lag_seconds: int = Field(default=300, ge=0)
    runtime_collect_interval_seconds: int = Field(default=300, ge=1)
    runtime_bar_timeframe: str = "5m"
    runtime_reference_refresh_enabled: bool = True
    runtime_reference_refresh_period: str = "5d"
    runtime_reference_refresh_interval_seconds: int = Field(default=1800, ge=0)
    runtime_reference_max_data_age_seconds: int = Field(default=21600, ge=1)
    runtime_warmup_bars: int = Field(default=201, ge=1)
    runtime_exit_stop_loss_pct: float = Field(default=-0.03, le=0)
    runtime_exit_take_profit_pct: float = Field(default=0.05, ge=0)
    runtime_exit_high_volatility_fraction: float = Field(default=0.5, ge=0, le=1)

    @field_validator(
        "runtime_account_id",
        "runtime_bank_instrument_id",
        "runtime_execution_instrument_id",
        "runtime_reference_instrument_id",
        "runtime_strategy_id",
        mode="before",
    )
    @classmethod
    def empty_uuid_is_none(cls, value: object) -> object:
        if value == "":
            return None
        return value

    @field_validator(
        "runtime_reference_source",
        "runtime_fx_source",
        "runtime_fx_pair",
        mode="before",
    )
    @classmethod
    def empty_string_is_none(cls, value: object) -> object:
        if value == "":
            return None
        return value


@lru_cache
def get_settings() -> Settings:
    return Settings()
