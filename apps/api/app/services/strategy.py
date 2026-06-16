import math
from dataclasses import dataclass
from decimal import Decimal
from typing import Literal, TYPE_CHECKING
from sqlalchemy.orm import Session
from app.services.base import BaseStrategy

if TYPE_CHECKING:
    from app.models.entities import AgentMemoryEvent


StrategyType = Literal[
    "rsi",
    "sma_cross",
    "bollinger",
    "rsi_with_agents",
    "sma_cross_with_agents",
    "bollinger_with_agents",
    "blended",
    "macd",
    "auto",
]

CONFIDENCE_QUANT = Decimal("0.0001")


@dataclass(frozen=True)
class StrategyDecision:
    action: str
    reason_code: str
    confidence: Decimal
    trend_state: str
    entry_state: str
    execution_state: str
    buy_score: Decimal
    sell_score: Decimal
    component_scores: dict[str, float]
    readiness_block_flags: list[str]
    stop_loss_price: Decimal | None
    take_profit_price: Decimal | None
    expected_exit_price: Decimal | None
    exit_metadata: dict[str, str | float | None]

    def to_signal_details(self) -> dict:
        return {
            "action": self.action,
            "reason_code": self.reason_code,
            "confidence": float(self.confidence),
            "trend_state": self.trend_state,
            "entry_state": self.entry_state,
            "execution_state": self.execution_state,
            "buy_score": float(self.buy_score),
            "sell_score": float(self.sell_score),
            "component_scores": self.component_scores,
            "readiness_block_flags": list(self.readiness_block_flags),
            "stop_loss_price": float(self.stop_loss_price) if self.stop_loss_price is not None else None,
            "take_profit_price": float(self.take_profit_price) if self.take_profit_price is not None else None,
            "expected_exit_price": float(self.expected_exit_price) if self.expected_exit_price is not None else None,
            "exit_metadata": self.exit_metadata,
        }


