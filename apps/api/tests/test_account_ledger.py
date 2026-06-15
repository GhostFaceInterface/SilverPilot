from decimal import Decimal

from sqlalchemy import select

from app.models import (
    AccountLedgerEntry,
    AccountHoldingSnapshot,
    Asset,
    Currency,
    IndicatorDefinition,
    Instrument,
    MeasurementUnit,
    PaperTrade,
    Portfolio,
    ProviderAccount,
    RiskDecision,
    TechnicalIndicatorValue,
    TradeIntentRecord,
)
from app.paper_trading.service import execute_paper_trade_with_risk_decision
from app.schemas.paper_trading import PaperTradeRequest
from app.services.account_holdings import compute_account_holdings
from app.services.instrument_registry import ensure_reference_data


def test_instrument_account_ledger_schema_is_additive():
    asset_columns = Asset.__table__.columns
    paper_trade_columns = PaperTrade.__table__.columns

    assert "instrument_id" in asset_columns
    assert "unit_id" in asset_columns
    assert "quote_currency_id" in asset_columns
    assert "trade_intent_id" in paper_trade_columns
    for model in (
        Currency,
        MeasurementUnit,
        Instrument,
        ProviderAccount,
        TradeIntentRecord,
        AccountLedgerEntry,
        AccountHoldingSnapshot,
        IndicatorDefinition,
        TechnicalIndicatorValue,
    ):
        assert model.__table__.name


def test_reference_seed_maps_assets_and_is_idempotent(db_session):
    db_session.add_all(
        [
            Asset(symbol="XAG", name="Silver Spot Ounce", asset_type="metal", is_active=True),
            Asset(symbol="XAG_GRAM", name="Silver Gram", asset_type="metal", is_active=True),
        ]
    )
    db_session.commit()

    ensure_reference_data(db_session)
    ensure_reference_data(db_session)
    db_session.commit()

    assert db_session.execute(select(Currency).where(Currency.code == "USD")).scalar_one().name == "US Dollar"
    assert db_session.execute(select(Instrument).where(Instrument.symbol == "XAG")).scalar_one().name == "Silver"

    gram_asset = db_session.execute(select(Asset).where(Asset.symbol == "XAG_GRAM")).scalar_one()
    assert gram_asset.instrument.symbol == "XAG"
    assert gram_asset.unit.code == "gram"
    assert gram_asset.quote_currency.code == "USD"


def test_paper_trade_dual_writes_ledger_and_derived_holdings(db_session):
    asset = Asset(symbol="XAG_GRAM", name="Silver Gram", asset_type="metal", is_active=True)
    portfolio = Portfolio(
        name="gram-paper",
        base_currency="USD",
        initial_cash=Decimal("2500.000000"),
        cash_balance=Decimal("2500.000000"),
        is_real_money=False,
    )
    decision = RiskDecision(
        decision="allow",
        reason_code="RISK_CHECK_PASSED",
        risk_level="low",
        confidence=Decimal("1.0000"),
        details_json={},
    )
    db_session.add_all([asset, portfolio, decision])
    db_session.commit()

    trade, _snapshot = execute_paper_trade_with_risk_decision(
        db_session,
        PaperTradeRequest(
            portfolio_name="gram-paper",
            asset_symbol="XAG_GRAM",
            action="paper_buy",
            quantity=Decimal("2.000000"),
            buy_price=Decimal("30.000000"),
            sell_price=Decimal("29.500000"),
            fees=Decimal("1.000000"),
            taxes=Decimal("0.500000"),
        ),
        decision,
    )

    account = db_session.execute(select(ProviderAccount)).scalar_one()
    ledger_entries = (
        db_session.execute(
            select(AccountLedgerEntry)
            .where(AccountLedgerEntry.account_id == account.id)
            .order_by(AccountLedgerEntry.id)
        )
        .scalars()
        .all()
    )
    assert [entry.entry_type for entry in ledger_entries] == ["deposit", "buy"]
    assert ledger_entries[0].cash_delta == Decimal("2500.000000")
    assert ledger_entries[1].paper_trade_id == trade.id
    assert ledger_entries[1].quantity_delta == Decimal("2.000000")
    assert ledger_entries[1].cash_delta == Decimal("-61.500000")

    holdings = compute_account_holdings(db_session, account.id)
    cash = next(holding for holding in holdings if holding.kind == "cash")
    metal = next(holding for holding in holdings if holding.kind == "instrument")
    assert cash.cash_balance == Decimal("2438.500000")
    assert metal.asset_symbol == "XAG_GRAM"
    assert metal.instrument_symbol == "XAG"
    assert metal.unit_code == "gram"
    assert metal.quantity == Decimal("2.000000")
    assert db_session.execute(select(PaperTrade)).scalar_one().id == trade.id
