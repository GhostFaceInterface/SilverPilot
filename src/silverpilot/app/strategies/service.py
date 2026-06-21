import hashlib
import json
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from silverpilot.app.db.models import (
    IndicatorSnapshotModel,
    MarketBarModel,
    MarketRegimeSnapshotModel,
    StrategyModel,
    StrategyRunModel,
    TradeIntentModel,
    VirtualAccountModel,
)
from silverpilot.app.domain.enums import (
    InstrumentType,
    MarketRegime,
    StrategyRunStatus,
    TradeIntentSide,
    TradeIntentStatus,
)
from silverpilot.app.indicators.service import hash_parameters


@dataclass(frozen=True)
class TrendUpPullbackConfig:
    max_data_age: timedelta = timedelta(hours=2)
    default_cash_amount: Decimal = Decimal("1000")
    min_rsi: Decimal = Decimal("35")
    max_rsi: Decimal = Decimal("60")
    max_close_above_ema_50_pct: Decimal = Decimal("0.01")

    def __post_init__(self) -> None:
        if self.max_data_age <= timedelta(0):
            raise ValueError("max_data_age must be greater than zero")
        if self.default_cash_amount <= Decimal("0"):
            raise ValueError("default_cash_amount must be greater than zero")
        if self.min_rsi < Decimal("0") or self.max_rsi > Decimal("100"):
            raise ValueError("RSI bounds must be between 0 and 100")
        if self.min_rsi > self.max_rsi:
            raise ValueError("min_rsi cannot be greater than max_rsi")
        if self.max_close_above_ema_50_pct < Decimal("0"):
            raise ValueError("max_close_above_ema_50_pct cannot be negative")


@dataclass(frozen=True)
class StrategyEngineResult:
    run: StrategyRunModel
    intents: list[TradeIntentModel]


@dataclass(frozen=True)
class TrendUpPullbackDecision:
    create_intent: bool
    status: StrategyRunStatus
    cash_amount: Decimal
    reasons: list[str]
    evidence_updates: dict[str, Any]

    @classmethod
    def create(
        cls,
        *,
        cash_amount: Decimal,
        reasons: list[str],
        evidence_updates: dict[str, Any],
    ) -> "TrendUpPullbackDecision":
        return cls(
            create_intent=True,
            status=StrategyRunStatus.INTENT_CREATED,
            cash_amount=cash_amount,
            reasons=reasons,
            evidence_updates=evidence_updates,
        )

    @classmethod
    def no_intent(
        cls,
        *,
        reasons: list[str],
        evidence_updates: dict[str, Any] | None = None,
    ) -> "TrendUpPullbackDecision":
        return cls(
            create_intent=False,
            status=StrategyRunStatus.NO_INTENT,
            cash_amount=Decimal("0"),
            reasons=reasons,
            evidence_updates=evidence_updates or {},
        )