class StrategyRunner:
    @staticmethod
    def _is_invalid(val) -> bool:
        """Helper to check if a value is None, NaN or infinite."""
        if val is None:
            return True
        try:
            val_float = float(val)
            return math.isnan(val_float) or math.isinf(val_float)
        except (ValueError, TypeError):
            return True

    @classmethod
    def evaluate_rsi_strategy(cls, rsi_14: Decimal | float | None, has_open_position: bool) -> tuple[str, str]:
        """
        RSI (14) Strategy:
        - Buy: RSI < 30 (Oversold) - only if has_open_position is False
        - Sell: RSI > 70 (Overbought) - only if has_open_position is True
        """
        if cls._is_invalid(rsi_14):
            return "HOLD", "RSI_INSUFFICIENT_DATA"

        rsi = float(rsi_14)

        if rsi < 30:
            return ("BUY", "RSI_OVERSOLD") if not has_open_position else ("HOLD", "RSI_OVERSOLD_BUT_POSITION_OPEN")
        if rsi > 70:
            return ("SELL", "RSI_OVERBOUGHT") if has_open_position else ("HOLD", "RSI_OVERBOUGHT_BUT_NO_POSITION")

        return "HOLD", "RSI_NEUTRAL"

    @classmethod
    def evaluate_sma_cross_strategy(
        cls,
        sma_20: Decimal | float | None,
        sma_50: Decimal | float | None,
        prev_sma_20: Decimal | float | None,
        prev_sma_50: Decimal | float | None,
        has_open_position: bool,
    ) -> tuple[str, str]:
        """
        SMA Crossover (20/50) Strategy:
        - Buy (Golden Cross): current sma_20 > current sma_50 AND previous sma_20 <= previous sma_50
        - Sell (Death Cross): current sma_20 < current sma_50 AND previous sma_20 >= previous sma_50
        """
        if (
            cls._is_invalid(sma_20)
            or cls._is_invalid(sma_50)
            or cls._is_invalid(prev_sma_20)
            or cls._is_invalid(prev_sma_50)
        ):
            return "HOLD", "SMA_INSUFFICIENT_DATA"

        cur20 = float(sma_20)
        cur50 = float(sma_50)
        prev20 = float(prev_sma_20)
        prev50 = float(prev_sma_50)

        # Golden Cross
        if cur20 > cur50 and prev20 <= prev50:
            return (
                ("BUY", "SMA_GOLDEN_CROSS") if not has_open_position else ("HOLD", "SMA_GOLDEN_CROSS_BUT_POSITION_OPEN")
            )

        # Death Cross
        if cur20 < cur50 and prev20 >= prev50:
            return ("SELL", "SMA_DEATH_CROSS") if has_open_position else ("HOLD", "SMA_DEATH_CROSS_BUT_NO_POSITION")

        return "HOLD", "SMA_NO_CROSSOVER"

    @classmethod
    def evaluate_bb_strategy(
        cls,
        close: Decimal | float | None,
        bb_lower: Decimal | float | None,
        bb_upper: Decimal | float | None,
        has_open_position: bool,
    ) -> tuple[str, str]:
        """
        Bollinger Bands (20, 2) Strategy:
        - Buy: close <= bb_lower (Touch/Cross lower band) - only if has_open_position is False
        - Sell: close >= bb_upper (Touch/Cross upper band) - only if has_open_position is True
        """
        if cls._is_invalid(close) or cls._is_invalid(bb_lower) or cls._is_invalid(bb_upper):
            return "HOLD", "BB_INSUFFICIENT_DATA"

        c = float(close)
        lower = float(bb_lower)
        upper = float(bb_upper)

        if c <= lower:
            return ("BUY", "BB_LOWER_TOUCH") if not has_open_position else ("HOLD", "BB_LOWER_TOUCH_BUT_POSITION_OPEN")
        if c >= upper:
            return ("SELL", "BB_UPPER_TOUCH") if has_open_position else ("HOLD", "BB_UPPER_TOUCH_BUT_NO_POSITION")

        return "HOLD", "BB_NEUTRAL"

    @classmethod
    def evaluate_blended_strategies(
        cls,
        close: Decimal | float | None,
        rsi_14: Decimal | float | None,
        sma_20: Decimal | float | None,
        sma_50: Decimal | float | None,
        prev_sma_20: Decimal | float | None,
        prev_sma_50: Decimal | float | None,
        bb_lower: Decimal | float | None,
        bb_upper: Decimal | float | None,
        has_open_position: bool,
    ) -> dict:
        """
        Executes RSI, Bollinger, and SMA Cross strategies concurrently and returns their votes.
        """
        rsi_act, rsi_reason = cls.evaluate_rsi_strategy(rsi_14, has_open_position)
        bb_act, bb_reason = cls.evaluate_bb_strategy(close, bb_lower, bb_upper, has_open_position)
        sma_act, sma_reason = cls.evaluate_sma_cross_strategy(
            sma_20, sma_50, prev_sma_20, prev_sma_50, has_open_position
        )
        return {
            "rsi": {"action": rsi_act, "reason": rsi_reason},
            "bollinger": {"action": bb_act, "reason": bb_reason},
            "sma_cross": {"action": sma_act, "reason": sma_reason},
        }

    @classmethod
    def evaluate_all_strategies(
        cls,
        close: Decimal | float | None,
        rsi_14: Decimal | float | None,
        sma_20: Decimal | float | None,
        sma_50: Decimal | float | None,
        prev_sma_20: Decimal | float | None,
        prev_sma_50: Decimal | float | None,
        bb_lower: Decimal | float | None,
        bb_upper: Decimal | float | None,
        has_open_position: bool,
        strategy_name: StrategyType,
        macd_line: Decimal | float | None = None,
        macd_signal: Decimal | float | None = None,
        prev_macd_line: Decimal | float | None = None,
        prev_macd_signal: Decimal | float | None = None,
        regime_info: dict | None = None,
    ) -> tuple[str, str]:
        """
        Routes calculation to the selected strategy.
        """
        strategy = STRATEGY_REGISTRY.get(strategy_name)
        if not strategy:
            return "HOLD", "UNKNOWN_STRATEGY"

        context = {
            "close": close,
            "rsi_14": rsi_14,
            "sma_20": sma_20,
            "sma_50": sma_50,
            "prev_sma_20": prev_sma_20,
            "prev_sma_50": prev_sma_50,
            "bb_lower": bb_lower,
            "bb_upper": bb_upper,
            "macd_line": macd_line,
            "macd_signal": macd_signal,
            "prev_macd_line": prev_macd_line,
            "prev_macd_signal": prev_macd_signal,
            "regime_info": regime_info,
            "has_open_position": has_open_position,
        }
        return strategy.evaluate_sync(context)

    @classmethod
    def classify_trend(
        cls,
        *,
        close: Decimal | float | None,
        sma_20: Decimal | float | None,
        sma_50: Decimal | float | None,
    ) -> str:
        if cls._is_invalid(close) or cls._is_invalid(sma_20) or cls._is_invalid(sma_50):
            return "MISSING"

        close_value = float(close)
        sma_20_value = float(sma_20)
        sma_50_value = float(sma_50)

        if sma_20_value > sma_50_value and close_value >= sma_20_value:
            return "BULLISH"
        if sma_20_value < sma_50_value and close_value <= sma_20_value:
            return "BEARISH"
        return "NEUTRAL"

    @classmethod
    def evaluate_strategy_v2(
        cls,
        *,
        daily_close: Decimal | float | None,
        daily_sma_20: Decimal | float | None,
        daily_sma_50: Decimal | float | None,
        entry_close: Decimal | float | None,
        entry_rsi_14: Decimal | float | None,
        entry_sma_20: Decimal | float | None,
        entry_sma_50: Decimal | float | None,
        entry_macd_histogram: Decimal | float | None,
        entry_bb_middle: Decimal | float | None,
        entry_atr_14: Decimal | float | None,
        has_open_position: bool,
        execution_ready: bool = True,
        readiness_block_flags: list[str] | None = None,
    ) -> StrategyDecision:
        block_flags = list(readiness_block_flags or [])
        if not execution_ready and "EXECUTION_TIMEFRAME_STALE" not in block_flags:
            block_flags.append("EXECUTION_TIMEFRAME_STALE")

        if "TIMEFRAME_SOURCE_MISMATCH" in block_flags:
            return StrategyDecision(
                action="HOLD",
                reason_code="TIMEFRAME_SOURCE_MISMATCH",
                confidence=Decimal("0.9900"),
                trend_state="BLOCKED",
                entry_state="BLOCKED",
                execution_state="BLOCKED",
                buy_score=Decimal("0.0000"),
                sell_score=Decimal("0.0000"),
                component_scores={},
                readiness_block_flags=block_flags,
                stop_loss_price=None,
                take_profit_price=None,
                expected_exit_price=None,
                exit_metadata={"mode": "fail_closed", "reason": "timeframe_source_mismatch"},
            )

        if "ENTRY_TIMEFRAME_STALE" in block_flags or "ENTRY_TIMEFRAME_UNUSABLE" in block_flags:
            return StrategyDecision(
                action="HOLD",
                reason_code="ENTRY_TIMEFRAME_STALE"
                if "ENTRY_TIMEFRAME_STALE" in block_flags
                else "ENTRY_TIMEFRAME_UNUSABLE",
                confidence=Decimal("0.9800"),
                trend_state="BLOCKED",
                entry_state="BLOCKED",
                execution_state="READY" if execution_ready else "BLOCKED",
                buy_score=Decimal("0.0000"),
                sell_score=Decimal("0.0000"),
                component_scores={},
                readiness_block_flags=block_flags,
                stop_loss_price=None,
                take_profit_price=None,
                expected_exit_price=None,
                exit_metadata={"mode": "fail_closed", "reason": "entry_timeframe_not_usable"},
            )

        trend_state = cls.classify_trend(close=daily_close, sma_20=daily_sma_20, sma_50=daily_sma_50)
        if trend_state == "MISSING":
            if "DAILY_TREND_MISSING" not in block_flags:
                block_flags.append("DAILY_TREND_MISSING")
            return StrategyDecision(
                action="HOLD",
                reason_code="DAILY_TREND_MISSING",
                confidence=Decimal("0.9900"),
                trend_state=trend_state,
                entry_state="BLOCKED",
                execution_state="READY" if execution_ready else "BLOCKED",
                buy_score=Decimal("0.0000"),
                sell_score=Decimal("0.0000"),
                component_scores={},
                readiness_block_flags=block_flags,
                stop_loss_price=None,
                take_profit_price=None,
                expected_exit_price=None,
                exit_metadata={"mode": "fail_closed", "reason": "missing_daily_trend"},
            )

        buy_score = Decimal("0.0000")
        sell_score = Decimal("0.0000")
        component_scores: dict[str, float] = {}
        buy_components = 0
        sell_components = 0

        if not cls._is_invalid(entry_sma_20) and not cls._is_invalid(entry_sma_50):
            if float(entry_sma_20) > float(entry_sma_50):
                buy_score += Decimal("1.1000")
                buy_components += 1
                component_scores["hour_sma_trend_buy"] = 1.1
            elif float(entry_sma_20) < float(entry_sma_50):
                sell_score += Decimal("1.1000")
                sell_components += 1
                component_scores["hour_sma_trend_sell"] = 1.1

        if not cls._is_invalid(entry_macd_histogram):
            if float(entry_macd_histogram) > 0:
                buy_score += Decimal("0.9000")
                buy_components += 1
                component_scores["hour_macd_buy"] = 0.9
            elif float(entry_macd_histogram) < 0:
                sell_score += Decimal("0.9000")
                sell_components += 1
                component_scores["hour_macd_sell"] = 0.9

        if not cls._is_invalid(entry_rsi_14):
            rsi = float(entry_rsi_14)
            if 45.0 <= rsi <= 62.0:
                buy_score += Decimal("0.6000")
                buy_components += 1
                component_scores["hour_rsi_trend_buy"] = 0.6
            elif 38.0 <= rsi < 45.0:
                buy_score += Decimal("0.4000")
                buy_components += 1
                component_scores["hour_rsi_recovery_buy"] = 0.4
            elif rsi < 30.0:
                buy_score += Decimal("0.3000")
                buy_components += 1
                component_scores["hour_rsi_oversold_buy"] = 0.3
            elif rsi >= 68.0:
                sell_score += Decimal("0.7000")
                sell_components += 1
                component_scores["hour_rsi_exit_sell"] = 0.7

        if not cls._is_invalid(entry_close) and not cls._is_invalid(entry_bb_middle):
            if float(entry_close) >= float(entry_bb_middle):
                buy_score += Decimal("0.4000")
                buy_components += 1
                component_scores["hour_price_above_mid_buy"] = 0.4
            else:
                sell_score += Decimal("0.4000")
                sell_components += 1
                component_scores["hour_price_below_mid_sell"] = 0.4

        atr_value = None if cls._is_invalid(entry_atr_14) else Decimal(str(entry_atr_14))
        close_value = None if cls._is_invalid(entry_close) else Decimal(str(entry_close))
        stop_loss_price = None
        take_profit_price = None
        expected_exit_price = None
        if atr_value is not None and close_value is not None:
            risk_unit = max(atr_value * Decimal("1.5"), close_value * Decimal("0.01"))
            reward_unit = max(atr_value * Decimal("2.5"), close_value * Decimal("0.015"))
            stop_loss_price = close_value - risk_unit
            take_profit_price = close_value + reward_unit
            expected_exit_price = take_profit_price

        if not execution_ready:
            return StrategyDecision(
                action="HOLD",
                reason_code="EXECUTION_TIMEFRAME_STALE",
                confidence=Decimal("0.9700"),
                trend_state=trend_state,
                entry_state="READY",
                execution_state="BLOCKED",
                buy_score=buy_score.quantize(CONFIDENCE_QUANT),
                sell_score=sell_score.quantize(CONFIDENCE_QUANT),
                component_scores=component_scores,
                readiness_block_flags=block_flags,
                stop_loss_price=stop_loss_price,
                take_profit_price=take_profit_price,
                expected_exit_price=expected_exit_price,
                exit_metadata={"mode": "fail_closed", "reason": "stale_execution_timeframe"},
            )

        if trend_state == "BEARISH" and not has_open_position and buy_score >= Decimal("2.0000"):
            if "DAILY_TREND_DOWN_BUY_BLOCK" not in block_flags:
                block_flags.append("DAILY_TREND_DOWN_BUY_BLOCK")
            return StrategyDecision(
                action="HOLD",
                reason_code="DAILY_TREND_DOWN_BUY_BLOCK",
                confidence=Decimal("0.9300"),
                trend_state=trend_state,
                entry_state="BLOCKED",
                execution_state="READY",
                buy_score=buy_score.quantize(CONFIDENCE_QUANT),
                sell_score=sell_score.quantize(CONFIDENCE_QUANT),
                component_scores=component_scores,
                readiness_block_flags=block_flags,
                stop_loss_price=stop_loss_price,
                take_profit_price=take_profit_price,
                expected_exit_price=expected_exit_price,
                exit_metadata={"mode": "trend_filter", "reason": "daily_downtrend_blocks_buy"},
            )

        buy_ready = buy_score >= Decimal("2.0000") and buy_components >= 2
        sell_ready = sell_score >= Decimal("2.0000") and sell_components >= 2

        if not has_open_position and buy_ready:
            confidence = min(Decimal("0.9900"), Decimal("0.5500") + (buy_score / Decimal("4.0")))
            return StrategyDecision(
                action="BUY",
                reason_code="STRATEGY_V2_BUY_CONFIRMED",
                confidence=confidence.quantize(CONFIDENCE_QUANT),
                trend_state=trend_state,
                entry_state="BUY_READY",
                execution_state="READY",
                buy_score=buy_score.quantize(CONFIDENCE_QUANT),
                sell_score=sell_score.quantize(CONFIDENCE_QUANT),
                component_scores=component_scores,
                readiness_block_flags=block_flags,
                stop_loss_price=stop_loss_price,
                take_profit_price=take_profit_price,
                expected_exit_price=expected_exit_price,
                exit_metadata={"mode": "atr_targets", "reason": "hourly_score_confirmed"},
            )

        if has_open_position and sell_ready:
            confidence = min(Decimal("0.9900"), Decimal("0.5500") + (sell_score / Decimal("4.0")))
            return StrategyDecision(
                action="SELL",
                reason_code="STRATEGY_V2_SELL_CONFIRMED",
                confidence=confidence.quantize(CONFIDENCE_QUANT),
                trend_state=trend_state,
                entry_state="SELL_READY",
                execution_state="READY",
                buy_score=buy_score.quantize(CONFIDENCE_QUANT),
                sell_score=sell_score.quantize(CONFIDENCE_QUANT),
                component_scores=component_scores,
                readiness_block_flags=block_flags,
                stop_loss_price=None,
                take_profit_price=None,
                expected_exit_price=None,
                exit_metadata={"mode": "position_exit", "reason": "hourly_score_exit"},
            )

        hold_reason = "STRATEGY_V2_NO_EDGE"
        if not has_open_position and not buy_ready and buy_components == 1:
            hold_reason = "STRATEGY_V2_INSUFFICIENT_CONFIRMATION"
        elif has_open_position and not sell_ready:
            hold_reason = "STRATEGY_V2_HOLD_POSITION"

        confidence = min(Decimal("0.9500"), Decimal("0.5000") + (max(buy_score, sell_score) / Decimal("5.0")))
        return StrategyDecision(
            action="HOLD",
            reason_code=hold_reason,
            confidence=confidence.quantize(CONFIDENCE_QUANT),
            trend_state=trend_state,
            entry_state="NO_EDGE",
            execution_state="READY",
            buy_score=buy_score.quantize(CONFIDENCE_QUANT),
            sell_score=sell_score.quantize(CONFIDENCE_QUANT),
            component_scores=component_scores,
            readiness_block_flags=block_flags,
            stop_loss_price=stop_loss_price,
            take_profit_price=take_profit_price,
            expected_exit_price=expected_exit_price,
            exit_metadata={"mode": "stand_aside", "reason": "score_below_threshold"},
        )

    @classmethod
    def evaluate_macd_strategy(
        cls,
        macd_line: Decimal | float | None,
        macd_signal: Decimal | float | None,
        prev_macd_line: Decimal | float | None,
        prev_macd_signal: Decimal | float | None,
        has_open_position: bool,
    ) -> tuple[str, str]:
        """
        MACD Crossover Strategy:
        - Buy (Golden Cross): current macd_line > current macd_signal AND previous macd_line <= previous macd_signal
        - Sell (Death Cross): current macd_line < current macd_signal AND previous macd_line >= previous macd_signal
        """
        if (
            cls._is_invalid(macd_line)
            or cls._is_invalid(macd_signal)
            or cls._is_invalid(prev_macd_line)
            or cls._is_invalid(prev_macd_signal)
        ):
            return "HOLD", "MACD_INSUFFICIENT_DATA"

        cur_line = float(macd_line)
        cur_signal = float(macd_signal)
        prev_line = float(prev_macd_line)
        prev_signal = float(prev_macd_signal)

        # Golden Cross
        if cur_line > cur_signal and prev_line <= prev_signal:
            return (
                ("BUY", "MACD_GOLDEN_CROSS")
                if not has_open_position
                else ("HOLD", "MACD_GOLDEN_CROSS_BUT_POSITION_OPEN")
            )

        # Death Cross
        if cur_line < cur_signal and prev_line >= prev_signal:
            return ("SELL", "MACD_DEATH_CROSS") if has_open_position else ("HOLD", "MACD_DEATH_CROSS_BUT_NO_POSITION")

        return "HOLD", "MACD_NO_CROSSOVER"

    @classmethod
    def apply_agent_filters(
        cls,
        action: str,
        news_sentiment: str | None,
        risk_decision: str | None,
        db: Session | None = None,
    ) -> tuple[str, str]:
        """
        Applies agent vetoes to the strategy action.
        BUY can be downgraded to HOLD, but HOLD is never upgraded to BUY.
        """
        if db is not None:
            from app.models.entities import AgentMemoryEvent
            from app.core.config import get_settings
            from sqlalchemy import desc

            settings = get_settings()

            stmt = (
                db.query(AgentMemoryEvent)
                .filter(
                    AgentMemoryEvent.agent_name == settings.auto_trading_sentiment_agent_name,
                    AgentMemoryEvent.event_type == "hermes_sentiment",
                    AgentMemoryEvent.key == "latest_analysis",
                )
                .order_by(desc(AgentMemoryEvent.id))
                .first()
            )
            if stmt is not None:
                val = stmt.value_json or {}
                score_val = val.get("score")
                if score_val is not None:
                    score_dec = Decimal(str(score_val))
                    if action == "BUY" and score_dec < settings.hermes_veto_threshold:
                        return "HOLD", "AGENT_VETO_HERMES_BEARISH_NEWS"
        if action == "BUY":
            if news_sentiment == "BEARISH":
                return "HOLD", "AGENT_VETO_BEARISH_NEWS"
            if risk_decision == "REJECTED":
                return "HOLD", "AGENT_VETO_RISK_REJECTED"
        return action, ""


