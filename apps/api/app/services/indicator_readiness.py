from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal

from sqlalchemy import desc, select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models import Asset, MarketBar, PriceSnapshot, TechnicalIndicator

CURRENT_INDICATOR_CALCULATION_VERSION = "technical-indicators-v1"
DEFAULT_INDICATOR_TIMEFRAME = "5m"
DEFAULT_REQUIRED_FIELDS = (
    "rsi_14",
    "macd_line",
    "macd_signal",
    "macd_histogram",
    "bb_upper_20_2",
    "bb_middle_20_2",
    "bb_lower_20_2",
    "sma_20",
    "sma_50",
    "atr_14",
)
DEFAULT_ALLOWED_SOURCES = (
    "yahoo-si-f",
    "gold-api-xag-usd",
    "metals-dev-silver-spot",
)
DEFAULT_REQUIRED_MIN_BAR_COUNT = 50


@dataclass(frozen=True)
class IndicatorReadiness:
    asset_symbol: str
    timeframe: str
    status: str
    usable: bool
    reason_codes: list[str]
    required_min_bar_count: int
    required_fields: tuple[str, ...]
    indicator: TechnicalIndicator | None
    indicator_id: int | None
    market_bar_id: int | None
    price_snapshot_id: int | None
    source: str | None
    bar_timestamp: datetime | None
    age_seconds: int | None
    freshness_minutes: int
    calculation_version: str | None
    quality_status: str | None
    input_bar_count: int | None
    missing_required_fields: list[str]
    close_usd_oz: Decimal | None

    def to_dict(self) -> dict:
        return {
            "asset_symbol": self.asset_symbol,
            "timeframe": self.timeframe,
            "status": self.status,
            "usable": self.usable,
            "reason_codes": list(self.reason_codes),
            "required_min_bar_count": self.required_min_bar_count,
            "required_fields": list(self.required_fields),
            "indicator_id": self.indicator_id,
            "market_bar_id": self.market_bar_id,
            "price_snapshot_id": self.price_snapshot_id,
            "source": self.source,
            "bar_timestamp": self.bar_timestamp,
            "age_seconds": self.age_seconds,
            "freshness_minutes": self.freshness_minutes,
            "calculation_version": self.calculation_version,
            "quality_status": self.quality_status,
            "input_bar_count": self.input_bar_count,
            "missing_required_fields": list(self.missing_required_fields),
            "close_usd_oz": self.close_usd_oz,
        }


@dataclass(frozen=True)
class IndicatorContext:
    readiness: IndicatorReadiness
    previous_indicator: TechnicalIndicator | None

    def to_dict(self) -> dict:
        return {
            "readiness": self.readiness.to_dict(),
            "previous_indicator_id": self.previous_indicator.id if self.previous_indicator else None,
            "previous_indicator_bar_timestamp": self.previous_indicator.bar_timestamp
            if self.previous_indicator
            else None,
        }


def get_indicator_readiness(
    db: Session,
    *,
    asset_symbol: str = "XAG_GRAM",
    timeframe: str = DEFAULT_INDICATOR_TIMEFRAME,
    required_min_bar_count: int = DEFAULT_REQUIRED_MIN_BAR_COUNT,
    max_age_minutes: int | None = None,
    allowed_sources: tuple[str, ...] = DEFAULT_ALLOWED_SOURCES,
) -> IndicatorReadiness:
    settings = get_settings()
    freshness_minutes = max_age_minutes or settings.risk_data_stale_after_minutes
    now = datetime.now(UTC)

    asset = db.execute(select(Asset).where(Asset.symbol == asset_symbol)).scalar_one_or_none()
    if asset is None:
        return _build_empty(
            asset_symbol=asset_symbol,
            timeframe=timeframe,
            required_min_bar_count=required_min_bar_count,
            freshness_minutes=freshness_minutes,
            reason_codes=["ASSET_NOT_FOUND"],
            status="empty",
        )

    stmt = (
        select(TechnicalIndicator)
        .join(PriceSnapshot, TechnicalIndicator.price_snapshot_id == PriceSnapshot.id)
        .join(MarketBar, TechnicalIndicator.market_bar_id == MarketBar.id)
        .where(PriceSnapshot.asset_id == asset.id)
        .where(MarketBar.asset_id == asset.id)
        .where(MarketBar.timeframe == timeframe)
        .where(MarketBar.source.in_(allowed_sources))
        .order_by(desc(TechnicalIndicator.bar_timestamp), desc(TechnicalIndicator.id))
        .limit(1)
    )
    indicator = db.execute(stmt).scalar_one_or_none()
    if indicator is None:
        return _build_empty(
            asset_symbol=asset_symbol,
            timeframe=timeframe,
            required_min_bar_count=required_min_bar_count,
            freshness_minutes=freshness_minutes,
            reason_codes=["INDICATOR_NOT_FOUND"],
            status="empty",
        )

    reasons: list[str] = []
    status = "ready"

    market_bar = indicator.market_bar
    price_snapshot = indicator.price_snapshot
    source = market_bar.source if market_bar is not None else None

    if market_bar is None:
        reasons.append("MARKET_BAR_MISSING")
        status = "degraded"
    if price_snapshot is None:
        reasons.append("PRICE_SNAPSHOT_MISSING")
        status = "degraded"

    if market_bar is not None and market_bar.timeframe != timeframe:
        reasons.append("TIMEFRAME_MISMATCH")
        status = "degraded"
    if market_bar is not None and market_bar.source not in allowed_sources:
        reasons.append("SOURCE_NOT_ALLOWED")
        status = "degraded"
    if indicator.calculation_version != CURRENT_INDICATOR_CALCULATION_VERSION:
        reasons.append("CALCULATION_VERSION_MISMATCH")
        status = "degraded"
    if indicator.quality_status != "ok":
        reasons.append("QUALITY_NOT_OK")
        status = "degraded"

    age_seconds = None
    if indicator.bar_timestamp is not None:
        aware_bar_ts = _aware(indicator.bar_timestamp)
        age_seconds = int((now - aware_bar_ts).total_seconds())
        if age_seconds > freshness_minutes * 60:
            reasons.append("INDICATOR_STALE")
            status = "stale"

    if indicator.input_bar_count < required_min_bar_count:
        reasons.append("INSUFFICIENT_HISTORY")
        if status == "ready":
            status = "warming_up"

    missing_required_fields = _missing_required_fields(indicator)
    if missing_required_fields:
        if indicator.input_bar_count < required_min_bar_count and status in {"ready", "warming_up"}:
            status = "warming_up"
            reasons.append("WARMUP_FIELDS_PENDING")
        else:
            reasons.append("REQUIRED_FIELDS_MISSING")
            if status == "ready":
                status = "degraded"

    usable = status == "ready"
    return IndicatorReadiness(
        asset_symbol=asset_symbol,
        timeframe=timeframe,
        status=status,
        usable=usable,
        reason_codes=reasons,
        required_min_bar_count=required_min_bar_count,
        required_fields=DEFAULT_REQUIRED_FIELDS,
        indicator=indicator,
        indicator_id=indicator.id,
        market_bar_id=indicator.market_bar_id,
        price_snapshot_id=indicator.price_snapshot_id,
        source=source,
        bar_timestamp=indicator.bar_timestamp,
        age_seconds=age_seconds,
        freshness_minutes=freshness_minutes,
        calculation_version=indicator.calculation_version,
        quality_status=indicator.quality_status,
        input_bar_count=indicator.input_bar_count,
        missing_required_fields=missing_required_fields,
        close_usd_oz=indicator.close_usd_oz,
    )


