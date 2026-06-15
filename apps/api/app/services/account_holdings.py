from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import (
    AccountHoldingSnapshot,
    AccountLedgerEntry,
    Asset,
    Currency,
    Instrument,
    MeasurementUnit,
    ProviderAccount,
)


@dataclass(frozen=True)
class HoldingView:
    account_id: int
    kind: str
    quantity: Decimal
    cash_balance: Decimal
    asset_symbol: str | None
    instrument_symbol: str | None
    unit_code: str | None
    currency_code: str | None


def compute_account_holdings(db: Session, account_id: int) -> list[HoldingView]:
    account = db.get(ProviderAccount, account_id)
    if account is None:
        return []

    holdings: list[HoldingView] = []
    asset_rows = db.execute(
        select(
            AccountLedgerEntry.asset_id,
            AccountLedgerEntry.instrument_id,
            AccountLedgerEntry.unit_id,
            func.sum(AccountLedgerEntry.quantity_delta).label("quantity"),
        )
        .where(AccountLedgerEntry.account_id == account_id)
        .group_by(AccountLedgerEntry.asset_id, AccountLedgerEntry.instrument_id, AccountLedgerEntry.unit_id)
    ).all()
    for row in asset_rows:
        quantity = row.quantity or Decimal("0")
        if quantity == 0 or (row.asset_id is None and row.instrument_id is None and row.unit_id is None):
            continue
        asset = db.get(Asset, row.asset_id) if row.asset_id is not None else None
        instrument = db.get(Instrument, row.instrument_id) if row.instrument_id is not None else None
        unit = db.get(MeasurementUnit, row.unit_id) if row.unit_id is not None else None
        holdings.append(
            HoldingView(
                account_id=account_id,
                kind="instrument",
                quantity=quantity,
                cash_balance=Decimal("0"),
                asset_symbol=asset.symbol if asset else None,
                instrument_symbol=instrument.symbol if instrument else None,
                unit_code=unit.code if unit else None,
                currency_code=None,
            )
        )

    cash_rows = db.execute(
        select(
            AccountLedgerEntry.currency_id,
            func.sum(AccountLedgerEntry.cash_delta).label("cash_balance"),
        )
        .where(AccountLedgerEntry.account_id == account_id)
        .group_by(AccountLedgerEntry.currency_id)
    ).all()
    for row in cash_rows:
        cash_balance = row.cash_balance or Decimal("0")
        if cash_balance == 0 and row.currency_id is None:
            continue
        currency = db.get(Currency, row.currency_id) if row.currency_id is not None else None
        holdings.append(
            HoldingView(
                account_id=account_id,
                kind="cash",
                quantity=Decimal("0"),
                cash_balance=cash_balance,
                asset_symbol=None,
                instrument_symbol=currency.code if currency else None,
                unit_code="currency_unit",
                currency_code=currency.code if currency else None,
            )
        )

    return holdings


def refresh_account_holding_snapshots(db: Session, account_id: int) -> list[AccountHoldingSnapshot]:
    latest_entry_id = db.execute(
        select(AccountLedgerEntry.id)
        .where(AccountLedgerEntry.account_id == account_id)
        .order_by(AccountLedgerEntry.occurred_at.desc(), AccountLedgerEntry.id.desc())
        .limit(1)
    ).scalar_one_or_none()
    observed_at = datetime.now(UTC)
    snapshots: list[AccountHoldingSnapshot] = []

    for holding in compute_account_holdings(db, account_id):
        asset = db.execute(select(Asset).where(Asset.symbol == holding.asset_symbol)).scalar_one_or_none()
        instrument = db.execute(
            select(Instrument).where(Instrument.symbol == holding.instrument_symbol)
        ).scalar_one_or_none()
        unit = db.execute(select(MeasurementUnit).where(MeasurementUnit.code == holding.unit_code)).scalar_one_or_none()
        currency = (
            db.execute(select(Currency).where(Currency.code == holding.currency_code)).scalar_one_or_none()
            if holding.currency_code
            else None
        )
        snapshot = AccountHoldingSnapshot(
            account_id=account_id,
            asset_id=asset.id if asset else None,
            instrument_id=instrument.id if instrument else None,
            unit_id=unit.id if unit else None,
            currency_id=currency.id if currency else None,
            quantity=holding.quantity,
            cash_balance=holding.cash_balance,
            source_ledger_entry_id=latest_entry_id,
            observed_at=observed_at,
            details_json={"source": "ledger_refresh"},
        )
        db.add(snapshot)
        snapshots.append(snapshot)

    db.flush()
    return snapshots
