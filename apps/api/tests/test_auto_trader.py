import datetime
from decimal import Decimal
from unittest.mock import AsyncMock, patch

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.config import Settings
from app.core.db import Base
from app.models import Asset, PaperTrade, Portfolio, PriceSnapshot, RiskDecision, Signal, TechnicalIndicator
from app.services.auto_trader import run_auto_trading
from app.services.indicator_readiness import IndicatorContext, IndicatorReadiness


def _make_context(
    indicator: TechnicalIndicator | None,
    *,
    timeframe: str,
    usable: bool = True,
    status: str = "ready",
    reason_codes: list[str] | None = None,
    source: str = "yahoo-si-f",
) -> IndicatorContext:
    readiness = IndicatorReadiness(
        asset_symbol="XAG_GRAM",
        timeframe=timeframe,
        status=status,
        usable=usable,
        reason_codes=reason_codes or [],
        required_min_bar_count=1,
        required_fields=(),
        indicator=indicator,
        indicator_id=indicator.id if indicator is not None else None,
        market_bar_id=indicator.market_bar_id if indicator is not None else None,
        price_snapshot_id=indicator.price_snapshot_id if indicator is not None else None,
        source=source,
        bar_timestamp=indicator.bar_timestamp if indicator is not None else None,
        age_seconds=0,
        freshness_minutes=60,
        calculation_version=indicator.calculation_version if indicator is not None else None,
        quality_status="ok" if indicator is not None else None,
        input_bar_count=indicator.input_bar_count if indicator is not None else None,
        missing_required_fields=[],
        close_usd_oz=indicator.close_usd_oz if indicator is not None else None,
    )
    return IndicatorContext(readiness=readiness, previous_indicator=None)


def _seed_runtime_state():
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    testing_session = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    Base.metadata.create_all(bind=engine)
    db = testing_session()

    asset = Asset(symbol="XAG_GRAM", name="Gram Silver", asset_type="metal", is_active=True)
    db.add(asset)
    db.flush()

    portfolio = Portfolio(
        name="gram-paper",
        base_currency="USD",
        initial_cash=Decimal("600.00"),
        cash_balance=Decimal("600.00"),
        is_real_money=False,
    )
    db.add(portfolio)
    db.flush()

    snapshots = {}
    indicators = {}
    for timeframe, price in (("1d", Decimal("31.00")), ("1h", Decimal("30.00")), ("5m", Decimal("30.20"))):
        snapshot = PriceSnapshot(
            asset_id=asset.id,
            source="yahoo-si-f",
            buy_price=price + Decimal("0.05"),
            sell_price=price - Decimal("0.05"),
            mid_price=price,
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
            timeframe=timeframe,
            calculation_version="technical-indicators-v2",
            input_bar_count=100,
            quality_status="ok",
            close_usd_oz=price,
            rsi_14=Decimal("50.00"),
            macd_histogram=Decimal("0.2000"),
            bb_middle_20_2=price - Decimal("0.10"),
            bb_upper_20_2=price + Decimal("1.00"),
            bb_lower_20_2=price - Decimal("1.00"),
            sma_20=price - Decimal("0.20"),
            sma_50=price - Decimal("0.50"),
            atr_14=Decimal("0.40"),
        )
        db.add(indicator)
        db.flush()
        snapshots[timeframe] = snapshot
        indicators[timeframe] = indicator

    db.commit()
    return engine, db, asset, portfolio, snapshots, indicators


@pytest.mark.anyio
async def test_auto_trading_disabled():
    engine, db, _, _, _, _ = _seed_runtime_state()
    settings = Settings(
        auto_trading_enabled=False,
        strategy_name="rsi",
        telegram_bot_token="token",
        telegram_chat_id=1,
    )

    with patch("app.services.auto_trader.get_settings", return_value=settings):
        await run_auto_trading(db)

    db.close()
    Base.metadata.drop_all(bind=engine)
    engine.dispose()