async def trigger_risk_critique_hook(db: Session, signal_id: int) -> "AgentMemoryEvent":
    """
    Integration hook/helper that triggers the Risk Agent's signal critique.
    Imports run_signal_critique locally to prevent circular dependencies.
    """
    from app.agents.risk import run_signal_critique

    return await run_signal_critique(db, signal_id=signal_id)


class RsiStrategy(BaseStrategy):
    def evaluate_sync(self, context: dict) -> tuple[str, str]:
        return StrategyRunner.evaluate_rsi_strategy(context.get("rsi_14"), context.get("has_open_position", False))

    async def evaluate(self, db: Session, context: dict) -> StrategyDecision:
        action, reason = self.evaluate_sync(context)

        atr_value = context.get("atr_value")
        close_value = context.get("close_value")
        stop_loss_price = None
        take_profit_price = None
        expected_exit_price = None
        if atr_value is not None and close_value is not None:
            risk_unit = max(atr_value * Decimal("1.5"), close_value * Decimal("0.01"))
            reward_unit = max(atr_value * Decimal("2.5"), close_value * Decimal("0.015"))
            stop_loss_price = close_value - risk_unit
            take_profit_price = close_value + reward_unit
            expected_exit_price = take_profit_price

        return StrategyDecision(
            action=action,
            reason_code=reason,
            confidence=Decimal("0.9000"),
            trend_state="NEUTRAL",
            entry_state="READY",
            execution_state="READY",
            buy_score=Decimal("0.0000"),
            sell_score=Decimal("0.0000"),
            component_scores={},
            readiness_block_flags=context.get("readiness_block_flags", []),
            stop_loss_price=stop_loss_price,
            take_profit_price=take_profit_price,
            expected_exit_price=expected_exit_price,
            exit_metadata={},
        )


