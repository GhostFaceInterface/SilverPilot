import datetime
from decimal import Decimal
from unittest.mock import AsyncMock, patch
import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.db import Base
from app.core.config import Settings
from app.models import (
    Asset,
    MarketBar,
    Portfolio,
    PriceSnapshot,
    TechnicalIndicator,
    Signal,
    PaperTrade,
    RiskDecision,
    AgentMemoryEvent,
)
from app.services.regime import get_market_regime
from app.services.strategy import StrategyRunner
from app.services.auto_trader import run_auto_trading
from app.services.indicator_readiness import IndicatorContext, IndicatorReadiness


def _ready_indicator_context(latest_indicator, previous_indicator=None, timeframe="5m") -> IndicatorContext:
    readiness = IndicatorReadiness(
        asset_symbol="XAG_GRAM",
        timeframe=timeframe,
        status="ready",
        usable=True,
        reason_codes=[],
        required_min_bar_count=50,
        required_fields=(),
        indicator=latest_indicator,
        indicator_id=latest_indicator.id,
        market_bar_id=latest_indicator.market_bar_id,
        price_snapshot_id=latest_indicator.price_snapshot_id,
        source=latest_indicator.price_snapshot.source if latest_indicator.price_snapshot else "yahoo-si-f",
        bar_timestamp=latest_indicator.bar_timestamp,
        age_seconds=0,
        freshness_minutes=60,
        calculation_version=latest_indicator.calculation_version,
        quality_status="ok",
        input_bar_count=latest_indicator.input_bar_count,
        missing_required_fields=[],
        close_usd_oz=latest_indicator.close_usd_oz,
    )
    return IndicatorContext(readiness=readiness, previous_indicator=previous_indicator)


def seed_indicator_history(db, asset, count=15, timeframe="5m", source="yahoo-si-f"):
    """Utility to seed historical PriceSnapshots, MarketBars and TechnicalIndicators for tests."""
    now = datetime.datetime.now(datetime.timezone.utc)
    indicators = []
    for i in range(count):
        observed_time = now - datetime.timedelta(minutes=5 * (count - i))
        # Increasing price pattern for trending behavior or static for sideways
        price = Decimal("25.00") + Decimal(str(i * 0.1))

        snapshot = PriceSnapshot(
            asset_id=asset.id,
            source=source,
            buy_price=price + Decimal("0.05"),
            sell_price=price - Decimal("0.05"),
            mid_price=price,
            currency="USD",
            spread_absolute=Decimal("0.10"),
            spread_percent=Decimal("0.4"),
            observed_at=observed_time,
        )
        db.add(snapshot)
        db.flush()

        bar_start = observed_time.replace(second=0, microsecond=0)
        bar_start = bar_start - datetime.timedelta(minutes=bar_start.minute % 5)
        market_bar = MarketBar(
            asset_id=asset.id,
            source=source,
            timeframe=timeframe,
            bar_start_at=bar_start,
            bar_end_at=bar_start + datetime.timedelta(minutes=5),
            open=price,
            high=price + Decimal("0.2"),
            low=price - Decimal("0.2"),
            close=price,
            currency="USD",
            sample_count=1,
            first_price_snapshot_id=snapshot.id,
            last_price_snapshot_id=snapshot.id,
            quality_status="ok",
            bar_builder_version="market-bars-v1",
        )
        db.add(market_bar)
        db.flush()

        indicator = TechnicalIndicator(
            price_snapshot_id=snapshot.id,
            market_bar_id=market_bar.id,
            bar_timestamp=bar_start,
            timeframe=timeframe,
            calculation_version="technical-indicators-v2",
            input_bar_count=i + 1,
            quality_status="ok",
            close_usd_oz=price,
            rsi_14=Decimal("45.0") + Decimal(str(i)),
            bb_upper_20_2=price + Decimal("1.5"),
            bb_middle_20_2=price,
            bb_lower_20_2=price - Decimal("1.5"),
            sma_20=price - Decimal("0.2"),
            sma_50=price - Decimal("0.5"),
            ema_20=price - Decimal("0.1"),
            ema_50=price - Decimal("0.3"),
            ema_200=price - Decimal("0.8"),
            adx_14=Decimal("20.0"),
            plus_di_14=Decimal("22.0"),
            minus_di_14=Decimal("18.0"),
            bb_bandwidth_20_2=Decimal("0.12"),
            bb_percent_b_20_2=Decimal("0.55"),
            atr_14=Decimal("0.3"),
            atr_percent_14=Decimal("0.012"),
            rsi_slope_1=Decimal("0.5"),
            macd_histogram_slope_1=Decimal("0.01"),
        )
        db.add(indicator)
        indicators.append(indicator)
    db.commit()
    return indicators


