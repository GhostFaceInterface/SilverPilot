import math
from decimal import Decimal
from typing import Literal, TYPE_CHECKING
from sqlalchemy.orm import Session

if TYPE_CHECKING:
    from app.models.entities import AgentMemoryEvent


StrategyType = Literal["rsi", "sma_cross", "bollinger", "rsi_with_agents", "sma_cross_with_agents", "bollinger_with_agents", "blended"]


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
    def evaluate_rsi_strategy(
        cls, rsi_14: Decimal | float | None, has_open_position: bool
    ) -> tuple[str, str]:
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
        if (
            cls._is_invalid(close)
            or cls._is_invalid(bb_lower)
            or cls._is_invalid(bb_upper)
        ):
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
            return cls.evaluate_sma_cross_strategy(
                sma_20, sma_50, prev_sma_20, prev_sma_50, has_open_position
            )
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
    def apply_agent_filters(
        cls, action: str, news_sentiment: str | None, risk_decision: str | None
    ) -> tuple[str, str]:
        """
        Applies agent filters (news sentiment and risk decision) to the strategy action.
        Vetoes BUY action to HOLD if news_sentiment is BEARISH or risk_decision is REJECTED.
        """
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