class SmaCrossStrategy(BaseStrategy):
    def evaluate_sync(self, context: dict) -> tuple[str, str]:
        return StrategyRunner.evaluate_sma_cross_strategy(
            context.get("sma_20"),
            context.get("sma_50"),
            context.get("prev_sma_20"),
            context.get("prev_sma_50"),
            context.get("has_open_position", False),
        )

    async def evaluate(self, db: Session, context: dict) -> StrategyDecision:
        action, reason = self.evaluate_sync(context)

        atr_value = context.get("atr_value")
        close_value = context.get("close_value")
        stop_loss_price = None
        take_profit_price = None
        expected_exit_price = None
        if atr_value is not None and close_value is not None:
            risk_unit = max(atr_value * Decimal("1.5"), close_value * Decimal("0.01"))
            reward_unit = max(atr_value * Decimal("2.5"), close_value * Decimal("0.015"))
            stop_loss_price = close_value - risk_unit
            take_profit_price = close_value + reward_unit
            expected_exit_price = take_profit_price

        return StrategyDecision(
            action=action,
            reason_code=reason,
            confidence=Decimal("0.9000"),
            trend_state="NEUTRAL",
            entry_state="READY",
            execution_state="READY",
            buy_score=Decimal("0.0000"),
            sell_score=Decimal("0.0000"),
            component_scores={},
            readiness_block_flags=context.get("readiness_block_flags", []),
            stop_loss_price=stop_loss_price,
            take_profit_price=take_profit_price,
            expected_exit_price=expected_exit_price,
            exit_metadata={},
        )


