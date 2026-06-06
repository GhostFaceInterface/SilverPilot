from app.services.strategy import StrategyRunner


class TestStrategyRunnerRSI:
    def test_rsi_oversold_no_position(self):
        action, reason = StrategyRunner.evaluate_rsi_strategy(25.0, has_open_position=False)
        assert action == "BUY"
        assert reason == "RSI_OVERSOLD"

    def test_rsi_oversold_with_position(self):
        action, reason = StrategyRunner.evaluate_rsi_strategy(25.0, has_open_position=True)
        assert action == "HOLD"
        assert reason == "RSI_OVERSOLD_BUT_POSITION_OPEN"

    def test_rsi_overbought_with_position(self):
        action, reason = StrategyRunner.evaluate_rsi_strategy(75.0, has_open_position=True)
        assert action == "SELL"
        assert reason == "RSI_OVERBOUGHT"

    def test_rsi_overbought_no_position(self):
        action, reason = StrategyRunner.evaluate_rsi_strategy(75.0, has_open_position=False)
        assert action == "HOLD"
        assert reason == "RSI_OVERBOUGHT_BUT_NO_POSITION"

    def test_rsi_neutral(self):
        action, reason = StrategyRunner.evaluate_rsi_strategy(50.0, has_open_position=False)
        assert action == "HOLD"
        assert reason == "RSI_NEUTRAL"

    def test_rsi_invalid(self):
        # Test None
        action, reason = StrategyRunner.evaluate_rsi_strategy(None, has_open_position=False)
        assert action == "HOLD"
        assert reason == "RSI_INSUFFICIENT_DATA"

        # Test NaN
        action, reason = StrategyRunner.evaluate_rsi_strategy(float("nan"), has_open_position=False)
        assert action == "HOLD"
        assert reason == "RSI_INSUFFICIENT_DATA"


class TestStrategyRunnerSMACross:
    def test_sma_golden_cross_no_position(self):
        # sma_20 > sma_50 (22 > 20) AND prev_sma_20 <= prev_sma_50 (18 <= 19)
        action, reason = StrategyRunner.evaluate_sma_cross_strategy(
            sma_20=22.0, sma_50=20.0, prev_sma_20=18.0, prev_sma_50=19.0, has_open_position=False
        )
        assert action == "BUY"
        assert reason == "SMA_GOLDEN_CROSS"

    def test_sma_golden_cross_with_position(self):
        action, reason = StrategyRunner.evaluate_sma_cross_strategy(
            sma_20=22.0, sma_50=20.0, prev_sma_20=18.0, prev_sma_50=19.0, has_open_position=True
        )
        assert action == "HOLD"
        assert reason == "SMA_GOLDEN_CROSS_BUT_POSITION_OPEN"

    def test_sma_death_cross_with_position(self):
        # sma_20 < sma_50 (18 < 20) AND prev_sma_20 >= prev_sma_50 (22 >= 21)
        action, reason = StrategyRunner.evaluate_sma_cross_strategy(
            sma_20=18.0, sma_50=20.0, prev_sma_20=22.0, prev_sma_50=21.0, has_open_position=True
        )
        assert action == "SELL"
        assert reason == "SMA_DEATH_CROSS"

    def test_sma_death_cross_no_position(self):
        action, reason = StrategyRunner.evaluate_sma_cross_strategy(
            sma_20=18.0, sma_50=20.0, prev_sma_20=22.0, prev_sma_50=21.0, has_open_position=False
        )
        assert action == "HOLD"
        assert reason == "SMA_DEATH_CROSS_BUT_NO_POSITION"

    def test_sma_no_crossover(self):
        action, reason = StrategyRunner.evaluate_sma_cross_strategy(
            sma_20=22.0, sma_50=20.0, prev_sma_20=21.0, prev_sma_50=19.0, has_open_position=False
        )
        assert action == "HOLD"
        assert reason == "SMA_NO_CROSSOVER"

    def test_sma_invalid(self):
        action, reason = StrategyRunner.evaluate_sma_cross_strategy(
            sma_20=None, sma_50=20.0, prev_sma_20=21.0, prev_sma_50=19.0, has_open_position=False
        )
        assert action == "HOLD"
        assert reason == "SMA_INSUFFICIENT_DATA"

        action, reason = StrategyRunner.evaluate_sma_cross_strategy(
            sma_20=22.0, sma_50=float("nan"), prev_sma_20=21.0, prev_sma_50=19.0, has_open_position=False
        )
        assert action == "HOLD"
        assert reason == "SMA_INSUFFICIENT_DATA"


