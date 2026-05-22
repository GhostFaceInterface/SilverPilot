import datetime
from decimal import Decimal
from unittest.mock import AsyncMock, patch
import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.db import Base
from app.core.config import Settings
from app.models import Asset, Portfolio, PriceSnapshot, TechnicalIndicator, Signal, PaperTrade, RiskDecision
from app.services.auto_trader import run_auto_trading


@pytest.mark.anyio
async def test_auto_trading_disabled():
    # Setup database
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    TestingSession = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    Base.metadata.create_all(bind=engine)
    db = TestingSession()

    # Override settings
    settings = Settings(
        auto_trading_enabled=False, strategy_name="rsi", telegram_bot_token="test_token", telegram_chat_id=12345
    )

    with patch("app.services.auto_trader.get_settings", return_value=settings):
        # We don't seed anything. If it's enabled it would fail/query. Since it's disabled, it should return early.
        await run_auto_trading(db)

    db.close()
    Base.metadata.drop_all(bind=engine)


@pytest.mark.anyio
async def test_auto_trading_buy_signal():
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    TestingSession = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    Base.metadata.create_all(bind=engine)
    db = TestingSession()

    # 1. Seed critical asset and portfolio
    asset = Asset(symbol="XAG", name="Silver", asset_type="metal", is_active=True)
    db.add(asset)
    db.flush()

    portfolio = Portfolio(
        name="default-paper",
        base_currency="USD",
        initial_cash=Decimal("600.00"),
        cash_balance=Decimal("600.00"),
        is_real_money=False,
    )
    db.add(portfolio)
    db.flush()

    # 2. Seed price snapshot and indicator for buy signal (RSI < 30)
    snapshot = PriceSnapshot(
        asset_id=asset.id,
        source="yahoo-si-f",
        buy_price=Decimal("30.00"),
        sell_price=Decimal("29.90"),
        mid_price=Decimal("29.95"),
        currency="USD",
        spread_absolute=Decimal("0.10"),
        spread_percent=Decimal("0.33"),
        observed_at=datetime.datetime.now(datetime.timezone.utc),
    )
    db.add(snapshot)
    db.flush()

    indicator = TechnicalIndicator(
        price_snapshot_id=snapshot.id,
        bar_timestamp=datetime.datetime.now(datetime.timezone.utc),
        timeframe="15m",
        close_usd_oz=Decimal("29.95"),
        rsi_14=Decimal("25.00"),  # Oversold!
        bb_upper_20_2=Decimal("35.00"),
        bb_lower_20_2=Decimal("28.00"),
        sma_20=Decimal("31.00"),
        sma_50=Decimal("32.00"),
    )
    db.add(indicator)
    db.commit()

    # Settings setup
    settings = Settings(
        auto_trading_enabled=True, strategy_name="rsi", telegram_bot_token="test_token", telegram_chat_id=12345
    )

    # Risk decision mock
    mock_risk = RiskDecision(
        decision="allow", reason_code="RISK_CHECK_PASSED", risk_level="low", confidence=Decimal("1.0"), details_json={}
    )

    with (
        patch("app.services.auto_trader.get_settings", return_value=settings),
        patch("app.paper_trading.service.evaluate_paper_trade_risk", return_value=mock_risk),
        patch("app.services.auto_trader.Bot") as MockBot,
    ):
        mock_bot_instance = AsyncMock()
        MockBot.return_value = mock_bot_instance

        # Run auto trading
        await run_auto_trading(db)

        # Check Signal record created
        signal = db.execute(select(Signal).where(Signal.action == "BUY")).scalar_one_or_none()
        assert signal is not None
        assert signal.reason_code == "RSI_OVERSOLD"
        assert signal.price_snapshot_id == snapshot.id
        assert signal.indicator_id == indicator.id

        # Check PaperTrade record created
        trade = db.execute(select(PaperTrade).where(PaperTrade.action == "paper_buy")).scalar_one_or_none()
        assert trade is not None
        assert trade.price == Decimal("30.00")  # snapshot.buy_price
        assert trade.fees == Decimal("0.05")

        # Verify portfolio cash balance updated (600 - net_amount)
        assert portfolio.cash_balance < Decimal("1.00")

        # Verify telegram message was sent
        mock_bot_instance.send_message.assert_called_once()
        sent_text = mock_bot_instance.send_message.call_args[1]["text"]
        assert "SilverPilot Auto-Trading Raporu" in sent_text
        assert "ALIM (BUY)" in sent_text
        assert "XAG (Gümüş)" in sent_text

    db.close()
    Base.metadata.drop_all(bind=engine)


