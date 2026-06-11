import pytest
from decimal import Decimal
from unittest.mock import MagicMock, patch
from sqlalchemy.orm import Session

from app.services.strategy import STRATEGY_REGISTRY


@pytest.mark.anyio
async def test_macd_strategy_golden_cross_buy():
    macd_strat = STRATEGY_REGISTRY["macd"]
    db = MagicMock(spec=Session)

    # Golden cross: current macd_line > macd_signal and prev_macd_line <= prev_macd_signal
    context = {
        "macd_line": Decimal("0.5"),
        "macd_signal": Decimal("0.2"),
        "prev_macd_line": Decimal("0.1"),
        "prev_macd_signal": Decimal("0.2"),
        "has_open_position": False,
        "atr_value": Decimal("0.5"),
        "close_value": Decimal("30.0"),
    }
    decision = await macd_strat.evaluate(db, context)
    assert decision.action == "BUY"
    assert decision.reason_code == "MACD_GOLDEN_CROSS"


@pytest.mark.anyio
async def test_macd_strategy_golden_cross_position_open():
    macd_strat = STRATEGY_REGISTRY["macd"]
    db = MagicMock(spec=Session)

    # Golden cross but position already open
    context = {
        "macd_line": Decimal("0.5"),
        "macd_signal": Decimal("0.2"),
        "prev_macd_line": Decimal("0.1"),
        "prev_macd_signal": Decimal("0.2"),
        "has_open_position": True,
        "atr_value": Decimal("0.5"),
        "close_value": Decimal("30.0"),
    }
    decision = await macd_strat.evaluate(db, context)
    assert decision.action == "HOLD"
    assert decision.reason_code == "MACD_GOLDEN_CROSS_BUT_POSITION_OPEN"


@pytest.mark.anyio
async def test_macd_strategy_death_cross_sell():
    macd_strat = STRATEGY_REGISTRY["macd"]
    db = MagicMock(spec=Session)

    # Death cross: current macd_line < macd_signal and prev_macd_line >= prev_macd_signal
    context = {
        "macd_line": Decimal("0.1"),
        "macd_signal": Decimal("0.2"),
        "prev_macd_line": Decimal("0.3"),
        "prev_macd_signal": Decimal("0.2"),
        "has_open_position": True,
        "atr_value": Decimal("0.5"),
        "close_value": Decimal("30.0"),
    }
    decision = await macd_strat.evaluate(db, context)
    assert decision.action == "SELL"
    assert decision.reason_code == "MACD_DEATH_CROSS"


@pytest.mark.anyio
async def test_macd_strategy_death_cross_no_position():
    macd_strat = STRATEGY_REGISTRY["macd"]
    db = MagicMock(spec=Session)

    # Death cross but no position
    context = {
        "macd_line": Decimal("0.1"),
        "macd_signal": Decimal("0.2"),
        "prev_macd_line": Decimal("0.3"),
        "prev_macd_signal": Decimal("0.2"),
        "has_open_position": False,
        "atr_value": Decimal("0.5"),
        "close_value": Decimal("30.0"),
    }
    decision = await macd_strat.evaluate(db, context)
    assert decision.action == "HOLD"
    assert decision.reason_code == "MACD_DEATH_CROSS_BUT_NO_POSITION"


@pytest.mark.anyio
async def test_macd_strategy_no_crossover():
    macd_strat = STRATEGY_REGISTRY["macd"]
    db = MagicMock(spec=Session)

    # No cross
    context = {
        "macd_line": Decimal("0.5"),
        "macd_signal": Decimal("0.2"),
        "prev_macd_line": Decimal("0.4"),
        "prev_macd_signal": Decimal("0.2"),
        "has_open_position": False,
        "atr_value": Decimal("0.5"),
        "close_value": Decimal("30.0"),
    }
    decision = await macd_strat.evaluate(db, context)
    assert decision.action == "HOLD"
    assert decision.reason_code == "MACD_NO_CROSSOVER"


@pytest.mark.anyio
async def test_macd_strategy_insufficient_data():
    macd_strat = STRATEGY_REGISTRY["macd"]
    db = MagicMock(spec=Session)

    # Insufficient data
    context = {
        "macd_line": None,
        "macd_signal": Decimal("0.2"),
        "prev_macd_line": Decimal("0.4"),
        "prev_macd_signal": Decimal("0.2"),
        "has_open_position": False,
    }
    decision = await macd_strat.evaluate(db, context)
    assert decision.action == "HOLD"
    assert decision.reason_code == "MACD_INSUFFICIENT_DATA"