class BollingerStrategy(BaseStrategy):
    def evaluate_sync(self, context: dict) -> tuple[str, str]:
        return StrategyRunner.evaluate_bb_strategy(
            context.get("close"),
            context.get("bb_lower"),
            context.get("bb_upper"),
            context.get("has_open_position", False),
        )

    async def evaluate(self, db: Session, context: dict) -> StrategyDecision:
        action, reason = self.evaluate_sync(context)

        atr_value = context.get("atr_value")
        close_value = context.get("close_value")
        stop_loss_price = None
        take_profit_price = None
        expected_exit_price = None
        if atr_value is not None and close_value is not None:
            risk_unit = max(atr_value * Decimal("1.5"), close_value * Decimal("0.01"))
            reward_unit = max(atr_value * Decimal("2.5"), close_value * Decimal("0.015"))
            stop_loss_price = close_value - risk_unit
            take_profit_price = close_value + reward_unit
            expected_exit_price = take_profit_price

        return StrategyDecision(
            action=action,
            reason_code=reason,
            confidence=Decimal("0.9000"),
            trend_state="NEUTRAL",
            entry_state="READY",
            execution_state="READY",
            buy_score=Decimal("0.0000"),
            sell_score=Decimal("0.0000"),
            component_scores={},
            readiness_block_flags=context.get("readiness_block_flags", []),
            stop_loss_price=stop_loss_price,
            take_profit_price=take_profit_price,
            expected_exit_price=expected_exit_price,
            exit_metadata={},
        )