@pytest.mark.anyio
async def test_auto_trading_sell_signal():
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    TestingSession = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    Base.metadata.create_all(bind=engine)
    db = TestingSession()

    # 1. Seed critical asset and portfolio
    asset = Asset(symbol="XAG", name="Silver", asset_type="metal", is_active=True)
    db.add(asset)
    db.flush()

    portfolio = Portfolio(
        name="default-paper",
        base_currency="USD",
        initial_cash=Decimal("600.00"),
        cash_balance=Decimal("100.00"),  # Already invested mostly
        is_real_money=False,
    )
    db.add(portfolio)
    db.flush()

    # 2. Seed open position of 15 XAG
    # To have an open position, we need to add a successful trade
    mock_risk_decision = RiskDecision(
        decision="allow", reason_code="RISK_CHECK_PASSED", risk_level="low", confidence=Decimal("1.0"), details_json={}
    )
    db.add(mock_risk_decision)
    db.flush()

    buy_trade = PaperTrade(
        portfolio_id=portfolio.id,
        asset_id=asset.id,
        action="paper_buy",
        quantity=Decimal("15.000000"),
        price=Decimal("30.000000"),
        gross_amount=Decimal("450.000000"),
        fees=Decimal("0.050000"),
        taxes=Decimal("0.000000"),
        net_amount=Decimal("450.050000"),
        risk_decision_id=mock_risk_decision.id,
    )
    db.add(buy_trade)
    db.flush()

    # 3. Seed price snapshot and indicator for sell signal (RSI > 70)
    snapshot = PriceSnapshot(
        asset_id=asset.id,
        source="yahoo-si-f",
        buy_price=Decimal("35.00"),
        sell_price=Decimal("34.90"),
        mid_price=Decimal("34.95"),
        currency="USD",
        spread_absolute=Decimal("0.10"),
        spread_percent=Decimal("0.28"),
        observed_at=datetime.datetime.now(datetime.timezone.utc),
    )
    db.add(snapshot)
    db.flush()

    indicator = TechnicalIndicator(
        price_snapshot_id=snapshot.id,
        bar_timestamp=datetime.datetime.now(datetime.timezone.utc),
        timeframe="15m",
        close_usd_oz=Decimal("34.95"),
        rsi_14=Decimal("75.00"),  # Overbought!
        bb_upper_20_2=Decimal("33.00"),
        bb_lower_20_2=Decimal("26.00"),
        sma_20=Decimal("29.00"),
        sma_50=Decimal("28.00"),
    )
    db.add(indicator)
    db.commit()

    # Settings setup
    settings = Settings(
        auto_trading_enabled=True, strategy_name="rsi", telegram_bot_token="test_token", telegram_chat_id=12345
    )

    with (
        patch("app.services.auto_trader.get_settings", return_value=settings),
        patch("app.paper_trading.service.evaluate_paper_trade_risk", return_value=mock_risk_decision),
        patch("app.services.auto_trader.Bot") as MockBot,
    ):
        mock_bot_instance = AsyncMock()
        MockBot.return_value = mock_bot_instance

        # Run auto trading
        await run_auto_trading(db)

        # Check Signal record created
        signal = db.execute(select(Signal).where(Signal.action == "SELL")).scalar_one_or_none()
        assert signal is not None
        assert signal.reason_code == "RSI_OVERBOUGHT"

        # Check PaperTrade record created
        trade = db.execute(select(PaperTrade).where(PaperTrade.action == "paper_sell")).scalar_one_or_none()
        assert trade is not None
        assert trade.price == Decimal("34.90")  # snapshot.sell_price
        assert trade.fees == Decimal("0.05")
        assert trade.quantity == Decimal("15.00")

        # Verify portfolio cash balance updated (100 + net_amount)
        # gross = 15 * 34.90 = 523.50
        # net = 523.50 - 0.05 = 523.45
        # cash_balance = 100 + 523.45 = 623.45
        assert portfolio.cash_balance == Decimal("623.45")

        # Verify telegram message was sent
        mock_bot_instance.send_message.assert_called_once()
        sent_text = mock_bot_instance.send_message.call_args[1]["text"]
        assert "SATIM (SELL)" in sent_text

    db.close()
    Base.metadata.drop_all(bind=engine)
