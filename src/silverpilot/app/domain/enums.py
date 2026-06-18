from enum import StrEnum


class AccountStatus(StrEnum):
    ACTIVE = "active"
    DISABLED = "disabled"


class BankStatus(StrEnum):
    ACTIVE = "active"
    DISABLED = "disabled"


class InstrumentType(StrEnum):
    REFERENCE = "reference"
    EXECUTION = "execution"


class MarketRegime(StrEnum):
    TREND_UP = "trend_up"
    TREND_DOWN = "trend_down"
    RANGE = "range"
    HIGH_VOLATILITY = "high_volatility"
    LOW_VOLATILITY = "low_volatility"
    NO_TRADE = "no_trade"


class StrategyRunStatus(StrEnum):
    INTENT_CREATED = "intent_created"
    NO_INTENT = "no_intent"


class TradeIntentSide(StrEnum):
    BUY = "buy"


class TradeIntentStatus(StrEnum):
    PENDING_RISK = "pending_risk"
