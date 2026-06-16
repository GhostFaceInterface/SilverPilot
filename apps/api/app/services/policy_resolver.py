from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models import SourceProfile, StrategyPolicy

DEFAULT_TIMEFRAME_ROLES = {"trend": "1d", "entry": "1h", "execution": "5m"}


DEFAULT_SOURCE_PROFILES = (
    {
        "source_key": "kuveyt-public-silver-page",
        "role": "execution_price",
        "priority": 10,
        "enabled": True,
        "stale_after_minutes": 60,
        "market_calendar": "bank_trading",
        "reliability_weight": Decimal("1.0000"),
        "details_json": {"collector_name": "kuveyt_public_silver", "asset_symbol": "XAG_GRAM"},
    },
    {
        "source_key": "global-xag-usd",
        "role": "trend_cross_check",
        "priority": 20,
        "enabled": True,
        "stale_after_minutes": 90,
        "market_calendar": "comex",
        "reliability_weight": Decimal("0.8000"),
        "details_json": {"sources": ["yahoo-si-f", "gold-api-xag-usd", "metals-dev-silver-spot"]},
    },
    {
        "source_key": "tcmb-today-xml",
        "role": "fx_conversion",
        "priority": 30,
        "enabled": True,
        "stale_after_minutes": 180,
        "market_calendar": "tcmb_business_day",
        "reliability_weight": Decimal("0.9000"),
        "details_json": {"pair": "USDTRY", "collector_name": "tcmb_usd_try"},
    },
    {
        "source_key": "rss-news-context",
        "role": "news_context",
        "priority": 100,
        "enabled": True,
        "stale_after_minutes": 360,
        "market_calendar": None,
        "reliability_weight": Decimal("0.5000"),
        "details_json": {"sources": ["fed-rss", "bloomberght-rss", "fxstreet-rss", "investing-rss"]},
    },
)


def _default_strategy_policy(strategy_name: str) -> dict[str, Any]:
    settings = get_settings()
    return {
        "strategy_name": strategy_name,
        "execution_mode": settings.auto_trading_mode,
        "timeframe_roles": dict(DEFAULT_TIMEFRAME_ROLES),
        "freshness_policy": {
            "1d": settings.strategy_trend_max_age_minutes,
            "1h": settings.strategy_entry_max_age_minutes,
            "5m": settings.strategy_execution_max_age_minutes,
        },
        "min_history": {"default": 50},
        "notification_policy": {
            "trade": "always",
            "critical": "always",
            "block_change": "reason_change",
            "hourly_digest": "hourly",
        },
        "details_json": {
            "source_divergence_threshold_percent": float(settings.source_divergence_threshold_percent),
            "policy_version": 1,
        },
    }


@dataclass(frozen=True)
class ResolvedStrategyPolicy:
    strategy_name: str
    execution_mode: str
    timeframe_roles: dict[str, str]
    freshness_policy: dict[str, int]
    min_history: dict[str, int]
    notification_policy: dict[str, Any]
    details: dict[str, Any]
    policy_source: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "strategy_name": self.strategy_name,
            "execution_mode": self.execution_mode,
            "timeframe_roles": dict(self.timeframe_roles),
            "freshness_policy": dict(self.freshness_policy),
            "min_history": dict(self.min_history),
            "notification_policy": dict(self.notification_policy),
            "details": dict(self.details),
            "policy_source": self.policy_source,
        }

    def freshness_minutes(self, timeframe: str) -> int:
        value = self.freshness_policy.get(timeframe)
        if value is not None:
            return int(value)
        settings = get_settings()
        return int(settings.risk_data_stale_after_minutes)

    @property
    def source_divergence_threshold_percent(self) -> Decimal:
        return Decimal(str(self.details.get("source_divergence_threshold_percent", "3.0")))


def ensure_default_policies(db: Session) -> None:
    existing_source_keys = set(db.execute(select(SourceProfile.source_key)).scalars().all())
    for payload in DEFAULT_SOURCE_PROFILES:
        if payload["source_key"] not in existing_source_keys:
            db.add(SourceProfile(**payload))

    existing_strategy_names = set(db.execute(select(StrategyPolicy.strategy_name)).scalars().all())
    for strategy_name in ("strategy_v2", "blended"):
        if strategy_name not in existing_strategy_names:
            db.add(StrategyPolicy(**_default_strategy_policy(strategy_name)))
    db.flush()


def resolve_strategy_policy(db: Session, strategy_name: str | None = None) -> ResolvedStrategyPolicy:
    strategy_name = strategy_name or get_settings().strategy_name or "strategy_v2"
    ensure_default_policies(db)
    row = db.execute(
        select(StrategyPolicy).where(StrategyPolicy.strategy_name == strategy_name).limit(1)
    ).scalar_one_or_none()
    if row is None:
        payload = _default_strategy_policy(strategy_name)
        row = StrategyPolicy(**payload)
        db.add(row)
        db.flush()
        policy_source = "safe_default"
    else:
        policy_source = "db"

    return ResolvedStrategyPolicy(
        strategy_name=row.strategy_name,
        execution_mode=row.execution_mode,
        timeframe_roles={str(key): str(value) for key, value in (row.timeframe_roles or {}).items()},
        freshness_policy={str(key): int(value) for key, value in (row.freshness_policy or {}).items()},
        min_history={str(key): int(value) for key, value in (row.min_history or {}).items()},
        notification_policy=dict(row.notification_policy or {}),
        details=dict(row.details_json or {}),
        policy_source=policy_source,
    )


def resolve_enabled_source_profiles(db: Session, *, role: str | None = None) -> list[SourceProfile]:
    ensure_default_policies(db)
    stmt = (
        select(SourceProfile)
        .where(SourceProfile.enabled.is_(True))
        .order_by(SourceProfile.priority.asc(), SourceProfile.source_key.asc())
    )
    if role is not None:
        stmt = stmt.where(SourceProfile.role == role)
    return list(db.execute(stmt).scalars().all())
