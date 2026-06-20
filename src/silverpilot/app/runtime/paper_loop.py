import argparse
import json
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from time import sleep
from uuid import UUID, uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session

from silverpilot.app.collectors.price_collector import (
    QuoteBarBuilder,
    collect_bank_instrument_once,
)
from silverpilot.app.core.settings import Settings, get_settings
from silverpilot.app.db.models import (
    MarketBarModel,
    MarketRegimeSnapshotModel,
    PositionModel,
    PriceQuoteModel,
    RuntimeTickModel,
    StrategyRunModel,
    SystemHealthEventModel,
    TradeIntentModel,
)
from silverpilot.app.db.session import create_db_engine
from silverpilot.app.domain.enums import (
    IndicatorSourcePolicy,
    InstrumentType,
    PaperOrderSide,
    TradeIntentStatus,
)
from silverpilot.app.domain.interfaces import PriceProvider
from silverpilot.app.indicators.service import IndicatorName, IndicatorService
from silverpilot.app.paper_trading.service import PaperBroker, PaperOrderRequest
from silverpilot.app.providers.kuveyt_turk import KUVEYT_TURK_SOURCE_NAME, KuveytTurkPriceProvider
from silverpilot.app.regimes.service import RegimeDetector
from silverpilot.app.risks.service import RiskContext, RiskManager
from silverpilot.app.runtime.warmup import WarmupProgress, calculate_warmup_progress
from silverpilot.app.strategies.service import StrategyEngine


@dataclass(frozen=True)
class PaperRuntimeConfig:
    account_id: UUID
    bank_instrument_id: UUID
    execution_instrument_id: UUID
    strategy_id: UUID
    indicator_source_policy: IndicatorSourcePolicy = IndicatorSourcePolicy.REFERENCE_MARKET_FIRST
    reference_instrument_id: UUID | None = None
    reference_source: str | None = None
    reference_timeframe: str | None = None
    source: str = KUVEYT_TURK_SOURCE_NAME
    timeframe: str = "5m"
    warmup_bars: int = 201
    stop_loss_pct: Decimal = Decimal("-0.03")
    take_profit_pct: Decimal = Decimal("0.05")
    high_volatility_exit_fraction: Decimal = Decimal("0.50")


@dataclass(frozen=True)
class PaperRuntimeTickResult:
    status: str
    summary: dict[str, object]