class BlendedStrategy(BaseStrategy):
    def evaluate_sync(self, context: dict) -> tuple[str, str]:
        votes = StrategyRunner.evaluate_blended_strategies(
            context.get("close"),
            context.get("rsi_14"),
            context.get("sma_20"),
            context.get("sma_50"),
            context.get("prev_sma_20"),
            context.get("prev_sma_50"),
            context.get("bb_lower"),
            context.get("bb_upper"),
            context.get("has_open_position", False),
        )
        actions = [votes["rsi"]["action"], votes["bollinger"]["action"], votes["sma_cross"]["action"]]
        buy_count = actions.count("BUY")
        sell_count = actions.count("SELL")
        if buy_count > sell_count and buy_count >= 1:
            return "BUY", "BLENDED_MAJORITY"
        elif sell_count > buy_count and sell_count >= 1:
            return "SELL", "BLENDED_MAJORITY"
        return "HOLD", "BLENDED_NEUTRAL"

    async def evaluate(self, db: Session, context: dict) -> StrategyDecision:
        from app.services.regime import get_market_regime
        from app.agents.orchestrator import run_blended_consensus_resolution

        asset = context["asset"]
        hourly_context = context["hourly_context"]
        latest_indicator = context.get("latest_indicator")
        has_open_position = context.get("has_open_position", False)
        latest_snapshot = context.get("latest_snapshot")
        latest_event = context.get("latest_event")

        regime_info = get_market_regime(db, asset_symbol=asset.symbol, timeframe=hourly_context.readiness.timeframe)
        if regime_info.get("status") == "degraded":
            return StrategyDecision(
                action="HOLD",
                reason_code="REGIME_DEGRADED",
                confidence=Decimal("0.0000"),
                trend_state="REGIME_DEGRADED",
                entry_state="READY",
                execution_state="READY",
                buy_score=Decimal("0.0000"),
                sell_score=Decimal("0.0000"),
                component_scores={},
                readiness_block_flags=context.get("readiness_block_flags", []),
                stop_loss_price=None,
                take_profit_price=None,
                expected_exit_price=None,
                exit_metadata={"regime_info": regime_info},
            )

        close = latest_indicator.close_usd_oz if latest_indicator else None
        rsi_14 = latest_indicator.rsi_14 if latest_indicator else None
        sma_20 = latest_indicator.sma_20 if latest_indicator else None
        sma_50 = latest_indicator.sma_50 if latest_indicator else None
        prev_sma_20 = (
            hourly_context.previous_indicator.sma_20
            if (hourly_context.previous_indicator and latest_indicator)
            else None
        )
        prev_sma_50 = (
            hourly_context.previous_indicator.sma_50
            if (hourly_context.previous_indicator and latest_indicator)
            else None
        )
        bb_lower = latest_indicator.bb_lower_20_2 if latest_indicator else None
        bb_upper = latest_indicator.bb_upper_20_2 if latest_indicator else None

        strategy_votes = StrategyRunner.evaluate_blended_strategies(
            close=close,
            rsi_14=rsi_14,
            sma_20=sma_20,
            sma_50=sma_50,
            prev_sma_20=prev_sma_20,
            prev_sma_50=prev_sma_50,
            bb_lower=bb_lower,
            bb_upper=bb_upper,
            has_open_position=has_open_position,
        )

        consensus_event = await run_blended_consensus_resolution(
            db=db,
            regime_info=regime_info,
            strategy_votes=strategy_votes,
            latest_snapshot=latest_snapshot,
            hermes_sentiment=latest_event.value_json if latest_event else None,
        )

        resolved_stance = consensus_event.value_json.get("resolved_stance", "NEUTRAL")
        confidence = Decimal(str(consensus_event.value_json.get("confidence", "0.5")))
        resolution_markdown = consensus_event.value_json.get("resolution_markdown", "")

        if resolved_stance == "BULLISH":
            if not has_open_position:
                action = "BUY"
                reason_code = "BLENDED_BULLISH"
            else:
                action = "HOLD"
                reason_code = "BLENDED_BULLISH_BUT_POSITION_OPEN"
        elif resolved_stance == "BEARISH":
            if has_open_position:
                action = "SELL"
                reason_code = "BLENDED_BEARISH"
            else:
                action = "HOLD"
                reason_code = "BLENDED_BEARISH_BUT_NO_POSITION"
        else:
            action = "HOLD"
            reason_code = "BLENDED_NEUTRAL"

        atr_value = context.get("atr_value")
        close_value = context.get("close_value")
        stop_loss_price = None
        take_profit_price = None
        expected_exit_price = None
        if atr_value is not None and close_value is not None:
            risk_unit = max(atr_value * Decimal("1.5"), close_value * Decimal("0.01"))
            reward_unit = max(atr_value * Decimal("2.5"), close_value * Decimal("0.015"))
            stop_loss_price = close_value - risk_unit
            take_profit_price = close_value + reward_unit
            expected_exit_price = take_profit_price

        exit_metadata = {
            "mode": "blended_consensus",
            "reason": resolution_markdown,
            "resolved_stance": resolved_stance,
            "consensus_event_id": consensus_event.id,
            "regime_info": regime_info,
            "strategy_votes": strategy_votes,
            "arbiter_decision": resolved_stance,
            "arbiter_reason": resolution_markdown,
        }

        return StrategyDecision(
            action=action,
            reason_code=reason_code,
            confidence=confidence,
            trend_state="NEUTRAL",
            entry_state="READY",
            execution_state="READY",
            buy_score=Decimal("0.0000"),
            sell_score=Decimal("0.0000"),
            component_scores={},
            readiness_block_flags=context.get("readiness_block_flags", []),
            stop_loss_price=stop_loss_price,
            take_profit_price=take_profit_price,
            expected_exit_price=expected_exit_price,
            exit_metadata=exit_metadata,
        )


