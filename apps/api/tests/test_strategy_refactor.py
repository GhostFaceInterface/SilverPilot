import pytest
from decimal import Decimal
from unittest.mock import MagicMock
from sqlalchemy.orm import Session
from app.services.strategy import STRATEGY_REGISTRY


@pytest.mark.anyio
async def test_rsi_strategy_polymorphic():
    rsi_strat = STRATEGY_REGISTRY["rsi"]
    db = MagicMock(spec=Session)

    # oversold buy condition
    context = {
        "rsi_14": 25.0,
        "has_open_position": False,
        "atr_value": Decimal("0.5"),
        "close_value": Decimal("30.0"),
    }
    decision = await rsi_strat.evaluate(db, context)
    assert decision.action == "BUY"
    assert decision.reason_code == "RSI_OVERSOLD"
    expected_sl = Decimal("30.0") - max(Decimal("0.5") * Decimal("1.5"), Decimal("30.0") * Decimal("0.01"))
    assert decision.stop_loss_price == expected_sl

    # overbought sell condition
    context_sell = {
        "rsi_14": 75.0,
        "has_open_position": True,
        "atr_value": Decimal("0.5"),
        "close_value": Decimal("30.0"),
    }
    decision_sell = await rsi_strat.evaluate(db, context_sell)
    assert decision_sell.action == "SELL"
    assert decision_sell.reason_code == "RSI_OVERBOUGHT"


@pytest.mark.anyio
async def test_sma_cross_strategy_polymorphic():
    sma_strat = STRATEGY_REGISTRY["sma_cross"]
    db = MagicMock(spec=Session)

    # Golden cross buy
    context = {
        "sma_20": 31.0,
        "sma_50": 30.0,
        "prev_sma_20": 29.0,
        "prev_sma_50": 30.0,
        "has_open_position": False,
        "atr_value": Decimal("0.5"),
        "close_value": Decimal("30.0"),
    }
    decision = await sma_strat.evaluate(db, context)
    assert decision.action == "BUY"
    assert decision.reason_code == "SMA_GOLDEN_CROSS"


@pytest.mark.anyio
async def test_bollinger_strategy_polymorphic():
    bb_strat = STRATEGY_REGISTRY["bollinger"]
    db = MagicMock(spec=Session)

    # Lower band touch buy
    context = {
        "close": 27.5,
        "bb_lower": 28.0,
        "bb_upper": 32.0,
        "has_open_position": False,
        "atr_value": Decimal("0.5"),
        "close_value": Decimal("30.0"),
    }
    decision = await bb_strat.evaluate(db, context)
    assert decision.action == "BUY"
    assert decision.reason_code == "BB_LOWER_TOUCH"