@pytest.mark.anyio
async def test_regime_classifier_sideways_coldstart():
    """Verify get_market_regime returns SIDEWAYS safely with clean fallbacks on cold start."""
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    TestingSession = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    Base.metadata.create_all(bind=engine)
    db = TestingSession()

    try:
        # Fewer than 14 records -> cold start
        asset = Asset(symbol="XAG_GRAM", name="Gram Silver", asset_type="metal", is_active=True)
        db.add(asset)
        db.flush()

        seed_indicator_history(db, asset, count=5)

        regime = get_market_regime(db)
        assert regime["regime"] == "SIDEWAYS"
        assert regime["adx"] == 0.0
        assert regime["bb_bandwidth"] == 0.0

    finally:
        db.close()
        Base.metadata.drop_all(bind=engine)


@pytest.mark.anyio
async def test_regime_classifier_trending():
    """Verify get_market_regime calculates correct market variables when seeded."""
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    TestingSession = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    Base.metadata.create_all(bind=engine)
    db = TestingSession()

    try:
        asset = Asset(symbol="XAG_GRAM", name="Gram Silver", asset_type="metal", is_active=True)
        db.add(asset)
        db.flush()

        seed_indicator_history(db, asset, count=50)

        regime = get_market_regime(db)
        assert "regime" in regime
        assert "adx" in regime
        assert "bb_bandwidth" in regime
        assert "relative_atr" in regime

    finally:
        db.close()
        Base.metadata.drop_all(bind=engine)


@pytest.mark.anyio
async def test_blended_strategy_votes():
    """Verify evaluate_blended_strategies aggregates all core strategy votes correctly."""
    votes = StrategyRunner.evaluate_blended_strategies(
        close=Decimal("25.00"),
        rsi_14=Decimal("25.00"),  # BUY in RSI
        sma_20=Decimal("26.00"),
        sma_50=Decimal("24.00"),
        prev_sma_20=Decimal("23.00"),
        prev_sma_50=Decimal("23.50"),  # BUY in SMA Cross (Golden Cross)
        bb_lower=Decimal("26.00"),
        bb_upper=Decimal("30.00"),
        has_open_position=False,
    )

    assert "rsi" in votes
    assert "bollinger" in votes
    assert "sma_cross" in votes

    assert votes["rsi"]["action"] == "BUY"
    assert votes["sma_cross"]["action"] == "BUY"
    assert votes["bollinger"]["action"] == "BUY"  # Close 25.0 <= bb_lower 26.0


@pytest.mark.anyio
async def test_auto_trading_blended_bullish_consensus():
    """Verify that when the consensus is BULLISH, a BUY paper trade is executed."""
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    TestingSession = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    Base.metadata.create_all(bind=engine)
    db = TestingSession()

    try:
        # Seed asset and portfolio
        asset = Asset(symbol="XAG_GRAM", name="Gram Silver", asset_type="metal", is_active=True)
        db.add(asset)
        db.flush()

        portfolio = Portfolio(
            name="gram-paper",
            base_currency="USD",
            initial_cash=Decimal("1000.00"),
            cash_balance=Decimal("1000.00"),
            is_real_money=False,
        )
        db.add(portfolio)
        db.flush()

        db.add(
            PriceSnapshot(
                asset_id=asset.id,
                source="tcmb-today-xml",
                buy_price=Decimal("32.00"),
                sell_price=Decimal("32.00"),
                mid_price=Decimal("32.00"),
                currency="TRY",
                spread_absolute=Decimal("0.0"),
                spread_percent=Decimal("0.0"),
                observed_at=datetime.datetime.now(datetime.timezone.utc),
            )
        )
        db.flush()

        indicators = seed_indicator_history(db, asset, count=16)
        latest_indicator = indicators[-1]
        prev_indicator = indicators[-2] if len(indicators) > 1 else None

        settings = Settings(
            auto_trading_enabled=True, strategy_name="blended", telegram_bot_token="test_token", telegram_chat_id=12345
        )

        mock_risk = RiskDecision(
            decision="allow",
            reason_code="RISK_CHECK_PASSED",
            risk_level="low",
            confidence=Decimal("1.0"),
            details_json={},
        )

        mock_llm_response = {
            "content": '{"resolved_stance": "BULLISH", "confidence": 0.9, "resolution_markdown": "Test BULLISH Arbiter justification."}'
        }

        with (
            patch("app.services.auto_trader.get_settings", return_value=settings),
            patch(
                "app.services.auto_trader.get_latest_indicator_context",
                return_value=_ready_indicator_context(latest_indicator, prev_indicator),
            ),
            patch("app.paper_trading.service.evaluate_paper_trade_risk", return_value=mock_risk),
            patch("app.llm.gateway.DeepSeekGateway.generate_completion", return_value=mock_llm_response),
            patch("app.services.telegram.Bot") as MockBot,
        ):
            mock_bot_instance = AsyncMock()
            MockBot.return_value = mock_bot_instance

            # Execute trader
            await run_auto_trading(db)

            # Check Blended Consensus AgentMemoryEvent
            event = db.execute(
                select(AgentMemoryEvent).where(AgentMemoryEvent.event_type == "blended_consensus_resolution")
            ).scalar_one_or_none()
            assert event is not None
            assert event.value_json["resolved_stance"] == "BULLISH"
            assert event.value_json["confidence"] == 0.9
            assert "Test BULLISH Arbiter justification" in event.value_json["resolution_markdown"]

            # Check Signal record
            signal = db.execute(select(Signal).where(Signal.action == "BUY")).scalar_one_or_none()
            assert signal is not None
            assert signal.reason_code == "BLENDED_BULLISH"
            assert signal.details_json["strategy_name"] == "blended"
            assert "regime_info" in signal.details_json
            assert "strategy_votes" in signal.details_json
            assert signal.details_json["arbiter_decision"] == "BULLISH"

            # Check PaperTrade record
            trade = db.execute(select(PaperTrade).where(PaperTrade.action == "paper_buy")).scalar_one_or_none()
            assert trade is not None
            assert trade.fees == Decimal("0.050000")

            # Check silent value for notification (BULLISH is not silent)
            mock_bot_instance.send_message.assert_called_once()
            called_args = mock_bot_instance.send_message.call_args[1]
            assert called_args["disable_notification"] is False
            assert "SilverPilot Canlı Analiz Raporu" in called_args["text"]
            assert "Yüce Hakem Kararı:" in called_args["text"]

    finally:
        db.close()
        Base.metadata.drop_all(bind=engine)