@pytest.mark.anyio
async def test_auto_regime_strategy_sideways_rsi_buy():
    auto_strat = STRATEGY_REGISTRY["auto"]
    db = MagicMock(spec=Session)

    mock_regime = {
        "regime": "SIDEWAYS",
        "adx": 15.0,
        "bb_bandwidth": 0.010,
    }

    # Sideways triggers RSI and Bollinger. RSI < 30 triggers BUY.
    context = {
        "close": Decimal("30.0"),
        "rsi_14": Decimal("25.0"),
        "bb_lower": Decimal("28.0"),
        "bb_upper": Decimal("32.0"),
        "has_open_position": False,
        "atr_value": Decimal("0.5"),
        "close_value": Decimal("30.0"),
    }

    with patch("app.services.regime.get_market_regime", return_value=mock_regime):
        decision = await auto_strat.evaluate(db, context)
        assert decision.action == "BUY"
        assert decision.reason_code == "AUTO_REGIME_SIDEWAYS_BUY"
        assert decision.trend_state == "SIDEWAYS"
        assert decision.buy_score == Decimal("0.6000")  # RSI BUY (0.6) + BB HOLD (0.0) = 0.6 > 0.5


@pytest.mark.anyio
async def test_auto_regime_strategy_sideways_rsi_and_bb_buy():
    auto_strat = STRATEGY_REGISTRY["auto"]
    db = MagicMock(spec=Session)

    mock_regime = {
        "regime": "SIDEWAYS",
        "adx": 20.0,
        "bb_bandwidth": 0.012,
    }

    # Both RSI and BB trigger BUY.
    context = {
        "close": Decimal("27.0"),  # lower than bb_lower
        "rsi_14": Decimal("25.0"),  # lower than 30
        "bb_lower": Decimal("28.0"),
        "bb_upper": Decimal("32.0"),
        "has_open_position": False,
        "atr_value": Decimal("0.5"),
        "close_value": Decimal("27.0"),
    }

    with patch("app.services.regime.get_market_regime", return_value=mock_regime):
        decision = await auto_strat.evaluate(db, context)
        assert decision.action == "BUY"
        assert decision.reason_code == "AUTO_REGIME_SIDEWAYS_BUY"
        assert decision.buy_score == Decimal("1.0000")  # RSI BUY (0.6) + BB BUY (0.4) = 1.0


@pytest.mark.anyio
async def test_auto_regime_strategy_trending_sma_buy():
    auto_strat = STRATEGY_REGISTRY["auto"]
    db = MagicMock(spec=Session)

    mock_regime = {
        "regime": "TRENDING_UP",
        "adx": 30.0,
        "bb_bandwidth": 0.020,
    }

    # Trending triggers SMA Cross and MACD.
    # SMA Cross Golden Cross (BUY), MACD No Cross (HOLD)
    context = {
        "sma_20": Decimal("31.0"),
        "sma_50": Decimal("30.0"),
        "prev_sma_20": Decimal("29.0"),
        "prev_sma_50": Decimal("30.0"),
        "macd_line": Decimal("0.1"),
        "macd_signal": Decimal("0.2"),
        "prev_macd_line": Decimal("0.1"),
        "prev_macd_signal": Decimal("0.2"),
        "has_open_position": False,
        "atr_value": Decimal("0.5"),
        "close_value": Decimal("30.0"),
    }

    with patch("app.services.regime.get_market_regime", return_value=mock_regime):
        decision = await auto_strat.evaluate(db, context)
        assert decision.action == "BUY"
        assert decision.reason_code == "AUTO_REGIME_TRENDING_BUY"
        assert decision.trend_state == "TRENDING_UP"
        assert decision.buy_score == Decimal("0.6000")  # SMA BUY (0.6) + MACD HOLD (0.0) = 0.6 > 0.5


@pytest.mark.anyio
async def test_auto_regime_strategy_trending_both_buy():
    auto_strat = STRATEGY_REGISTRY["auto"]
    db = MagicMock(spec=Session)

    mock_regime = {
        "regime": "TRENDING_UP",
        "adx": 30.0,
        "bb_bandwidth": 0.020,
    }

    # SMA Cross Golden Cross (BUY), MACD Golden Cross (BUY)
    context = {
        "sma_20": Decimal("31.0"),
        "sma_50": Decimal("30.0"),
        "prev_sma_20": Decimal("29.0"),
        "prev_sma_50": Decimal("30.0"),
        "macd_line": Decimal("0.5"),
        "macd_signal": Decimal("0.2"),
        "prev_macd_line": Decimal("0.1"),
        "prev_macd_signal": Decimal("0.2"),
        "has_open_position": False,
        "atr_value": Decimal("0.5"),
        "close_value": Decimal("30.0"),
    }

    with patch("app.services.regime.get_market_regime", return_value=mock_regime):
        decision = await auto_strat.evaluate(db, context)
        assert decision.action == "BUY"
        assert decision.reason_code == "AUTO_REGIME_TRENDING_BUY"
        assert decision.buy_score == Decimal("1.0000")  # SMA BUY (0.6) + MACD BUY (0.4) = 1.0


