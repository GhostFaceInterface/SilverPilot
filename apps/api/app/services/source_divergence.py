from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation

from sqlalchemy import desc, select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models import Asset, RawBankPrice, RawFxRate, RawGlobalPrice
from app.services.policy_resolver import ResolvedStrategyPolicy

TROY_OUNCE_GRAMS = Decimal("31.1034768")
SOURCE_DIVERGENCE_BLOCK = "SOURCE_DIVERGENCE_BLOCK"
SOURCE_DIVERGENCE_STALE_DATA = "SOURCE_DIVERGENCE_STALE_DATA"


@dataclass(frozen=True)
class SourceDivergenceResult:
    status: str
    blocked: bool
    reason_code: str | None
    threshold_percent: Decimal
    bank_mid_try_gram: Decimal | None
    global_xag_usd_oz: Decimal | None
    usd_try: Decimal | None
    converted_try_gram: Decimal | None
    divergence_percent: Decimal | None
    bank_source: str | None
    global_source: str | None
    fx_source: str | None
    bank_asset_symbol: str | None
    global_asset_symbol: str | None
    bank_observed_at: datetime | None
    global_observed_at: datetime | None
    fx_observed_at: datetime | None
    bank_age_minutes: int | None
    global_age_minutes: int | None
    fx_age_minutes: int | None

    def to_dict(self) -> dict:
        return {
            "status": self.status,
            "blocked": self.blocked,
            "reason_code": self.reason_code,
            "threshold_percent": self.threshold_percent,
            "bank_mid_try_gram": self.bank_mid_try_gram,
            "global_xag_usd_oz": self.global_xag_usd_oz,
            "usd_try": self.usd_try,
            "converted_try_gram": self.converted_try_gram,
            "divergence_percent": self.divergence_percent,
            "bank_source": self.bank_source,
            "global_source": self.global_source,
            "fx_source": self.fx_source,
            "bank_asset_symbol": self.bank_asset_symbol,
            "global_asset_symbol": self.global_asset_symbol,
            "bank_observed_at": self.bank_observed_at,
            "global_observed_at": self.global_observed_at,
            "fx_observed_at": self.fx_observed_at,
            "bank_age_minutes": self.bank_age_minutes,
            "global_age_minutes": self.global_age_minutes,
            "fx_age_minutes": self.fx_age_minutes,
        }