@pytest.mark.anyio
async def test_auto_trading_uses_strategy_v2_and_trade_intent():
    engine, db, _, portfolio, _, indicators = _seed_runtime_state()
    settings = Settings(
        auto_trading_enabled=True,
        strategy_name="rsi",
        telegram_bot_token="token",
        telegram_chat_id=1,
    )
    contexts = {
        "1d": _make_context(indicators["1d"], timeframe="1d"),
        "1h": _make_context(indicators["1h"], timeframe="1h"),
        "5m": _make_context(indicators["5m"], timeframe="5m"),
    }
    allow_decision = RiskDecision(
        decision="allow",
        reason_code="RISK_CHECK_PASSED",
        risk_level="low",
        confidence=Decimal("1.0000"),
        details_json={},
    )
    db.add(allow_decision)
    db.flush()

    with (
        patch("app.services.auto_trader.get_settings", return_value=settings),
        patch("app.services.auto_trader.get_strategy_timeframe_contexts", return_value=contexts),
        patch("app.services.trade_intents.evaluate_paper_trade_risk", return_value=allow_decision),
        patch("app.services.telegram.Bot") as bot_cls,
    ):
        bot = AsyncMock()
        bot_cls.return_value = bot

        await run_auto_trading(db)

        signal = db.execute(select(Signal).order_by(Signal.id.desc())).scalar_one()
        assert signal.action == "BUY"
        assert signal.reason_code == "STRATEGY_V2_BUY_CONFIRMED"
        assert signal.details_json["strategy_name"] == "strategy_v2"
        assert signal.details_json["timeframe_policy"] == {"trend": "1d", "entry": "1h", "execution": "5m"}
        assert signal.details_json["stop_loss_price"] is not None
        assert signal.details_json["take_profit_price"] is not None

        trade = db.execute(select(PaperTrade).where(PaperTrade.action == "paper_buy")).scalar_one()
        assert trade.risk_decision.reason_code == "RISK_CHECK_PASSED"
        assert portfolio.cash_balance < Decimal("0.001000")
        bot.send_message.assert_called_once()

    db.close()
    Base.metadata.drop_all(bind=engine)
    engine.dispose()


@pytest.mark.anyio
async def test_auto_trading_holds_when_daily_trend_missing():
    engine, db, _, portfolio, _, indicators = _seed_runtime_state()
    settings = Settings(auto_trading_enabled=True, telegram_bot_token="token", telegram_chat_id=1)
    contexts = {
        "1d": _make_context(None, timeframe="1d", usable=False, status="empty", reason_codes=["INDICATOR_NOT_FOUND"]),
        "1h": _make_context(indicators["1h"], timeframe="1h"),
        "5m": _make_context(indicators["5m"], timeframe="5m"),
    }

    with (
        patch("app.services.auto_trader.get_settings", return_value=settings),
        patch("app.services.auto_trader.get_strategy_timeframe_contexts", return_value=contexts),
        patch("app.services.telegram.Bot") as bot_cls,
    ):
        bot = AsyncMock()
        bot_cls.return_value = bot

        await run_auto_trading(db)

        signal = db.execute(select(Signal).order_by(Signal.id.desc())).scalar_one()
        assert signal.action == "HOLD"
        assert signal.reason_code == "DAILY_TREND_MISSING"
        assert signal.details_json["readiness_block_flags"] == ["DAILY_TREND_MISSING"]
        assert db.execute(select(PaperTrade)).scalars().all() == []
        assert portfolio.cash_balance == Decimal("600.00")
        bot.send_message.assert_called_once()

    db.close()
    Base.metadata.drop_all(bind=engine)
    engine.dispose()