class PaperRuntime:
    def __init__(self, *, session: Session, config: PaperRuntimeConfig) -> None:
        self._session = session
        self._config = config

    def tick(
        self, *, now: datetime, provider: PriceProvider | None = None
    ) -> PaperRuntimeTickResult:
        started_at = now
        trade_intent_ids: list[str] = []
        risk_decision_ids: list[str] = []
        trade_ids: list[str] = []
        summary: dict[str, object] = {
            "quote_inserted": False,
            "bar_inserted": False,
            "indicators": {},
            "regime": None,
            "strategy_run_id": None,
            "trade_intent_ids": trade_intent_ids,
            "risk_decision_ids": risk_decision_ids,
            "trade_ids": trade_ids,
            "warmup": {},
        }
        status = "ok"
        try:
            quote_result = collect_bank_instrument_once(
                self._session,
                bank_instrument_id=self._config.bank_instrument_id,
                provider=provider or KuveytTurkPriceProvider(),
                commit=False,
            )
            summary["quote_id"] = str(quote_result.quote.id)
            summary["quote_inserted"] = quote_result.inserted
            bar = self._build_latest_closed_bar(now=now)
            if bar is None:
                status = "warming_up"
                summary["warmup"] = {"reason": "no_closed_bar"}
                return self._record_tick(status, summary, started_at, now)
            summary["bar_id"] = str(bar.id)
            summary["bar_inserted"] = True

            warmup = self._warmup_progress()
            summary["warmup"] = warmup.as_dict()
            if not warmup.complete:
                status = "warming_up"
                return self._record_tick(status, summary, started_at, now)

            summary["indicators"] = self._calculate_indicators(bar, now)
            regime = RegimeDetector(session=self._session).detect_and_cache(
                instrument_type=InstrumentType.EXECUTION,
                instrument_id=self._config.bank_instrument_id,
                source=self._config.source,
                timeframe=self._config.timeframe,
                source_bar_end_at=bar.bar_end_at,
                detected_at=now,
            )
            summary["regime"] = regime.snapshot.regime
            summary["regime_snapshot_id"] = str(regime.snapshot.id)

            strategy_result = StrategyEngine(session=self._session).run(
                strategy_id=self._config.strategy_id,
                account_id=self._config.account_id,
                instrument_type=InstrumentType.EXECUTION,
                instrument_id=self._config.bank_instrument_id,
                source=self._config.source,
                timeframe=self._config.timeframe,
                source_bar_end_at=bar.bar_end_at,
                run_at=now,
            )
            summary["strategy_run_id"] = str(strategy_result.run.id)
            intents = [
                *strategy_result.intents,
                *self._exit_intents(strategy_result.run, regime.snapshot, now),
            ]
            trade_intent_ids.extend(str(intent.id) for intent in intents)
            for intent in intents:
                decision = (
                    RiskManager(session=self._session)
                    .evaluate(
                        trade_intent_id=intent.id,
                        context=self._risk_context(now),
                    )
                    .decision
                )
                risk_decision_ids.append(str(decision.id))
                if decision.decision in {"approve", "reduce"}:
                    trade = (
                        PaperBroker(session=self._session)
                        .execute(
                            PaperOrderRequest(
                                risk_decision_id=decision.id,
                                side=PaperOrderSide(intent.side),
                                executed_at=now,
                                quote_id=decision.quote_id,
                            )
                        )
                        .trade
                    )
                    trade_ids.append(str(trade.id))
            return self._record_tick(status, summary, started_at, now)
        except Exception as exc:
            self._session.rollback()
            summary["error"] = str(exc)
            status = "failed"
            with self._session.begin():
                return self._record_tick(status, summary, started_at, now)

    def _build_latest_closed_bar(self, *, now: datetime) -> MarketBarModel | None:
        end_at = _floor_time(now, self._timeframe_delta())
        start_at = end_at - self._timeframe_delta()
        try:
            return (
                QuoteBarBuilder(session=self._session)
                .build_execution_bar(
                    bank_instrument_id=self._config.bank_instrument_id,
                    source=self._config.source,
                    timeframe=self._config.timeframe,
                    bar_start_at=start_at,
                    bar_end_at=end_at,
                )
                .bar
            )
        except ValueError:
            return None

    def _calculate_indicators(self, bar: MarketBarModel, now: datetime) -> dict[str, str]:
        service = IndicatorService(session=self._session)
        requested: list[tuple[IndicatorName, dict[str, object]]] = [
            ("ema", {"period": 50}),
            ("ema", {"period": 200}),
            ("rsi", {"period": 14}),
            ("atr", {"period": 14}),
            ("adx", {"period": 14}),
            ("bb_width", {"period": 20}),
        ]
        values: dict[str, str] = {}
        for name, parameters in requested:
            try:
                result = service.calculate_and_cache(
                    instrument_type=InstrumentType.EXECUTION,
                    instrument_id=self._config.bank_instrument_id,
                    source=self._config.source,
                    timeframe=self._config.timeframe,
                    indicator_name=name,
                    parameters=parameters,
                    source_bar_end_at=bar.bar_end_at,
                    calculated_at=now,
                )
                values[f"{name}_{parameters['period']}"] = str(result.snapshot.value)
            except ValueError as exc:
                values[f"{name}_{parameters['period']}"] = f"missing:{exc}"
        return values

    def _exit_intents(
        self,
        strategy_run: StrategyRunModel,
        regime: MarketRegimeSnapshotModel,
        now: datetime,
    ) -> list[TradeIntentModel]:
        position = self._session.scalar(
            select(PositionModel).where(
                PositionModel.account_id == self._config.account_id,
                PositionModel.bank_instrument_id == self._config.bank_instrument_id,
                PositionModel.quantity > 0,
            )
        )
        if position is None:
            return []
        quote = self._session.scalar(
            select(PriceQuoteModel)
            .where(
                PriceQuoteModel.bank_instrument_id == self._config.bank_instrument_id,
                PriceQuoteModel.source == self._config.source,
                PriceQuoteModel.observed_at <= now,
            )
            .order_by(PriceQuoteModel.observed_at.desc(), PriceQuoteModel.fetched_at.desc())
        )
        if quote is None:
            return []
        return_pct = (Decimal(quote.bank_buy_price) - Decimal(position.average_cost)) / Decimal(
            position.average_cost
        )
        quantity = Decimal(position.quantity)
        reason = None
        if regime.regime == "trend_down":
            reason = "exit_trend_down"
        elif regime.regime == "high_volatility":
            reason = "exit_high_volatility"
            quantity = (quantity * self._config.high_volatility_exit_fraction).quantize(
                Decimal("0.00000001")
            )
        elif return_pct <= self._config.stop_loss_pct:
            reason = "exit_stop_loss"
        elif return_pct >= self._config.take_profit_pct:
            reason = "exit_take_profit"
        if reason is None or quantity <= Decimal("0"):
            return []
        cash_amount = (quantity * Decimal(quote.bank_buy_price)).quantize(Decimal("0.00000001"))
        intent = TradeIntentModel(
            id=uuid4(),
            account_id=self._config.account_id,
            strategy_run_id=strategy_run.id,
            side="sell",
            cash_amount=cash_amount,
            quantity=quantity,
            signal_time=now,
            status=TradeIntentStatus.PENDING_RISK.value,
            rationale=reason,
            evidence={"reason": reason, "return_pct": str(return_pct), "quantity": str(quantity)},
            created_at=now,
        )
        self._session.add(intent)
        self._session.flush()
        return [intent]

    def _risk_context(self, now: datetime) -> RiskContext:
        return RiskContext(
            execution_instrument_id=self._config.execution_instrument_id,
            quote_source=self._config.source,
            evaluated_at=now,
            current_position_cash=Decimal("0"),
            current_drawdown=Decimal("0"),
            current_daily_loss=Decimal("0"),
            expected_edge_after_costs=Decimal("0"),
        )

    def _warmup_progress(self) -> WarmupProgress:
        return calculate_warmup_progress(
            self._session,
            indicator_source_policy=self._config.indicator_source_policy,
            required_bars=self._config.warmup_bars,
            execution_bar_instrument_id=self._config.bank_instrument_id,
            execution_source=self._config.source,
            execution_timeframe=self._config.timeframe,
            reference_instrument_id=self._config.reference_instrument_id,
            reference_source=self._config.reference_source,
            reference_timeframe=self._config.reference_timeframe,
        )

    def _record_tick(
        self,
        status: str,
        summary: dict[str, object],
        started_at: datetime,
        finished_at: datetime,
    ) -> PaperRuntimeTickResult:
        severity = "error" if status == "failed" else "info"
        tick = RuntimeTickModel(
            id=uuid4(),
            account_id=self._config.account_id,
            bank_instrument_id=self._config.bank_instrument_id,
            execution_instrument_id=self._config.execution_instrument_id,
            strategy_id=self._config.strategy_id,
            status=status,
            summary=summary,
            started_at=started_at,
            finished_at=finished_at,
            created_at=finished_at,
        )
        event = SystemHealthEventModel(
            id=uuid4(),
            component="paper_runtime",
            status=status,
            severity=severity,
            message=f"paper runtime tick {status}",
            payload=summary,
            occurred_at=finished_at,
            created_at=finished_at,
        )
        self._session.add_all([tick, event])
        self._session.commit()
        return PaperRuntimeTickResult(status=status, summary=summary)

    def _timeframe_delta(self) -> timedelta:
        if self._config.timeframe == "5m":
            return timedelta(minutes=5)
        raise ValueError(f"unsupported timeframe: {self._config.timeframe}")


