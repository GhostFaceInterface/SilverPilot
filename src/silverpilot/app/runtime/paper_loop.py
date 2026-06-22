import argparse
import json
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from time import sleep
from uuid import UUID, uuid4

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from silverpilot.app.collectors.price_collector import (
    QuoteBarBuilder,
    collect_bank_instrument_once,
)
from silverpilot.app.collectors.reference_backfill import backfill_reference_bars
from silverpilot.app.core.settings import Settings, get_settings
from silverpilot.app.db.models import (
    FxReferenceInstrumentModel,
    MarketBarModel,
    MarketRegimeSnapshotModel,
    PositionModel,
    PriceQuoteModel,
    ReferenceDataBackfillRunModel,
    ReferenceMarketInstrumentModel,
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
from silverpilot.app.providers.yahoo_finance import (
    YAHOO_RESEARCH_SOURCE_NAME,
    YahooFinanceReferenceProvider,
)
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
    fx_source: str | None = None
    fx_pair: str | None = None
    reference_refresh_enabled: bool = True
    reference_refresh_period: str = "5d"
    reference_refresh_interval_seconds: int = 1800
    reference_ingestion_delay_seconds: int = 60
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
            execution_bar = self._build_latest_closed_bar(now=now)
            if execution_bar is None:
                status = "warming_up"
                summary["warmup"] = {"reason": "no_closed_bar"}
                return self._record_tick(status, summary, started_at, now)
            summary["bar_id"] = str(execution_bar.id)
            summary["bar_inserted"] = True

            source_gate_reason = self._reference_source_gate_reason()
            if source_gate_reason is not None:
                status = "warming_up"
                summary["warmup"] = {
                    "reason": source_gate_reason,
                    "blocked_by": "source_feasibility_gate",
                    "next_action": (
                        "Review and write approved SI=F and TRY=X Yahoo dry-run backfills."
                    ),
                }
                return self._record_tick(status, summary, started_at, now)

            summary["reference_refresh"] = self._refresh_reference_inputs(now)

            warmup = self._warmup_progress(now)
            summary["warmup"] = warmup.as_dict()
            if not warmup.complete:
                status = "warming_up"
                return self._record_tick(status, summary, started_at, now)

            signal_bar = self._latest_signal_bar(decision_at=now, execution_bar=execution_bar)
            if signal_bar is None:
                status = "warming_up"
                summary["warmup"] = {**warmup.as_dict(), "reason": "no_signal_bar"}
                return self._record_tick(status, summary, started_at, now)
            summary["signal_bar_id"] = str(signal_bar.id)
            summary["signal_instrument_type"] = signal_bar.instrument_type
            summary["signal_instrument_id"] = str(signal_bar.instrument_id)
            summary["signal_source"] = signal_bar.source
            summary["signal_timeframe"] = signal_bar.timeframe
            summary["signal_bar_end_at"] = signal_bar.bar_end_at.isoformat()
            summary["signal_available_at"] = (
                signal_bar.signal_available_at.isoformat()
                if signal_bar.signal_available_at is not None
                else None
            )

            summary["indicators"] = self._calculate_indicators(signal_bar, now)
            regime = RegimeDetector(session=self._session).detect_and_cache(
                instrument_type=InstrumentType(signal_bar.instrument_type),
                instrument_id=signal_bar.instrument_id,
                source=signal_bar.source,
                timeframe=signal_bar.timeframe,
                source_bar_end_at=signal_bar.bar_end_at,
                detected_at=now,
            )
            summary["regime"] = regime.snapshot.regime
            summary["regime_snapshot_id"] = str(regime.snapshot.id)

            strategy_result = StrategyEngine(session=self._session).run(
                strategy_id=self._config.strategy_id,
                account_id=self._config.account_id,
                instrument_type=InstrumentType(signal_bar.instrument_type),
                instrument_id=signal_bar.instrument_id,
                source=signal_bar.source,
                timeframe=signal_bar.timeframe,
                source_bar_end_at=signal_bar.bar_end_at,
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

    def _latest_signal_bar(
        self,
        *,
        decision_at: datetime,
        execution_bar: MarketBarModel,
    ) -> MarketBarModel | None:
        if self._config.indicator_source_policy == IndicatorSourcePolicy.EXECUTION_BANK_DIAGNOSTIC:
            return execution_bar
        if (
            self._config.reference_instrument_id is None
            or not self._config.reference_source
            or not self._config.reference_timeframe
        ):
            return None
        return self._session.scalar(
            select(MarketBarModel)
            .where(
                MarketBarModel.instrument_type == InstrumentType.REFERENCE.value,
                MarketBarModel.instrument_id == self._config.reference_instrument_id,
                MarketBarModel.source == self._config.reference_source,
                MarketBarModel.timeframe == self._config.reference_timeframe,
                or_(
                    MarketBarModel.signal_available_at.is_(None),
                    MarketBarModel.signal_available_at <= decision_at,
                ),
            )
            .order_by(MarketBarModel.bar_end_at.desc(), MarketBarModel.id.desc())
        )

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
                    instrument_type=InstrumentType(bar.instrument_type),
                    instrument_id=bar.instrument_id,
                    source=bar.source,
                    timeframe=bar.timeframe,
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

    def _reference_source_gate_reason(self) -> str | None:
        if self._config.indicator_source_policy != IndicatorSourcePolicy.REFERENCE_MARKET_FIRST:
            return None
        if (
            self._config.reference_instrument_id is None
            or not self._config.reference_source
            or not self._config.reference_timeframe
        ):
            return None
        if not self._config.fx_source or not self._config.fx_pair:
            return "fx_source_not_configured"
        reference = self._session.get(
            ReferenceMarketInstrumentModel,
            self._config.reference_instrument_id,
        )
        if reference is None:
            return "reference_instrument_not_found"
        reference_reason = _approved_yahoo_paper_source_reason(
            source=reference.source,
            symbol=reference.symbol,
            timeframe=self._config.reference_timeframe,
            source_delay_status=reference.source_delay_status,
            data_delay_seconds=reference.data_delay_seconds,
            source_risk_status=reference.source_risk_status,
            approved_scope=reference.approved_scope,
            approved_timeframe=reference.approved_timeframe,
            approved_symbols=reference.approved_symbols,
            real_money_allowed=reference.real_money_allowed,
        )
        if reference_reason is not None:
            return reference_reason
        fx = self._session.scalar(
            select(FxReferenceInstrumentModel).where(
                FxReferenceInstrumentModel.source == self._config.fx_source,
                FxReferenceInstrumentModel.pair == self._config.fx_pair,
            )
        )
        if fx is None:
            return "fx_instrument_not_found"
        return _approved_yahoo_paper_source_reason(
            source=fx.source,
            symbol=fx.symbol,
            timeframe=self._config.reference_timeframe,
            source_delay_status=fx.source_delay_status,
            data_delay_seconds=fx.data_delay_seconds,
            source_risk_status=fx.source_risk_status,
            approved_scope=fx.approved_scope,
            approved_timeframe=fx.approved_timeframe,
            approved_symbols=fx.approved_symbols,
            real_money_allowed=fx.real_money_allowed,
        )

    def _refresh_reference_inputs(self, now: datetime) -> dict[str, object]:
        if not self._config.reference_refresh_enabled:
            return {"status": "skipped", "reason": "reference_refresh_disabled"}
        if self._config.reference_source != YAHOO_RESEARCH_SOURCE_NAME:
            return {"status": "skipped", "reason": "reference_source_not_yahoo_research"}
        if self._config.reference_instrument_id is None or self._config.reference_timeframe is None:
            return {"status": "skipped", "reason": "reference_source_not_configured"}
        reference = self._session.get(
            ReferenceMarketInstrumentModel,
            self._config.reference_instrument_id,
        )
        fx = None
        if self._config.fx_source and self._config.fx_pair:
            fx = self._session.scalar(
                select(FxReferenceInstrumentModel).where(
                    FxReferenceInstrumentModel.source == self._config.fx_source,
                    FxReferenceInstrumentModel.pair == self._config.fx_pair,
                )
            )
        if reference is None or fx is None:
            return {"status": "skipped", "reason": "reference_or_fx_not_found"}

        instruments: list[ReferenceMarketInstrumentModel | FxReferenceInstrumentModel] = [
            reference,
            fx,
        ]
        refreshed: list[dict[str, object]] = []
        for instrument in instruments:
            if not self._reference_refresh_due(instrument_id=instrument.id, now=now):
                refreshed.append(
                    {
                        "symbol": instrument.symbol,
                        "status": "skipped",
                        "reason": "refresh_interval_not_elapsed",
                    }
                )
                continue
            delay_seconds = _effective_yahoo_delay_seconds(
                data_delay_seconds=instrument.data_delay_seconds,
                source_delay_status=instrument.source_delay_status,
            )
            if delay_seconds is None:
                refreshed.append(
                    {
                        "symbol": instrument.symbol,
                        "status": "skipped",
                        "reason": "source_delay_not_approved",
                    }
                )
                continue
            provider = YahooFinanceReferenceProvider(
                instrument_id=instrument.id,
                source=instrument.source,
                data_delay_seconds=delay_seconds,
                ingestion_delay_seconds=self._config.reference_ingestion_delay_seconds,
            )
            result = backfill_reference_bars(
                self._session,
                instrument=instrument,
                provider=provider,
                timeframe=self._config.reference_timeframe,
                period=self._config.reference_refresh_period,
                dry_run=False,
                started_at=now,
            )
            refreshed.append(
                {
                    "symbol": instrument.symbol,
                    "status": result.status,
                    "bars_fetched": result.bars_fetched,
                    "rows_inserted": result.rows_inserted,
                    "rows_updated": result.rows_updated,
                    "run_id": str(result.run.id),
                }
            )
        status = "ok"
        if any(item.get("status") == "failed" for item in refreshed):
            status = "degraded"
        elif all(item.get("status") == "skipped" for item in refreshed):
            status = "skipped"
        return {
            "status": status,
            "period": self._config.reference_refresh_period,
            "items": refreshed,
        }

    def _reference_refresh_due(self, *, instrument_id: UUID, now: datetime) -> bool:
        interval = timedelta(seconds=self._config.reference_refresh_interval_seconds)
        if interval <= timedelta(0):
            return True
        last_started_at = self._session.scalar(
            select(ReferenceDataBackfillRunModel.started_at)
            .where(
                ReferenceDataBackfillRunModel.source == YAHOO_RESEARCH_SOURCE_NAME,
                ReferenceDataBackfillRunModel.instrument_id == instrument_id,
                ReferenceDataBackfillRunModel.timeframe == self._config.reference_timeframe,
                ReferenceDataBackfillRunModel.period == self._config.reference_refresh_period,
            )
            .order_by(ReferenceDataBackfillRunModel.started_at.desc())
            .limit(1)
        )
        if last_started_at is None:
            return True
        return _aware_datetime(now) - _aware_datetime(last_started_at) >= interval

    def _warmup_progress(self, decision_at: datetime) -> WarmupProgress:
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
            decision_at=decision_at,
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
        fx_source=settings.runtime_fx_source,
        fx_pair=settings.runtime_fx_pair,
        reference_refresh_enabled=settings.runtime_reference_refresh_enabled,
        reference_refresh_period=settings.runtime_reference_refresh_period,
        reference_refresh_interval_seconds=settings.runtime_reference_refresh_interval_seconds,
        reference_ingestion_delay_seconds=settings.reference_ingestion_delay_seconds,
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


def _aware_datetime(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value


def _approved_yahoo_paper_source_reason(
    *,
    source: str,
    symbol: str,
    timeframe: str | None,
    source_delay_status: str | None,
    data_delay_seconds: int | None,
    source_risk_status: str | None,
    approved_scope: str | None,
    approved_timeframe: str | None,
    approved_symbols: str | None,
    real_money_allowed: bool,
) -> str | None:
    if source != "yahoo_research":
        return "reference_source_not_yahoo_research"
    if timeframe != "4h" or approved_timeframe != "4h":
        return "reference_timeframe_not_approved"
    if source_risk_status != "owner_accepted_paper_use_risk":
        return "source_risk_not_owner_accepted"
    if approved_scope != "live-paper only":
        return "source_scope_not_live_paper"
    if real_money_allowed:
        return "real_money_not_allowed_for_yahoo"
    approved = {item.strip() for item in (approved_symbols or "").split(",") if item.strip()}
    if symbol not in approved:
        return "symbol_not_owner_approved"
    if data_delay_seconds is None and source_delay_status != "assumed_conservative":
        return "source_delay_not_approved"
    return None


def _effective_yahoo_delay_seconds(
    *,
    data_delay_seconds: int | None,
    source_delay_status: str | None,
) -> int | None:
    if data_delay_seconds is not None:
        return data_delay_seconds
    if source_delay_status == "assumed_conservative":
        return 1800
    return None


if __name__ == "__main__":
    raise SystemExit(main())