class StrategyEngine:
    """Runs the first deterministic trend-up pullback strategy."""

    def __init__(self, *, session: Session, config: TrendUpPullbackConfig | None = None) -> None:
        self._session = session
        self._config = config or TrendUpPullbackConfig()

    def run(
        self,
        *,
        strategy_id: UUID,
        account_id: UUID,
        instrument_type: InstrumentType,
        instrument_id: UUID,
        source: str,
        timeframe: str,
        source_bar_end_at: datetime,
        run_at: datetime,
    ) -> StrategyEngineResult:
        if _aware_datetime(source_bar_end_at) > _aware_datetime(run_at):
            raise ValueError("source_bar_end_at cannot be after run_at")

        strategy = self._load_strategy(strategy_id)
        self._load_active_account(account_id)
        evidence: dict[str, Any] = {
            "strategy": {"name": strategy.name, "version": strategy.version},
            "reasons": [],
        }
        bar = self._closed_bar(
            instrument_type=instrument_type,
            instrument_id=instrument_id,
            source=source,
            timeframe=timeframe,
            source_bar_end_at=source_bar_end_at,
        )
        regime = self._regime_snapshot(
            instrument_type=instrument_type,
            instrument_id=instrument_id,
            source=source,
            timeframe=timeframe,
            source_bar_end_at=source_bar_end_at,
        )
        indicators = self._indicator_values(
            instrument_type=instrument_type,
            instrument_id=instrument_id,
            source=source,
            timeframe=timeframe,
            source_bar_end_at=source_bar_end_at,
        )
        decision = self._evaluate(
            strategy=strategy,
            bar=bar,
            regime=regime,
            indicators=indicators,
            source_bar_end_at=source_bar_end_at,
            run_at=run_at,
            evidence=evidence,
        )
        input_hash = _hash_inputs(
            {
                "strategy_id": str(strategy.id),
                "strategy_version": strategy.version,
                "strategy_parameters": strategy.parameters,
                "bar_close": str(bar.close) if bar is not None else None,
                "regime_id": str(regime.id) if regime is not None else None,
                "regime": regime.regime if regime is not None else None,
                "indicators": {key: str(value) for key, value in indicators.values.items()},
                "missing_indicators": indicators.missing,
                "source_bar_end_at": source_bar_end_at.isoformat(),
            }
        )
        run = StrategyRunModel(
            strategy_id=strategy.id,
            account_id=account_id,
            instrument_type=instrument_type.value,
            instrument_id=instrument_id,
            source=source,
            timeframe=timeframe,
            source_bar_end_at=source_bar_end_at,
            run_at=run_at,
            regime_snapshot_id=regime.id if regime is not None else None,
            input_hash=input_hash,
            status=decision.status.value,
            evidence=evidence,
            created_at=run_at,
        )
        self._session.add(run)
        self._session.flush()

        intents: list[TradeIntentModel] = []
        if decision.create_intent:
            intent = TradeIntentModel(
                account_id=account_id,
                strategy_run_id=run.id,
                side=TradeIntentSide.BUY.value,
                cash_amount=decision.cash_amount,
                quantity=None,
                signal_time=run_at,
                status=TradeIntentStatus.PENDING_RISK.value,
                rationale="trend_up_pullback_long",
                evidence=evidence,
                created_at=run_at,
            )
            self._session.add(intent)
            self._session.flush()
            intents.append(intent)

        return StrategyEngineResult(run=run, intents=intents)

    def _evaluate(
        self,
        *,
        strategy: StrategyModel,
        bar: MarketBarModel | None,
        regime: MarketRegimeSnapshotModel | None,
        indicators: "_IndicatorLookup",
        source_bar_end_at: datetime,
        run_at: datetime,
        evidence: dict[str, Any],
    ) -> "_StrategyDecision":
        decision = evaluate_trend_up_pullback(
            strategy=strategy,
            bar=bar,
            regime=regime,
            indicators=indicators,
            source_bar_end_at=source_bar_end_at,
            run_at=run_at,
            config=self._config,
        )
        evidence["reasons"].extend(decision.reasons)
        evidence.update(decision.evidence_updates)
        if decision.create_intent:
            return _StrategyDecision.create(decision.cash_amount)
        return _StrategyDecision.no_intent()

    def _load_strategy(self, strategy_id: UUID) -> StrategyModel:
        strategy = self._session.get(StrategyModel, strategy_id)
        if strategy is None:
            raise ValueError(f"strategy was not found: {strategy_id}")
        return strategy

    def _load_active_account(self, account_id: UUID) -> VirtualAccountModel:
        account = self._session.get(VirtualAccountModel, account_id)
        if account is None:
            raise ValueError(f"account was not found: {account_id}")
        if account.status != "active":
            raise ValueError(f"account is not active: {account_id}")
        return account

    def _closed_bar(
        self,
        *,
        instrument_type: InstrumentType,
        instrument_id: UUID,
        source: str,
        timeframe: str,
        source_bar_end_at: datetime,
    ) -> MarketBarModel | None:
        return self._session.scalar(
            select(MarketBarModel).where(
                MarketBarModel.instrument_type == instrument_type.value,
                MarketBarModel.instrument_id == instrument_id,
                MarketBarModel.source == source,
                MarketBarModel.timeframe == timeframe,
                MarketBarModel.bar_end_at == source_bar_end_at,
            )
        )

    def _regime_snapshot(
        self,
        *,
        instrument_type: InstrumentType,
        instrument_id: UUID,
        source: str,
        timeframe: str,
        source_bar_end_at: datetime,
    ) -> MarketRegimeSnapshotModel | None:
        return self._session.scalar(
            select(MarketRegimeSnapshotModel).where(
                MarketRegimeSnapshotModel.instrument_type == instrument_type.value,
                MarketRegimeSnapshotModel.instrument_id == instrument_id,
                MarketRegimeSnapshotModel.source == source,
                MarketRegimeSnapshotModel.timeframe == timeframe,
                MarketRegimeSnapshotModel.source_bar_end_at == source_bar_end_at,
            )
        )

    def _indicator_values(
        self,
        *,
        instrument_type: InstrumentType,
        instrument_id: UUID,
        source: str,
        timeframe: str,
        source_bar_end_at: datetime,
    ) -> "_IndicatorLookup":
        snapshots = list(
            self._session.scalars(
                select(IndicatorSnapshotModel).where(
                    IndicatorSnapshotModel.instrument_type == instrument_type.value,
                    IndicatorSnapshotModel.instrument_id == instrument_id,
                    IndicatorSnapshotModel.source == source,
                    IndicatorSnapshotModel.timeframe == timeframe,
                    IndicatorSnapshotModel.source_bar_end_at == source_bar_end_at,
                )
            )
        )
        required: dict[str, tuple[str, dict[str, object]]] = {
            "ema_50": ("ema", {"period": 50}),
            "ema_200": ("ema", {"period": 200}),
            "rsi_14": ("rsi", {"period": 14}),
            "atr_14": ("atr", {"period": 14}),
        }
        values: dict[str, Decimal] = {}
        missing: list[str] = []
        for key, (indicator_name, parameters) in required.items():
            snapshot = _find_indicator_snapshot(snapshots, indicator_name, parameters)
            if snapshot is None:
                missing.append(key)
                continue
            values[key] = Decimal(snapshot.value)
        return _IndicatorLookup(values=values, missing=missing)


