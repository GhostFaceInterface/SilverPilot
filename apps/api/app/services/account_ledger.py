from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import AccountLedgerEntry, Asset, Currency, PaperTrade, Portfolio
from app.services.instrument_registry import (
    get_or_create_currency,
    get_or_create_default_provider_account,
    map_existing_assets,
)

MONEY_QUANT = Decimal("0.000001")


def ensure_opening_balance(db: Session, portfolio: Portfolio) -> None:
    account = get_or_create_default_provider_account(db, portfolio)
    existing_count = db.execute(
        select(func.count(AccountLedgerEntry.id)).where(AccountLedgerEntry.account_id == account.id)
    ).scalar_one()
    if existing_count:
        return

    currency = get_or_create_currency(db, portfolio.base_currency)
    db.add(
        AccountLedgerEntry(
            account_id=account.id,
            currency_id=currency.id,
            entry_type="deposit",
            quantity_delta=Decimal("0"),
            cash_delta=Decimal(portfolio.initial_cash).quantize(MONEY_QUANT),
            gross_amount=Decimal(portfolio.initial_cash).quantize(MONEY_QUANT),
            fees=Decimal("0"),
            taxes=Decimal("0"),
            occurred_at=datetime.now(UTC),
            details_json={"source": "portfolio_initial_cash", "portfolio_id": portfolio.id},
        )
    )
    db.flush()


def record_paper_trade_ledger_entry(db: Session, *, portfolio: Portfolio, asset: Asset, trade: PaperTrade) -> None:
    if trade.action not in ("paper_buy", "paper_sell"):
        return

    ensure_opening_balance(db, portfolio)
    map_existing_assets(db)
    account = get_or_create_default_provider_account(db, portfolio)
    currency = _resolve_trade_currency(db, portfolio, asset)

    quantity_sign = Decimal("1") if trade.action == "paper_buy" else Decimal("-1")
    cash_sign = Decimal("-1") if trade.action == "paper_buy" else Decimal("1")
    db.add(
        AccountLedgerEntry(
            account_id=account.id,
            asset_id=asset.id,
            instrument_id=asset.instrument_id,
            unit_id=asset.unit_id,
            currency_id=currency.id,
            quote_currency_id=asset.quote_currency_id or currency.id,
            entry_type="buy" if trade.action == "paper_buy" else "sell",
            quantity_delta=(Decimal(trade.quantity) * quantity_sign).quantize(MONEY_QUANT),
            cash_delta=(Decimal(trade.net_amount) * cash_sign).quantize(MONEY_QUANT),
            price=trade.price,
            gross_amount=trade.gross_amount,
            fees=trade.fees,
            taxes=trade.taxes,
            paper_trade_id=trade.id,
            trade_intent_id=trade.trade_intent_id,
            risk_decision_id=trade.risk_decision_id,
            occurred_at=datetime.now(UTC),
            details_json={"source": "paper_trade_dual_write", "portfolio_id": portfolio.id},
        )
    )
    db.flush()


def _resolve_trade_currency(db: Session, portfolio: Portfolio, asset: Asset) -> Currency:
    return get_or_create_currency(db, portfolio.base_currency)