def evaluate_source_divergence(db: Session, *, policy: ResolvedStrategyPolicy | None = None) -> SourceDivergenceResult:
    now = datetime.now(UTC)
    settings = get_settings()
    threshold = policy.source_divergence_threshold_percent if policy is not None else Decimal("3.0")
    bank_asset = _asset(db, "XAG_GRAM")
    global_asset = _asset(db, "XAG")
    bank = _latest_bank_price(db, bank_asset.id if bank_asset is not None else None)
    global_price = _latest_global_price(db, global_asset.id if global_asset is not None else None)
    fx_rate = db.execute(
        select(RawFxRate)
        .where(RawFxRate.base_currency == "USD", RawFxRate.quote_currency == "TRY")
        .order_by(desc(RawFxRate.fetched_at), desc(RawFxRate.observed_at))
        .limit(1)
    ).scalar_one_or_none()

    bank_mid = _mid(bank.buy_price, bank.sell_price) if bank is not None else None
    global_mid = _mid(global_price.buy_price, global_price.sell_price) if global_price is not None else None
    usd_try = Decimal(str(fx_rate.rate)) if fx_rate is not None and fx_rate.rate is not None else None

    converted = None
    divergence = None
    status = "insufficient_data"
    blocked = False
    reason_code = None

    bank_age = _age_minutes(bank.observed_at, now) if bank is not None else None
    global_age = _age_minutes(global_price.observed_at, now) if global_price is not None else None
    fx_age = _age_minutes(fx_rate.observed_at, now) if fx_rate is not None else None
    stale_reasons = _stale_reasons(
        bank_age=bank_age,
        global_age=global_age,
        fx_age=fx_age,
        bank_max_minutes=settings.risk_data_stale_after_minutes,
        global_max_minutes=settings.global_xag_freshness_minutes,
        fx_max_minutes=settings.risk_data_stale_after_minutes,
    )

    if bank_mid is not None and global_mid is not None and usd_try is not None and global_mid > 0 and usd_try > 0:
        if stale_reasons:
            status = "stale_data"
            blocked = True
            reason_code = SOURCE_DIVERGENCE_STALE_DATA
        else:
            converted = (global_mid * usd_try) / TROY_OUNCE_GRAMS
            if converted > 0:
                divergence = (abs(bank_mid - converted) / converted) * Decimal("100")
                status = "ok"
                if divergence > threshold:
                    status = "blocked"
                    blocked = True
                    reason_code = SOURCE_DIVERGENCE_BLOCK

    return SourceDivergenceResult(
        status=status,
        blocked=blocked,
        reason_code=reason_code,
        threshold_percent=threshold,
        bank_mid_try_gram=bank_mid,
        global_xag_usd_oz=global_mid,
        usd_try=usd_try,
        converted_try_gram=converted,
        divergence_percent=divergence,
        bank_source=bank.source if bank is not None else None,
        global_source=global_price.source if global_price is not None else None,
        fx_source=fx_rate.source if fx_rate is not None else None,
        bank_asset_symbol=bank_asset.symbol if bank_asset is not None else None,
        global_asset_symbol=global_asset.symbol if global_asset is not None else None,
        bank_observed_at=bank.observed_at if bank is not None else None,
        global_observed_at=global_price.observed_at if global_price is not None else None,
        fx_observed_at=fx_rate.observed_at if fx_rate is not None else None,
        bank_age_minutes=bank_age,
        global_age_minutes=global_age,
        fx_age_minutes=fx_age,
    )


def _asset(db: Session, symbol: str) -> Asset | None:
    return db.execute(select(Asset).where(Asset.symbol == symbol)).scalar_one_or_none()


def _latest_bank_price(db: Session, asset_id: int | None) -> RawBankPrice | None:
    if asset_id is None:
        return None
    return db.execute(
        select(RawBankPrice)
        .where(
            RawBankPrice.asset_id == asset_id,
            RawBankPrice.currency == "TRY",
            RawBankPrice.is_degraded.is_(False),
        )
        .order_by(desc(RawBankPrice.fetched_at), desc(RawBankPrice.observed_at))
        .limit(1)
    ).scalar_one_or_none()


def _latest_global_price(db: Session, asset_id: int | None) -> RawGlobalPrice | None:
    if asset_id is None:
        return None
    return db.execute(
        select(RawGlobalPrice)
        .where(RawGlobalPrice.asset_id == asset_id, RawGlobalPrice.currency == "USD")
        .order_by(desc(RawGlobalPrice.fetched_at), desc(RawGlobalPrice.observed_at))
        .limit(1)
    ).scalar_one_or_none()


def _stale_reasons(
    *,
    bank_age: int | None,
    global_age: int | None,
    fx_age: int | None,
    bank_max_minutes: int,
    global_max_minutes: int,
    fx_max_minutes: int,
) -> list[str]:
    reasons = []
    if bank_age is None or bank_age > bank_max_minutes:
        reasons.append("bank_price_stale")
    if global_age is None or global_age > global_max_minutes:
        reasons.append("global_xag_stale")
    if fx_age is None or fx_age > fx_max_minutes:
        reasons.append("usd_try_stale")
    return reasons


def _mid(buy_price, sell_price) -> Decimal | None:
    try:
        buy = Decimal(str(buy_price))
        sell = Decimal(str(sell_price))
    except (InvalidOperation, TypeError, ValueError):
        return None
    if buy <= 0 or sell <= 0:
        return None
    return (buy + sell) / Decimal("2")


def _age_minutes(value: datetime | None, now: datetime) -> int | None:
    if value is None:
        return None
    if value.tzinfo is None:
        value = value.replace(tzinfo=UTC)
    return max(int((now - value.astimezone(UTC)).total_seconds() // 60), 0)