@dataclass(frozen=True)
class _IndicatorLookup:
    values: dict[str, Decimal]
    missing: list[str]


@dataclass(frozen=True)
class _StrategyDecision:
    create_intent: bool
    status: StrategyRunStatus
    cash_amount: Decimal

    @classmethod
    def create(cls, cash_amount: Decimal) -> "_StrategyDecision":
        return cls(
            create_intent=True,
            status=StrategyRunStatus.INTENT_CREATED,
            cash_amount=cash_amount,
        )

    @classmethod
    def no_intent(cls) -> "_StrategyDecision":
        return cls(
            create_intent=False,
            status=StrategyRunStatus.NO_INTENT,
            cash_amount=Decimal("0"),
        )


def _find_indicator_snapshot(
    snapshots: list[IndicatorSnapshotModel],
    indicator_name: str,
    parameters: dict[str, object],
) -> IndicatorSnapshotModel | None:
    parameters_hash = hash_parameters(parameters)
    for snapshot in snapshots:
        if (
            snapshot.indicator_name == indicator_name
            and snapshot.parameters_hash == parameters_hash
        ):
            return snapshot
    return None


def evaluate_trend_up_pullback(
    *,
    strategy: StrategyModel,
    bar: MarketBarModel | None,
    regime: MarketRegimeSnapshotModel | None,
    indicators: _IndicatorLookup,
    source_bar_end_at: datetime,
    run_at: datetime,
    config: TrendUpPullbackConfig | None = None,
) -> TrendUpPullbackDecision:
    rule_config = config or TrendUpPullbackConfig()
    if not strategy.enabled:
        return TrendUpPullbackDecision.no_intent(reasons=["strategy_disabled"])
    if strategy.name != "trend_up_pullback":
        return TrendUpPullbackDecision.no_intent(reasons=["unsupported_strategy"])
    if bar is None:
        return TrendUpPullbackDecision.no_intent(reasons=["missing_closed_bar"])
    if _aware_datetime(run_at) - _aware_datetime(source_bar_end_at) > rule_config.max_data_age:
        return TrendUpPullbackDecision.no_intent(reasons=["stale_bar"])
    if regime is None:
        return TrendUpPullbackDecision.no_intent(reasons=["missing_regime"])
    if regime.regime != MarketRegime.TREND_UP.value:
        return TrendUpPullbackDecision.no_intent(reasons=[f"regime_blocked:{regime.regime}"])
    if indicators.missing:
        return TrendUpPullbackDecision.no_intent(
            reasons=["missing_indicators"],
            evidence_updates={"missing_indicators": indicators.missing},
        )

    close = Decimal(bar.close)
    ema_50 = indicators.values["ema_50"]
    ema_200 = indicators.values["ema_200"]
    rsi_14 = indicators.values["rsi_14"]
    atr_14 = indicators.values["atr_14"]
    max_close = ema_50 * (Decimal("1") + rule_config.max_close_above_ema_50_pct)
    evidence_updates: dict[str, Any] = {
        "indicator_values": {key: str(value) for key, value in indicators.values.items()},
        "bar_close": str(close),
        "max_pullback_close": str(max_close),
    }

    if close > max_close:
        return TrendUpPullbackDecision.no_intent(
            reasons=["price_not_in_pullback_zone"],
            evidence_updates=evidence_updates,
        )
    if close < ema_200:
        return TrendUpPullbackDecision.no_intent(
            reasons=["price_below_ema_200"],
            evidence_updates=evidence_updates,
        )
    if rsi_14 < rule_config.min_rsi or rsi_14 > rule_config.max_rsi:
        return TrendUpPullbackDecision.no_intent(
            reasons=["rsi_outside_pullback_bounds"],
            evidence_updates=evidence_updates,
        )
    if atr_14 <= Decimal("0"):
        return TrendUpPullbackDecision.no_intent(
            reasons=["atr_not_positive"],
            evidence_updates=evidence_updates,
        )

    cash_amount = _strategy_cash_amount(strategy.parameters, rule_config.default_cash_amount)
    evidence_updates["cash_amount"] = str(cash_amount)
    return TrendUpPullbackDecision.create(
        cash_amount=cash_amount,
        reasons=["trend_up_pullback_confirmed"],
        evidence_updates=evidence_updates,
    )


def _strategy_cash_amount(parameters: dict[str, object], default: Decimal) -> Decimal:
    raw_value = parameters.get("cash_amount", default)
    value = Decimal(str(raw_value))
    if value <= Decimal("0"):
        raise ValueError("strategy cash_amount must be greater than zero")
    return value


def _hash_inputs(payload: dict[str, object]) -> str:
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def _aware_datetime(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value