@pytest.mark.anyio
async def test_auto_regime_strategy_missing_regime_info():
    auto_strat = STRATEGY_REGISTRY["auto"]
    db = MagicMock(spec=Session)

    context = {
        "close": Decimal("30.0"),
        "rsi_14": Decimal("25.0"),
        "bb_lower": Decimal("28.0"),
        "bb_upper": Decimal("32.0"),
        "has_open_position": False,
        "atr_value": Decimal("0.5"),
        "close_value": Decimal("30.0"),
    }

    with patch("app.services.regime.get_market_regime", return_value=None):
        decision = await auto_strat.evaluate(db, context)
        assert decision.action == "BUY"
        assert decision.reason_code == "AUTO_REGIME_SIDEWAYS_BUY"
        assert decision.trend_state == "SIDEWAYS"


@pytest.mark.anyio
async def test_auto_regime_strategy_indicators_none():
    auto_strat = STRATEGY_REGISTRY["auto"]
    db = MagicMock(spec=Session)

    mock_regime = {
        "regime": "SIDEWAYS",
        "adx": None,
        "bb_bandwidth": None,
    }

    context = {
        "close": Decimal("30.0"),
        "rsi_14": Decimal("25.0"),
        "bb_lower": Decimal("28.0"),
        "bb_upper": Decimal("32.0"),
        "has_open_position": False,
        "atr_value": Decimal("0.5"),
        "close_value": Decimal("30.0"),
    }

    with patch("app.services.regime.get_market_regime", return_value=mock_regime):
        decision = await auto_strat.evaluate(db, context)
        assert decision.action == "BUY"
        assert decision.reason_code == "AUTO_REGIME_SIDEWAYS_BUY"


@pytest.mark.anyio
async def test_auto_regime_strategy_adx_boundaries():
    auto_strat = STRATEGY_REGISTRY["auto"]
    db = MagicMock(spec=Session)

    context = {
        "close": Decimal("30.0"),
        "rsi_14": Decimal("25.0"),
        "bb_lower": Decimal("28.0"),
        "bb_upper": Decimal("32.0"),
        "sma_20": Decimal("31.0"),
        "sma_50": Decimal("30.0"),
        "prev_sma_20": Decimal("29.0"),
        "prev_sma_50": Decimal("30.0"),
        "macd_line": Decimal("0.5"),
        "macd_signal": Decimal("0.2"),
        "prev_macd_line": Decimal("0.1"),
        "prev_macd_signal": Decimal("0.2"),
        "has_open_position": False,
        "atr_value": Decimal("0.5"),
        "close_value": Decimal("30.0"),
    }

    with patch(
        "app.services.regime.get_market_regime", return_value={"regime": "SIDEWAYS", "adx": 24.9, "bb_bandwidth": 0.020}
    ):
        decision = await auto_strat.evaluate(db, context)
        assert decision.action == "BUY"
        assert decision.reason_code == "AUTO_REGIME_SIDEWAYS_BUY"

    with patch(
        "app.services.regime.get_market_regime", return_value={"regime": "TRENDING", "adx": 25.0, "bb_bandwidth": 0.020}
    ):
        decision = await auto_strat.evaluate(db, context)
        assert decision.action == "BUY"
        assert decision.reason_code == "AUTO_REGIME_TRENDING_BUY"


@pytest.mark.anyio
async def test_macd_strategy_various_nones():
    macd_strat = STRATEGY_REGISTRY["macd"]
    db = MagicMock(spec=Session)

    base_context = {
        "macd_line": Decimal("0.5"),
        "macd_signal": Decimal("0.2"),
        "prev_macd_line": Decimal("0.1"),
        "prev_macd_signal": Decimal("0.2"),
        "has_open_position": False,
    }

    for key in ["macd_line", "macd_signal", "prev_macd_line", "prev_macd_signal"]:
        context = dict(base_context)
        context[key] = None
        decision = await macd_strat.evaluate(db, context)
        assert decision.action == "HOLD"
        assert decision.reason_code == "MACD_INSUFFICIENT_DATA"
