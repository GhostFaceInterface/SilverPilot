from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, InvalidOperation

from sqlalchemy import desc, select
from sqlalchemy.orm import Session

from app.models import RawBankPrice, RawFxRate, RawGlobalPrice
from app.services.policy_resolver import ResolvedStrategyPolicy

TROY_OUNCE_GRAMS = Decimal("31.1034768")
SOURCE_DIVERGENCE_BLOCK = "SOURCE_DIVERGENCE_BLOCK"


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
        }


def evaluate_source_divergence(db: Session, *, policy: ResolvedStrategyPolicy | None = None) -> SourceDivergenceResult:
    threshold = policy.source_divergence_threshold_percent if policy is not None else Decimal("3.0")
    bank = db.execute(
        select(RawBankPrice).order_by(desc(RawBankPrice.fetched_at), desc(RawBankPrice.observed_at)).limit(1)
    ).scalar_one_or_none()
    global_price = db.execute(
        select(RawGlobalPrice).order_by(desc(RawGlobalPrice.fetched_at), desc(RawGlobalPrice.observed_at)).limit(1)
    ).scalar_one_or_none()
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
    if bank_mid is not None and global_mid is not None and usd_try is not None and global_mid > 0 and usd_try > 0:
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
    )


def _mid(buy_price, sell_price) -> Decimal | None:
    try:
        buy = Decimal(str(buy_price))
        sell = Decimal(str(sell_price))
    except (InvalidOperation, TypeError, ValueError):
        return None
    if buy <= 0 or sell <= 0:
        return None
    return (buy + sell) / Decimal("2")