def config_from_settings(settings: Settings) -> PaperRuntimeConfig:
    required = {
        "runtime_account_id": settings.runtime_account_id,
        "runtime_bank_instrument_id": settings.runtime_bank_instrument_id,
        "runtime_execution_instrument_id": settings.runtime_execution_instrument_id,
        "runtime_strategy_id": settings.runtime_strategy_id,
    }
    missing = [name for name, value in required.items() if value is None]
    if missing:
        raise ValueError(f"missing runtime settings: {','.join(missing)}")
    assert settings.runtime_account_id is not None
    assert settings.runtime_bank_instrument_id is not None
    assert settings.runtime_execution_instrument_id is not None
    assert settings.runtime_strategy_id is not None
    return PaperRuntimeConfig(
        account_id=settings.runtime_account_id,
        bank_instrument_id=settings.runtime_bank_instrument_id,
        execution_instrument_id=settings.runtime_execution_instrument_id,
        strategy_id=settings.runtime_strategy_id,
        indicator_source_policy=settings.indicator_source_policy,
        reference_instrument_id=settings.runtime_reference_instrument_id,
        reference_source=settings.runtime_reference_source,
        reference_timeframe=settings.runtime_reference_timeframe,
        timeframe=settings.runtime_bar_timeframe,
        warmup_bars=settings.runtime_warmup_bars,
        stop_loss_pct=Decimal(str(settings.runtime_exit_stop_loss_pct)),
        take_profit_pct=Decimal(str(settings.runtime_exit_take_profit_pct)),
        high_volatility_exit_fraction=Decimal(str(settings.runtime_exit_high_volatility_fraction)),
    )


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run the SilverPilot paper runtime loop.")
    parser.add_argument("--database-url", default=None)
    parser.add_argument("--once", action="store_true")
    args = parser.parse_args(argv)
    settings = get_settings()
    engine = create_db_engine(args.database_url)
    while True:
        if not settings.runtime_enabled:
            print(json.dumps({"status": "disabled", "summary": {"runtime_enabled": False}}))
            if args.once:
                return 0
            sleep(settings.runtime_collect_interval_seconds)
            continue
        config = config_from_settings(settings)
        now = datetime.now(UTC)
        with Session(engine) as session:
            result = PaperRuntime(session=session, config=config).tick(now=now)
        print(json.dumps({"status": result.status, "summary": result.summary}, sort_keys=True))
        if args.once:
            return 0 if result.status != "failed" else 1
        sleep(settings.runtime_collect_interval_seconds)


def _floor_time(value: datetime, delta: timedelta) -> datetime:
    epoch = datetime(1970, 1, 1, tzinfo=UTC)
    aware = value if value.tzinfo is not None else value.replace(tzinfo=UTC)
    seconds = int((aware - epoch).total_seconds())
    width = int(delta.total_seconds())
    return epoch + timedelta(seconds=seconds - (seconds % width))


if __name__ == "__main__":
    raise SystemExit(main())