@pytest.mark.anyio
async def test_auto_trading_blended_neutral_consensus_silent():
    """Verify that when consensus is NEUTRAL, action is HOLD, and silent Telegram message is dispatched."""
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    TestingSession = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    Base.metadata.create_all(bind=engine)
    db = TestingSession()

    try:
        # Seed asset and portfolio
        asset = Asset(symbol="XAG_GRAM", name="Gram Silver", asset_type="metal", is_active=True)
        db.add(asset)
        db.flush()

        portfolio = Portfolio(
            name="gram-paper",
            base_currency="USD",
            initial_cash=Decimal("1000.00"),
            cash_balance=Decimal("1000.00"),
            is_real_money=False,
        )
        db.add(portfolio)
        db.flush()

        indicators = seed_indicator_history(db, asset, count=16)
        latest_indicator = indicators[-1]
        prev_indicator = indicators[-2] if len(indicators) > 1 else None

        settings = Settings(
            auto_trading_enabled=True, strategy_name="blended", telegram_bot_token="test_token", telegram_chat_id=12345
        )

        mock_llm_response = {
            "content": '{"resolved_stance": "NEUTRAL", "confidence": 0.75, "resolution_markdown": "Test NEUTRAL justification."}'
        }

        with (
            patch("app.services.auto_trader.get_settings", return_value=settings),
            patch(
                "app.services.auto_trader.get_latest_indicator_context",
                return_value=_ready_indicator_context(latest_indicator, prev_indicator),
            ),
            patch("app.llm.gateway.DeepSeekGateway.generate_completion", return_value=mock_llm_response),
            patch("app.services.telegram.Bot") as MockBot,
        ):
            mock_bot_instance = AsyncMock()
            MockBot.return_value = mock_bot_instance

            # Execute trader
            await run_auto_trading(db)

            # Check Signal record (should be HOLD)
            signal = db.execute(select(Signal).where(Signal.action == "HOLD")).scalar_one_or_none()
            assert signal is not None
            assert signal.reason_code == "BLENDED_NEUTRAL"

            # No trade should be executed
            trade = db.execute(select(PaperTrade)).scalar_one_or_none()
            assert trade is None

            # Verify silent Telegram message was sent with disable_notification=True
            mock_bot_instance.send_message.assert_called_once()
            called_args = mock_bot_instance.send_message.call_args[1]
            assert called_args["disable_notification"] is True
            assert "BEKLE (HOLD)" in called_args["text"]
            assert "Test NEUTRAL justification." in called_args["text"]

    finally:
        db.close()
        Base.metadata.drop_all(bind=engine)