@pytest.mark.anyio
async def test_auto_trading_holds_when_execution_timeframe_stale():
    engine, db, _, portfolio, _, indicators = _seed_runtime_state()
    settings = Settings(auto_trading_enabled=True, telegram_bot_token="token", telegram_chat_id=1)
    contexts = {
        "1d": _make_context(indicators["1d"], timeframe="1d"),
        "1h": _make_context(indicators["1h"], timeframe="1h"),
        "5m": _make_context(
            indicators["5m"], timeframe="5m", usable=False, status="stale", reason_codes=["INDICATOR_STALE"]
        ),
    }

    with (
        patch("app.services.auto_trader.get_settings", return_value=settings),
        patch("app.services.auto_trader.get_strategy_timeframe_contexts", return_value=contexts),
        patch("app.services.telegram.Bot") as bot_cls,
    ):
        bot = AsyncMock()
        bot_cls.return_value = bot

        await run_auto_trading(db)

        signal = db.execute(select(Signal).order_by(Signal.id.desc())).scalar_one()
        assert signal.action == "HOLD"
        assert signal.reason_code == "EXECUTION_TIMEFRAME_STALE"
        assert "EXECUTION_TIMEFRAME_STALE" in signal.details_json["readiness_block_flags"]
        assert db.execute(select(PaperTrade)).scalars().all() == []
        assert portfolio.cash_balance == Decimal("600.00")
        bot.send_message.assert_called_once()

    db.close()
    Base.metadata.drop_all(bind=engine)
    engine.dispose()


@pytest.mark.anyio
async def test_auto_trading_holds_when_entry_timeframe_stale():
    engine, db, _, portfolio, _, indicators = _seed_runtime_state()
    settings = Settings(auto_trading_enabled=True, telegram_bot_token="token", telegram_chat_id=1)
    contexts = {
        "1d": _make_context(indicators["1d"], timeframe="1d"),
        "1h": _make_context(
            indicators["1h"], timeframe="1h", usable=False, status="stale", reason_codes=["INDICATOR_STALE"]
        ),
        "5m": _make_context(indicators["5m"], timeframe="5m"),
    }

    with (
        patch("app.services.auto_trader.get_settings", return_value=settings),
        patch("app.services.auto_trader.get_strategy_timeframe_contexts", return_value=contexts),
        patch("app.services.telegram.Bot") as bot_cls,
    ):
        bot = AsyncMock()
        bot_cls.return_value = bot

        await run_auto_trading(db)

        signal = db.execute(select(Signal).order_by(Signal.id.desc())).scalar_one()
        assert signal.action == "HOLD"
        assert signal.reason_code == "ENTRY_TIMEFRAME_STALE"
        assert "ENTRY_TIMEFRAME_STALE" in signal.details_json["readiness_block_flags"]
        assert db.execute(select(PaperTrade)).scalars().all() == []
        assert portfolio.cash_balance == Decimal("600.00")
        bot.send_message.assert_called_once()

    db.close()
    Base.metadata.drop_all(bind=engine)
    engine.dispose()


@pytest.mark.anyio
async def test_auto_trading_holds_when_timeframe_sources_do_not_align():
    engine, db, _, portfolio, _, indicators = _seed_runtime_state()
    settings = Settings(auto_trading_enabled=True, telegram_bot_token="token", telegram_chat_id=1)
    contexts = {
        "1d": _make_context(indicators["1d"], timeframe="1d", source="yahoo-si-f"),
        "1h": _make_context(indicators["1h"], timeframe="1h", source="gold-api-xag-usd"),
        "5m": _make_context(indicators["5m"], timeframe="5m", source="yahoo-si-f"),
    }

    with (
        patch("app.services.auto_trader.get_settings", return_value=settings),
        patch("app.services.auto_trader.get_strategy_timeframe_contexts", return_value=contexts),
        patch("app.services.telegram.Bot") as bot_cls,
    ):
        bot = AsyncMock()
        bot_cls.return_value = bot

        await run_auto_trading(db)

        signal = db.execute(select(Signal).order_by(Signal.id.desc())).scalar_one()
        assert signal.action == "HOLD"
        assert signal.reason_code == "TIMEFRAME_SOURCE_MISMATCH"
        assert "TIMEFRAME_SOURCE_MISMATCH" in signal.details_json["readiness_block_flags"]
        assert db.execute(select(PaperTrade)).scalars().all() == []
        assert portfolio.cash_balance == Decimal("600.00")
        bot.send_message.assert_called_once()

    db.close()
    Base.metadata.drop_all(bind=engine)
    engine.dispose()
