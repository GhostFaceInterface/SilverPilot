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


class SourceRole(StrEnum):
    REFERENCE_MARKET = "reference_market"
    EXECUTION_QUOTE = "execution_quote"
    FX_CONVERSION = "fx_conversion"
    BENCHMARK = "benchmark"
    NEWS = "news"


class SourcePurpose(StrEnum):
    COLLECTION = "collection"
    WARMUP = "warmup"
    INDICATOR = "indicator"
    STRATEGY = "strategy"
    RISK = "risk"
    EXECUTION = "execution"
    VALUATION = "valuation"
    REPORTING = "reporting"


class IndicatorSourcePolicy(StrEnum):
    REFERENCE_MARKET_FIRST = "reference_market_first"
    EXECUTION_BANK_DIAGNOSTIC = "execution_bank_diagnostic"


class ExecutionSourcePolicy(StrEnum):
    ACCOUNT_BOUND_BANK_QUOTE = "account_bound_bank_quote"


class EndpointStatus(StrEnum):
    UNKNOWN = "unknown"
    OK = "ok"
    DEGRADED = "degraded"
    FAILED = "failed"


class MarketSessionStatus(StrEnum):
    UNKNOWN = "unknown"
    OPEN = "open"
    CLOSED = "closed"
    INDICATIVE_ONLY = "indicative_only"


class QuoteUsability(StrEnum):
    UNKNOWN = "unknown"
    ELIGIBLE = "eligible"
    BLOCKED = "blocked"
    OBSERVATION_ONLY = "observation_only"
    INDICATIVE_ONLY = "indicative_only"


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
    SELL = "sell"


class TradeIntentStatus(StrEnum):
    PENDING_RISK = "pending_risk"


class RiskDecisionOutcome(StrEnum):
    APPROVE = "approve"
    REDUCE = "reduce"
    REJECT = "reject"


class PaperOrderSide(StrEnum):
    BUY = "buy"
    SELL = "sell"


class PaperOrderStatus(StrEnum):
    PENDING = "pending"
    EXECUTED = "executed"
    REJECTED = "rejected"


class BacktestRunStatus(StrEnum):
    COMPLETED = "completed"
    FAILED = "failed"