def get_latest_indicator_context(
    db: Session,
    *,
    asset_symbol: str = "XAG_GRAM",
    timeframe: str = DEFAULT_INDICATOR_TIMEFRAME,
    required_min_bar_count: int = DEFAULT_REQUIRED_MIN_BAR_COUNT,
    max_age_minutes: int | None = None,
    allowed_sources: tuple[str, ...] = DEFAULT_ALLOWED_SOURCES,
) -> IndicatorContext:
    readiness = get_indicator_readiness(
        db,
        asset_symbol=asset_symbol,
        timeframe=timeframe,
        required_min_bar_count=required_min_bar_count,
        max_age_minutes=max_age_minutes,
        allowed_sources=allowed_sources,
    )
    previous_indicator = None
    if readiness.indicator is not None and readiness.usable:
        previous_indicator = get_previous_indicator(
            db,
            asset_symbol=asset_symbol,
            source=readiness.source,
            timeframe=timeframe,
            before_timestamp=readiness.bar_timestamp,
            calculation_version=readiness.calculation_version,
        )
    return IndicatorContext(readiness=readiness, previous_indicator=previous_indicator)


def get_previous_indicator(
    db: Session,
    *,
    asset_symbol: str,
    source: str | None,
    timeframe: str,
    before_timestamp: datetime | None,
    calculation_version: str | None,
) -> TechnicalIndicator | None:
    if source is None or before_timestamp is None or calculation_version is None:
        return None

    asset = db.execute(select(Asset).where(Asset.symbol == asset_symbol)).scalar_one_or_none()
    if asset is None:
        return None

    stmt = (
        select(TechnicalIndicator)
        .join(PriceSnapshot, TechnicalIndicator.price_snapshot_id == PriceSnapshot.id)
        .join(MarketBar, TechnicalIndicator.market_bar_id == MarketBar.id)
        .where(PriceSnapshot.asset_id == asset.id)
        .where(MarketBar.asset_id == asset.id)
        .where(MarketBar.source == source)
        .where(MarketBar.timeframe == timeframe)
        .where(TechnicalIndicator.calculation_version == calculation_version)
        .where(TechnicalIndicator.bar_timestamp < before_timestamp)
        .order_by(desc(TechnicalIndicator.bar_timestamp), desc(TechnicalIndicator.id))
        .limit(1)
    )
    return db.execute(stmt).scalar_one_or_none()


def _missing_required_fields(indicator: TechnicalIndicator) -> list[str]:
    missing: list[str] = []
    for field_name in DEFAULT_REQUIRED_FIELDS:
        if getattr(indicator, field_name) is None:
            missing.append(field_name)
    return missing


def _build_empty(
    *,
    asset_symbol: str,
    timeframe: str,
    required_min_bar_count: int,
    freshness_minutes: int,
    reason_codes: list[str],
    status: str,
) -> IndicatorReadiness:
    return IndicatorReadiness(
        asset_symbol=asset_symbol,
        timeframe=timeframe,
        status=status,
        usable=False,
        reason_codes=reason_codes,
        required_min_bar_count=required_min_bar_count,
        required_fields=DEFAULT_REQUIRED_FIELDS,
        indicator=None,
        indicator_id=None,
        market_bar_id=None,
        price_snapshot_id=None,
        source=None,
        bar_timestamp=None,
        age_seconds=None,
        freshness_minutes=freshness_minutes,
        calculation_version=None,
        quality_status=None,
        input_bar_count=None,
        missing_required_fields=list(DEFAULT_REQUIRED_FIELDS),
        close_usd_oz=None,
    )


def _aware(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)