class StrategyV2(BaseStrategy):
    def evaluate_sync(self, context: dict) -> tuple[str, str]:
        daily_context = context.get("daily_context")
        latest_indicator = context.get("latest_indicator")
        has_open_position = context.get("has_open_position", False)
        strategy_readiness_flags = context.get("readiness_block_flags", [])

        if latest_indicator is None or daily_context is None or daily_context.readiness.indicator is None:
            execution_ready = "EXECUTION_TIMEFRAME_STALE" not in strategy_readiness_flags
            dec = StrategyRunner.evaluate_strategy_v2(
                daily_close=None,
                daily_sma_20=None,
                daily_sma_50=None,
                entry_close=None,
                entry_rsi_14=None,
                entry_sma_20=None,
                entry_sma_50=None,
                entry_macd_histogram=None,
                entry_bb_middle=None,
                entry_atr_14=None,
                has_open_position=has_open_position,
                execution_ready=execution_ready,
                readiness_block_flags=strategy_readiness_flags,
            )
        else:
            execution_ready = "EXECUTION_TIMEFRAME_STALE" not in strategy_readiness_flags
            dec = StrategyRunner.evaluate_strategy_v2(
                daily_close=daily_context.readiness.indicator.close_usd_oz,
                daily_sma_20=daily_context.readiness.indicator.sma_20,
                daily_sma_50=daily_context.readiness.indicator.sma_50,
                entry_close=latest_indicator.close_usd_oz,
                entry_rsi_14=latest_indicator.rsi_14,
                entry_sma_20=latest_indicator.sma_20,
                entry_sma_50=latest_indicator.sma_50,
                entry_macd_histogram=latest_indicator.macd_histogram,
                entry_bb_middle=latest_indicator.bb_middle_20_2,
                entry_atr_14=latest_indicator.atr_14,
                has_open_position=has_open_position,
                execution_ready=execution_ready,
                readiness_block_flags=strategy_readiness_flags,
            )
        return dec.action, dec.reason_code

    async def evaluate(self, db: Session, context: dict) -> StrategyDecision:
        daily_context = context["daily_context"]
        latest_indicator = context.get("latest_indicator")
        has_open_position = context.get("has_open_position", False)
        strategy_readiness_flags = context.get("readiness_block_flags", [])

        if latest_indicator is None or daily_context.readiness.indicator is None:
            execution_ready = "EXECUTION_TIMEFRAME_STALE" not in strategy_readiness_flags
            return StrategyRunner.evaluate_strategy_v2(
                daily_close=None,
                daily_sma_20=None,
                daily_sma_50=None,
                entry_close=None,
                entry_rsi_14=None,
                entry_sma_20=None,
                entry_sma_50=None,
                entry_macd_histogram=None,
                entry_bb_middle=None,
                entry_atr_14=None,
                has_open_position=has_open_position,
                execution_ready=execution_ready,
                readiness_block_flags=strategy_readiness_flags,
            )
        else:
            execution_ready = "EXECUTION_TIMEFRAME_STALE" not in strategy_readiness_flags
            return StrategyRunner.evaluate_strategy_v2(
                daily_close=daily_context.readiness.indicator.close_usd_oz,
                daily_sma_20=daily_context.readiness.indicator.sma_20,
                daily_sma_50=daily_context.readiness.indicator.sma_50,
                entry_close=latest_indicator.close_usd_oz,
                entry_rsi_14=latest_indicator.rsi_14,
                entry_sma_20=latest_indicator.sma_20,
                entry_sma_50=latest_indicator.sma_50,
                entry_macd_histogram=latest_indicator.macd_histogram,
                entry_bb_middle=latest_indicator.bb_middle_20_2,
                entry_atr_14=latest_indicator.atr_14,
                has_open_position=has_open_position,
                execution_ready=execution_ready,
                readiness_block_flags=strategy_readiness_flags,
            )


class MacdStrategy(BaseStrategy):
    def evaluate_sync(self, context: dict) -> tuple[str, str]:
        return StrategyRunner.evaluate_macd_strategy(
            context.get("macd_line"),
            context.get("macd_signal"),
            context.get("prev_macd_line"),
            context.get("prev_macd_signal"),
            context.get("has_open_position", False),
        )

    async def evaluate(self, db: Session, context: dict) -> StrategyDecision:
        action, reason = self.evaluate_sync(context)

        atr_value = context.get("atr_value")
        close_value = context.get("close_value")
        stop_loss_price = None
        take_profit_price = None
        expected_exit_price = None
        if atr_value is not None and close_value is not None:
            risk_unit = max(atr_value * Decimal("1.5"), close_value * Decimal("0.01"))
            reward_unit = max(atr_value * Decimal("2.5"), close_value * Decimal("0.015"))
            stop_loss_price = close_value - risk_unit
            take_profit_price = close_value + reward_unit
            expected_exit_price = take_profit_price

        return StrategyDecision(
            action=action,
            reason_code=reason,
            confidence=Decimal("0.9000"),
            trend_state="NEUTRAL",
            entry_state="READY",
            execution_state="READY",
            buy_score=Decimal("0.0000"),
            sell_score=Decimal("0.0000"),
            component_scores={},
            readiness_block_flags=context.get("readiness_block_flags", []),
            stop_loss_price=stop_loss_price,
            take_profit_price=take_profit_price,
            expected_exit_price=expected_exit_price,
            exit_metadata={},
        )


