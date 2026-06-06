from decimal import Decimal

from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.db import Base
from app.models import Asset, PaperTrade, Portfolio
from app.services.trade_intents import TradeIntent, execute_trade_intent


def _seed_db():
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    testing_session = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    Base.metadata.create_all(bind=engine)
    db = testing_session()
    asset = Asset(symbol="XAG_GRAM", name="Gram Silver", asset_type="metal", is_active=True)
    portfolio = Portfolio(
        name="gram-paper",
        base_currency="USD",
        initial_cash=Decimal("600.000000"),
        cash_balance=Decimal("600.000000"),
        is_real_money=False,
    )
    db.add_all([asset, portfolio])
    db.commit()
    return engine, db, portfolio


def test_buy_intent_missing_stop_or_target_is_blocked():
    engine, db, portfolio = _seed_db()

    trade, snapshot = execute_trade_intent(
        db,
        intent=TradeIntent(
            portfolio_name="gram-paper",
            asset_symbol="XAG_GRAM",
            action="BUY",
            confidence=Decimal("0.8000"),
            reason_code="STRATEGY_V2_BUY_CONFIRMED",
            stop_loss_price=None,
            take_profit_price=Decimal("32.000000"),
            expected_exit_price=Decimal("32.000000"),
        ),
        buy_price=Decimal("30.000000"),
        sell_price=Decimal("29.900000"),
        fee_amount=Decimal("0.050000"),
    )

    assert trade.action == "blocked"
    assert trade.risk_decision.reason_code == "INTENT_METADATA_MISSING"
    assert portfolio.cash_balance == Decimal("600.000000")
    assert snapshot.cash_balance == Decimal("600.000000")

    db.close()
    Base.metadata.drop_all(bind=engine)


def test_risk_blocked_intent_leaves_balances_unchanged():
    engine, db, portfolio = _seed_db()

    trade, snapshot = execute_trade_intent(
        db,
        intent=TradeIntent(
            portfolio_name="gram-paper",
            asset_symbol="XAG_GRAM",
            action="BUY",
            confidence=Decimal("0.9000"),
            reason_code="STRATEGY_V2_BUY_CONFIRMED",
            stop_loss_price=Decimal("29.000000"),
            take_profit_price=Decimal("32.000000"),
            expected_exit_price=Decimal("32.000000"),
        ),
        buy_price=Decimal("30.000000"),
        sell_price=Decimal("29.900000"),
        fee_amount=Decimal("0.050000"),
    )

    assert trade.action == "blocked"
    assert trade.risk_decision.reason_code == "MISSING_DATA"
    assert portfolio.cash_balance == Decimal("600.000000")
    assert snapshot.cash_balance == Decimal("600.000000")
    assert db.execute(select(PaperTrade)).scalar_one().action == "blocked"

    db.close()
    Base.metadata.drop_all(bind=engine)