class TestStrategyRunnerBollinger:
    def test_bb_lower_touch_no_position(self):
        action, reason = StrategyRunner.evaluate_bb_strategy(
            close=10.0, bb_lower=10.5, bb_upper=15.0, has_open_position=False
        )
        assert action == "BUY"
        assert reason == "BB_LOWER_TOUCH"

    def test_bb_lower_touch_with_position(self):
        action, reason = StrategyRunner.evaluate_bb_strategy(
            close=10.0, bb_lower=10.5, bb_upper=15.0, has_open_position=True
        )
        assert action == "HOLD"
        assert reason == "BB_LOWER_TOUCH_BUT_POSITION_OPEN"

    def test_bb_upper_touch_with_position(self):
        action, reason = StrategyRunner.evaluate_bb_strategy(
            close=15.5, bb_lower=10.0, bb_upper=15.0, has_open_position=True
        )
        assert action == "SELL"
        assert reason == "BB_UPPER_TOUCH"

    def test_bb_upper_touch_no_position(self):
        action, reason = StrategyRunner.evaluate_bb_strategy(
            close=15.5, bb_lower=10.0, bb_upper=15.0, has_open_position=False
        )
        assert action == "HOLD"
        assert reason == "BB_UPPER_TOUCH_BUT_NO_POSITION"

    def test_bb_neutral(self):
        action, reason = StrategyRunner.evaluate_bb_strategy(
            close=12.0, bb_lower=10.0, bb_upper=15.0, has_open_position=False
        )
        assert action == "HOLD"
        assert reason == "BB_NEUTRAL"

    def test_bb_invalid(self):
        action, reason = StrategyRunner.evaluate_bb_strategy(
            close=12.0, bb_lower=None, bb_upper=15.0, has_open_position=False
        )
        assert action == "HOLD"
        assert reason == "BB_INSUFFICIENT_DATA"


class TestStrategyRunnerAllRouting:
    def test_routing_rsi(self):
        action, reason = StrategyRunner.evaluate_all_strategies(
            close=12.0,
            rsi_14=25.0,
            sma_20=None,
            sma_50=None,
            prev_sma_20=None,
            prev_sma_50=None,
            bb_lower=None,
            bb_upper=None,
            has_open_position=False,
            strategy_name="rsi",
        )
        assert action == "BUY"
        assert reason == "RSI_OVERSOLD"

    def test_routing_sma_cross(self):
        action, reason = StrategyRunner.evaluate_all_strategies(
            close=12.0,
            rsi_14=None,
            sma_20=22.0,
            sma_50=20.0,
            prev_sma_20=18.0,
            prev_sma_50=19.0,
            bb_lower=None,
            bb_upper=None,
            has_open_position=False,
            strategy_name="sma_cross",
        )
        assert action == "BUY"
        assert reason == "SMA_GOLDEN_CROSS"

    def test_routing_bollinger(self):
        action, reason = StrategyRunner.evaluate_all_strategies(
            close=10.0,
            rsi_14=None,
            sma_20=None,
            sma_50=None,
            prev_sma_20=None,
            prev_sma_50=None,
            bb_lower=10.5,
            bb_upper=15.0,
            has_open_position=False,
            strategy_name="bollinger",
        )
        assert action == "BUY"
        assert reason == "BB_LOWER_TOUCH"

    def test_routing_unknown(self):
        action, reason = StrategyRunner.evaluate_all_strategies(
            close=10.0,
            rsi_14=None,
            sma_20=None,
            sma_50=None,
            prev_sma_20=None,
            prev_sma_50=None,
            bb_lower=10.5,
            bb_upper=15.0,
            has_open_position=False,
            strategy_name="invalid_strategy_name",  # type: ignore
        )
        assert action == "HOLD"
        assert reason == "UNKNOWN_STRATEGY"


class TestStrategyRunnerV2:
    def test_single_oversold_rsi_cannot_buy_by_itself(self):
        decision = StrategyRunner.evaluate_strategy_v2(
            daily_close=30.0,
            daily_sma_20=29.0,
            daily_sma_50=28.0,
            entry_close=28.0,
            entry_rsi_14=25.0,
            entry_sma_20=28.0,
            entry_sma_50=28.0,
            entry_macd_histogram=0.0,
            entry_bb_middle=29.0,
            entry_atr_14=0.4,
            has_open_position=False,
        )
        assert decision.action == "HOLD"
        assert decision.reason_code == "STRATEGY_V2_INSUFFICIENT_CONFIRMATION"

    def test_daily_trend_down_blocks_buy(self):
        decision = StrategyRunner.evaluate_strategy_v2(
            daily_close=28.0,
            daily_sma_20=29.0,
            daily_sma_50=30.0,
            entry_close=30.0,
            entry_rsi_14=52.0,
            entry_sma_20=30.0,
            entry_sma_50=29.0,
            entry_macd_histogram=0.3,
            entry_bb_middle=29.5,
            entry_atr_14=0.4,
            has_open_position=False,
        )
        assert decision.action == "HOLD"
        assert decision.reason_code == "DAILY_TREND_DOWN_BUY_BLOCK"