class AutoRegimeStrategy(BaseStrategy):
    @staticmethod
    def _normalize_regime_info(regime_info: dict | None) -> dict:
        if not regime_info:
            return {
                "regime": "SIDEWAYS",
                "adx": 0.0,
                "bb_bandwidth": 0.0,
            }
        return regime_info

    def evaluate_sync(self, context: dict) -> tuple[str, str]:
        regime_info = self._normalize_regime_info(context.get("regime_info"))

        regime_info.get("regime", "SIDEWAYS")
        adx_val = regime_info.get("adx")
        adx = float(adx_val) if adx_val is not None else 0.0
        bb_val = regime_info.get("bb_bandwidth")
        bb_bandwidth = float(bb_val) if bb_val is not None else 0.0
        has_open_position = context.get("has_open_position", False)

        # Sideways/Mean-reversion
        is_sideways = adx < 25.0 or bb_bandwidth < 0.015
        if is_sideways:
            rsi_action, rsi_reason = StrategyRunner.evaluate_rsi_strategy(context.get("rsi_14"), has_open_position)
            bb_action, bb_reason = StrategyRunner.evaluate_bb_strategy(
                context.get("close"),
                context.get("bb_lower"),
                context.get("bb_upper"),
                has_open_position,
            )
            buy_score = 0.6 * (rsi_action == "BUY") + 0.4 * (bb_action == "BUY")
            sell_score = 0.6 * (rsi_action == "SELL") + 0.4 * (bb_action == "SELL")

            if buy_score > 0.5 and buy_score > sell_score:
                return "BUY", "AUTO_REGIME_SIDEWAYS_BUY"
            if sell_score > 0.5 and sell_score > buy_score:
                return "SELL", "AUTO_REGIME_SIDEWAYS_SELL"
            return "HOLD", "AUTO_REGIME_SIDEWAYS_HOLD"

        else:  # Trending
            sma_action, sma_reason = StrategyRunner.evaluate_sma_cross_strategy(
                context.get("sma_20"),
                context.get("sma_50"),
                context.get("prev_sma_20"),
                context.get("prev_sma_50"),
                has_open_position,
            )
            macd_action, macd_reason = StrategyRunner.evaluate_macd_strategy(
                context.get("macd_line"),
                context.get("macd_signal"),
                context.get("prev_macd_line"),
                context.get("prev_macd_signal"),
                has_open_position,
            )
            buy_score = 0.6 * (sma_action == "BUY") + 0.4 * (macd_action == "BUY")
            sell_score = 0.6 * (sma_action == "SELL") + 0.4 * (macd_action == "SELL")

            if buy_score > 0.5 and buy_score > sell_score:
                return "BUY", "AUTO_REGIME_TRENDING_BUY"
            if sell_score > 0.5 and sell_score > buy_score:
                return "SELL", "AUTO_REGIME_TRENDING_SELL"
            return "HOLD", "AUTO_REGIME_TRENDING_HOLD"

    async def evaluate(self, db: Session, context: dict) -> StrategyDecision:
        from app.services.regime import get_market_regime

        asset = context.get("asset")
        asset_symbol = asset.symbol if asset else "XAG_GRAM"

        hourly_context = context.get("hourly_context")
        timeframe = hourly_context.readiness.timeframe if hourly_context else "1h"

        regime_info = self._normalize_regime_info(get_market_regime(db, asset_symbol=asset_symbol, timeframe=timeframe))
        if regime_info.get("status") == "degraded":
            return StrategyDecision(
                action="HOLD",
                reason_code="REGIME_DEGRADED",
                confidence=Decimal("0.0000"),
                trend_state="REGIME_DEGRADED",
                entry_state="READY",
                execution_state="READY",
                buy_score=Decimal("0.0000"),
                sell_score=Decimal("0.0000"),
                component_scores={},
                readiness_block_flags=context.get("readiness_block_flags", []),
                stop_loss_price=None,
                take_profit_price=None,
                expected_exit_price=None,
                exit_metadata={"mode": "auto_regime", "regime_info": regime_info},
            )

        # Make a copy of context to prevent modifying caller's context dict
        local_context = dict(context)
        local_context["regime_info"] = regime_info

        action, reason = self.evaluate_sync(local_context)

        has_open_position = local_context.get("has_open_position", False)
        adx_val = regime_info.get("adx")
        adx = float(adx_val) if adx_val is not None else 0.0
        bb_val = regime_info.get("bb_bandwidth")
        bb_bandwidth = float(bb_val) if bb_val is not None else 0.0

        buy_score = Decimal("0.0000")
        sell_score = Decimal("0.0000")
        component_scores = {}

        is_sideways = adx < 25.0 or bb_bandwidth < 0.015
        if is_sideways:
            rsi_action, rsi_reason = StrategyRunner.evaluate_rsi_strategy(
                local_context.get("rsi_14"), has_open_position
            )
            bb_action, bb_reason = StrategyRunner.evaluate_bb_strategy(
                local_context.get("close"),
                local_context.get("bb_lower"),
                local_context.get("bb_upper"),
                has_open_position,
            )

            component_scores["rsi"] = {"action": rsi_action, "reason": rsi_reason}
            component_scores["bollinger"] = {"action": bb_action, "reason": bb_reason}

            buy_score = Decimal("0.6") * (rsi_action == "BUY") + Decimal("0.4") * (bb_action == "BUY")
            sell_score = Decimal("0.6") * (rsi_action == "SELL") + Decimal("0.4") * (bb_action == "SELL")
        else:
            sma_action, sma_reason = StrategyRunner.evaluate_sma_cross_strategy(
                local_context.get("sma_20"),
                local_context.get("sma_50"),
                local_context.get("prev_sma_20"),
                local_context.get("prev_sma_50"),
                has_open_position,
            )
            macd_action, macd_reason = StrategyRunner.evaluate_macd_strategy(
                local_context.get("macd_line"),
                local_context.get("macd_signal"),
                local_context.get("prev_macd_line"),
                local_context.get("prev_macd_signal"),
                has_open_position,
            )

            component_scores["sma_cross"] = {"action": sma_action, "reason": sma_reason}
            component_scores["macd"] = {"action": macd_action, "reason": macd_reason}

            buy_score = Decimal("0.6") * (sma_action == "BUY") + Decimal("0.4") * (macd_action == "BUY")
            sell_score = Decimal("0.6") * (sma_action == "SELL") + Decimal("0.4") * (macd_action == "SELL")

        atr_value = local_context.get("atr_value")
        close_value = local_context.get("close_value")
        stop_loss_price = None
        take_profit_price = None
        expected_exit_price = None
        if atr_value is not None and close_value is not None:
            risk_unit = max(atr_value * Decimal("1.5"), close_value * Decimal("0.01"))
            reward_unit = max(atr_value * Decimal("2.5"), close_value * Decimal("0.015"))
            stop_loss_price = close_value - risk_unit
            take_profit_price = close_value + reward_unit
            expected_exit_price = take_profit_price

        exit_metadata = {
            "mode": "auto_regime",
            "regime": regime_info.get("regime", "SIDEWAYS"),
            "adx": adx,
            "bb_bandwidth": bb_bandwidth,
        }

        return StrategyDecision(
            action=action,
            reason_code=reason,
            confidence=Decimal("0.9000"),
            trend_state=regime_info.get("regime", "SIDEWAYS"),
            entry_state="READY",
            execution_state="READY",
            buy_score=buy_score,
            sell_score=sell_score,
            component_scores=component_scores,
            readiness_block_flags=local_context.get("readiness_block_flags", []),
            stop_loss_price=stop_loss_price,
            take_profit_price=take_profit_price,
            expected_exit_price=expected_exit_price,
            exit_metadata=exit_metadata,
        )


STRATEGY_REGISTRY: dict[str, BaseStrategy] = {
    "rsi": RsiStrategy(),
    "sma_cross": SmaCrossStrategy(),
    "bollinger": BollingerStrategy(),
    "blended": BlendedStrategy(),
    "strategy_v2": StrategyV2(),
    "macd": MacdStrategy(),
    "auto": AutoRegimeStrategy(),
}
