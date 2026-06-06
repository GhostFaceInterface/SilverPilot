import math
from dataclasses import dataclass
from decimal import Decimal
from typing import Literal, TYPE_CHECKING
from sqlalchemy.orm import Session

if TYPE_CHECKING:
    from app.models.entities import AgentMemoryEvent


StrategyType = Literal[
    "rsi", "sma_cross", "bollinger", "rsi_with_agents", "sma_cross_with_agents", "bollinger_with_agents", "blended"
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
            if not has_open_position:
                return "BUY", "RSI_OVERSOLD"
            else:
                return "HOLD", "RSI_OVERSOLD_BUT_POSITION_OPEN"
        elif rsi > 70:
            if has_open_position:
                return "SELL", "RSI_OVERBOUGHT"
            else:
                return "HOLD", "RSI_OVERBOUGHT_BUT_NO_POSITION"

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
            if not has_open_position:
                return "BUY", "SMA_GOLDEN_CROSS"
            else:
                return "HOLD", "SMA_GOLDEN_CROSS_BUT_POSITION_OPEN"

        # Death Cross
        if cur20 < cur50 and prev20 >= prev50:
            if has_open_position:
                return "SELL", "SMA_DEATH_CROSS"
            else:
                return "HOLD", "SMA_DEATH_CROSS_BUT_NO_POSITION"

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
            if not has_open_position:
                return "BUY", "BB_LOWER_TOUCH"
            else:
                return "HOLD", "BB_LOWER_TOUCH_BUT_POSITION_OPEN"
        elif c >= upper:
            if has_open_position:
                return "SELL", "BB_UPPER_TOUCH"
            else:
                return "HOLD", "BB_UPPER_TOUCH_BUT_NO_POSITION"

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
    ) -> tuple[str, str]:
        """
        Routes calculation to the selected strategy.
        """
        if strategy_name == "rsi":
            return cls.evaluate_rsi_strategy(rsi_14, has_open_position)
        elif strategy_name == "sma_cross":
            return cls.evaluate_sma_cross_strategy(sma_20, sma_50, prev_sma_20, prev_sma_50, has_open_position)
        elif strategy_name == "bollinger":
            return cls.evaluate_bb_strategy(close, bb_lower, bb_upper, has_open_position)
        elif strategy_name == "blended":
            # For back-compatibility or simple non-agentic evaluation, return the majority action
            votes = cls.evaluate_blended_strategies(
                close, rsi_14, sma_20, sma_50, prev_sma_20, prev_sma_50, bb_lower, bb_upper, has_open_position
            )
            actions = [votes["rsi"]["action"], votes["bollinger"]["action"], votes["sma_cross"]["action"]]
            buy_count = actions.count("BUY")
            sell_count = actions.count("SELL")
            if buy_count > sell_count and buy_count >= 1:
                return "BUY", "BLENDED_MAJORITY"
            elif sell_count > buy_count and sell_count >= 1:
                return "SELL", "BLENDED_MAJORITY"
            return "HOLD", "BLENDED_NEUTRAL"
        else:
            return "HOLD", "UNKNOWN_STRATEGY"

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
                    AgentMemoryEvent.agent_name == "hermes-agent",
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
