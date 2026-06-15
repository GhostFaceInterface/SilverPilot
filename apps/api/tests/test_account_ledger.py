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
    Provider,
    ProviderAccount,
    RiskDecision,
    TechnicalIndicatorValue,
    TradeIntentRecord,
)
from app.paper_trading.service import execute_paper_trade_with_risk_decision
from app.schemas.paper_trading import PaperTradeRequest
from app.services.account_holdings import compute_account_holdings


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


def test_asset_semantics_are_read_from_db_objects(db_session):
    usd, gram, silver = _seed_reference_objects(db_session)
    gram_asset = Asset(
        symbol="XAG_GRAM",
        name="Silver Gram",
        asset_type="metal",
        is_active=True,
        instrument_id=silver.id,
        unit_id=gram.id,
        quote_currency_id=usd.id,
    )
    db_session.add(gram_asset)
    db_session.commit()

    loaded_asset = db_session.execute(select(Asset).where(Asset.symbol == "XAG_GRAM")).scalar_one()
    assert loaded_asset.instrument.symbol == "XAG"
    assert loaded_asset.unit.code == "gram"
    assert loaded_asset.quote_currency.code == "USD"


def test_paper_trade_dual_writes_ledger_and_derived_holdings(db_session):
    usd, gram, silver = _seed_reference_objects(db_session)
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
    db_session.add_all([portfolio, decision])
    db_session.flush()
    asset = Asset(
        symbol="XAG_GRAM",
        name="Silver Gram",
        asset_type="metal",
        is_active=True,
        instrument_id=silver.id,
        unit_id=gram.id,
        quote_currency_id=usd.id,
    )
    provider = Provider(name="kuveyt_turk", display_name="Kuveyt Turk", is_active=True, config_json={})
    db_session.add_all([asset, provider])
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


def _seed_reference_objects(db_session):
    usd = Currency(code="USD", name="US Dollar", numeric_code="840", minor_unit=2, is_active=True)
    gram = MeasurementUnit(
        code="gram",
        name="Gram",
        unit_type="mass",
        to_base_factor=Decimal("1.00000000"),
        base_unit_code="gram",
        is_active=True,
    )
    silver = Instrument(
        symbol="XAG",
        name="Silver",
        instrument_type="metal",
        native_unit=gram,
        is_active=True,
        metadata_json={},
    )
    db_session.add_all([usd, gram, silver])
    db_session.flush()
    return usd, gram, silver
