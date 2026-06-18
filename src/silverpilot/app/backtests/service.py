import hashlib
import json
from dataclasses import asdict, dataclass
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from uuid import UUID, uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session
from sqlalchemy.sql import Select

from silverpilot.app.db.models import (
    BacktestDatasetSnapshotModel,
    BacktestRunModel,
    ExecutionInstrumentModel,
    IndicatorSnapshotModel,
    MarketBarModel,
    MarketRegimeSnapshotModel,
    PaperTradeModel,
    PositionModel,
    PriceQuoteModel,
    StrategyModel,
    UserModel,
    VirtualAccountInstrumentModel,
    VirtualAccountModel,
    WalletModel,
)
from silverpilot.app.domain.clocks import SimulatedClock
from silverpilot.app.domain.enums import (
    BacktestRunStatus,
    InstrumentType,
    PaperOrderSide,
)
from silverpilot.app.paper_trading import PaperBroker, PaperCostModel, PaperOrderRequest
from silverpilot.app.risks import RiskContext, RiskManager, RiskPolicy
from silverpilot.app.strategies import StrategyEngine

_MONEY_QUANTUM = Decimal("0.00000001")


@dataclass(frozen=True)
class BacktestConfig:
    strategy_id: UUID
    base_account_id: UUID
    execution_instrument_id: UUID
    instrument_type: InstrumentType
    instrument_id: UUID
    source: str
    timeframe: str
    quote_source: str
    start_at: datetime
    end_at: datetime
    initial_cash: Decimal
    decision_latency: timedelta = timedelta(minutes=1)
    risk_policy: RiskPolicy | None = None
    cost_model: PaperCostModel | None = None

    def __post_init__(self) -> None:
        if self.start_at.tzinfo is None or self.start_at.utcoffset() is None:
            raise ValueError("start_at must be timezone-aware")
        if self.end_at.tzinfo is None or self.end_at.utcoffset() is None:
            raise ValueError("end_at must be timezone-aware")
        if self.start_at >= self.end_at:
            raise ValueError("start_at must be before end_at")
        if self.initial_cash <= Decimal("0"):
            raise ValueError("initial_cash must be greater than zero")
        if self.decision_latency < timedelta(0):
            raise ValueError("decision_latency cannot be negative")
        if not self.source.strip():
            raise ValueError("source is required")
        if not self.timeframe.strip():
            raise ValueError("timeframe is required")
        if not self.quote_source.strip():
            raise ValueError("quote_source is required")


@dataclass(frozen=True)
class BacktestDatasetSnapshotResult:
    snapshot: BacktestDatasetSnapshotModel
    inserted: bool


@dataclass(frozen=True)
class RejectedTradeDTO:
    evaluated_at: datetime
    trade_intent_id: UUID
    reasons: list[str]

    def to_json(self) -> dict[str, object]:
        return {
            "evaluated_at": self.evaluated_at.isoformat(),
            "trade_intent_id": str(self.trade_intent_id),
            "reasons": self.reasons,
        }


@dataclass(frozen=True)
class NoTradeDTO:
    evaluated_at: datetime
    source_bar_end_at: datetime
    reasons: list[str]

    def to_json(self) -> dict[str, object]:
        return {
            "evaluated_at": self.evaluated_at.isoformat(),
            "source_bar_end_at": self.source_bar_end_at.isoformat(),
            "reasons": self.reasons,
        }


@dataclass(frozen=True)
class PortfolioCurvePoint:
    timestamp: datetime
    cash: Decimal
    position_quantity: Decimal
    position_value: Decimal
    total_value: Decimal
    unrealized_pnl: Decimal
    realized_pnl: Decimal
    drawdown: Decimal

    def to_json(self) -> dict[str, object]:
        return {
            "timestamp": self.timestamp.isoformat(),
            "cash": str(self.cash),
            "position_quantity": str(self.position_quantity),
            "position_value": str(self.position_value),
            "total_value": str(self.total_value),
            "unrealized_pnl": str(self.unrealized_pnl),
            "realized_pnl": str(self.realized_pnl),
            "drawdown": str(self.drawdown),
        }


@dataclass(frozen=True)
class BacktestReportDTO:
    dataset_snapshot_id: UUID
    data_hash: str
    backtest_run_id: UUID
    account_id: UUID
    start_at: datetime
    end_at: datetime
    initial_cash: Decimal
    final_value: Decimal
    gross_pnl: Decimal
    pnl_before_costs: Decimal
    pnl_after_costs: Decimal
    total_costs: Decimal
    max_drawdown: Decimal
    trade_count: int
    rejected_trades: list[RejectedTradeDTO]
    no_trade_reasons: list[NoTradeDTO]
    portfolio_curve: list[PortfolioCurvePoint]

    def to_json(self) -> dict[str, object]:
        return {
            "dataset_snapshot_id": str(self.dataset_snapshot_id),
            "data_hash": self.data_hash,
            "backtest_run_id": str(self.backtest_run_id),
            "account_id": str(self.account_id),
            "start_at": self.start_at.isoformat(),
            "end_at": self.end_at.isoformat(),
            "initial_cash": str(self.initial_cash),
            "final_value": str(self.final_value),
            "gross_pnl": str(self.gross_pnl),
            "pnl_before_costs": str(self.pnl_before_costs),
            "pnl_after_costs": str(self.pnl_after_costs),
            "total_costs": str(self.total_costs),
            "max_drawdown": str(self.max_drawdown),
            "trade_count": self.trade_count,
            "rejected_trades": [item.to_json() for item in self.rejected_trades],
            "no_trade_reasons": [item.to_json() for item in self.no_trade_reasons],
            "portfolio_curve": [point.to_json() for point in self.portfolio_curve],
        }


class BacktestDatasetSnapshotService:
    """Builds immutable dataset identities for replay inputs."""

    def __init__(self, *, session: Session) -> None:
        self._session = session

    def create(self, *, config: BacktestConfig) -> BacktestDatasetSnapshotResult:
        payload = self._payload(config)
        data_hash = _hash_payload(payload)
        existing = self._session.scalar(
            select(BacktestDatasetSnapshotModel).where(
                BacktestDatasetSnapshotModel.data_hash == data_hash
            )
        )
        if existing is not None:
            return BacktestDatasetSnapshotResult(snapshot=existing, inserted=False)

        snapshot = BacktestDatasetSnapshotModel(
            id=uuid4(),
            instrument_type=config.instrument_type.value,
            instrument_id=config.instrument_id,
            execution_instrument_id=config.execution_instrument_id,
            source=config.source,
            timeframe=config.timeframe,
            quote_source=config.quote_source,
            start_at=config.start_at.astimezone(UTC),
            end_at=config.end_at.astimezone(UTC),
            input_ranges=payload,
            data_hash=data_hash,
            created_at=config.start_at.astimezone(UTC),
        )
        self._session.add(snapshot)
        self._session.flush()
        return BacktestDatasetSnapshotResult(snapshot=snapshot, inserted=True)

    def _payload(self, config: BacktestConfig) -> dict[str, object]:
        bank_instrument_id = _bank_instrument_id(self._session, config.execution_instrument_id)
        return {
            "config": _config_payload(config),
            "strategy": self._strategy_payload(config.strategy_id),
            "bars": self._bars_payload(config),
            "indicators": self._indicators_payload(config),
            "regimes": self._regimes_payload(config),
            "quotes": self._quotes_payload(
                bank_instrument_id=bank_instrument_id,
                source=config.quote_source,
                start_at=config.start_at,
                end_at=config.end_at,
            ),
        }

    def _strategy_payload(self, strategy_id: UUID) -> dict[str, object]:
        strategy = self._session.get(StrategyModel, strategy_id)
        if strategy is None:
            raise ValueError(f"strategy was not found: {strategy_id}")
        return {
            "id": str(strategy.id),
            "name": strategy.name,
            "version": strategy.version,
            "parameters": strategy.parameters,
            "enabled": strategy.enabled,
        }

    def _bars_payload(self, config: BacktestConfig) -> list[dict[str, object]]:
        bars = self._session.scalars(_bars_query(config)).all()
        return [
            {
                "id": str(bar.id),
                "open": str(bar.open),
                "high": str(bar.high),
                "low": str(bar.low),
                "close": str(bar.close),
                "quote_count": bar.quote_count,
                "bar_start_at": _iso(bar.bar_start_at),
                "bar_end_at": _iso(bar.bar_end_at),
            }
            for bar in bars
        ]

    def _indicators_payload(self, config: BacktestConfig) -> list[dict[str, object]]:
        rows = self._session.scalars(
            select(IndicatorSnapshotModel)
            .where(
                IndicatorSnapshotModel.instrument_type == config.instrument_type.value,
                IndicatorSnapshotModel.instrument_id == config.instrument_id,
                IndicatorSnapshotModel.source == config.source,
                IndicatorSnapshotModel.timeframe == config.timeframe,
                IndicatorSnapshotModel.source_bar_end_at >= config.start_at,
                IndicatorSnapshotModel.source_bar_end_at <= config.end_at,
            )
            .order_by(
                IndicatorSnapshotModel.source_bar_end_at,
                IndicatorSnapshotModel.indicator_name,
                IndicatorSnapshotModel.parameters_hash,
                IndicatorSnapshotModel.id,
            )
        ).all()
        return [
            {
                "id": str(row.id),
                "indicator_name": row.indicator_name,
                "parameters_hash": row.parameters_hash,
                "parameters": row.parameters,
                "value": str(row.value),
                "calculated_at": _iso(row.calculated_at),
                "source_bar_end_at": _iso(row.source_bar_end_at),
            }
            for row in rows
        ]

    def _regimes_payload(self, config: BacktestConfig) -> list[dict[str, object]]:
        rows = self._session.scalars(
            select(MarketRegimeSnapshotModel)
            .where(
                MarketRegimeSnapshotModel.instrument_type == config.instrument_type.value,
                MarketRegimeSnapshotModel.instrument_id == config.instrument_id,
                MarketRegimeSnapshotModel.source == config.source,
                MarketRegimeSnapshotModel.timeframe == config.timeframe,
                MarketRegimeSnapshotModel.source_bar_end_at >= config.start_at,
                MarketRegimeSnapshotModel.source_bar_end_at <= config.end_at,
            )
            .order_by(
                MarketRegimeSnapshotModel.source_bar_end_at,
                MarketRegimeSnapshotModel.config_version,
                MarketRegimeSnapshotModel.id,
            )
        ).all()
        return [
            {
                "id": str(row.id),
                "regime": row.regime,
                "confidence": str(row.confidence),
                "evidence": row.evidence,
                "config_version": row.config_version,
                "starts_at": _iso(row.starts_at),
                "confirmed_at": _iso(row.confirmed_at),
                "source_bar_end_at": _iso(row.source_bar_end_at),
            }
            for row in rows
        ]

    def _quotes_payload(
        self,
        *,
        bank_instrument_id: UUID,
        source: str,
        start_at: datetime,
        end_at: datetime,
    ) -> list[dict[str, object]]:
        rows = self._session.scalars(
            select(PriceQuoteModel)
            .where(
                PriceQuoteModel.bank_instrument_id == bank_instrument_id,
                PriceQuoteModel.source == source,
                PriceQuoteModel.observed_at >= start_at,
                PriceQuoteModel.observed_at <= end_at,
            )
            .order_by(PriceQuoteModel.observed_at, PriceQuoteModel.fetched_at, PriceQuoteModel.id)
        ).all()
        return [
            {
                "id": str(row.id),
                "bank_buy_price": str(row.bank_buy_price),
                "bank_sell_price": str(row.bank_sell_price),
                "observed_at": _iso(row.observed_at),
                "fetched_at": _iso(row.fetched_at),
                "source_hash": row.source_hash,
                "freshness_status": row.freshness_status,
            }
            for row in rows
        ]


class BacktestEngine:
    """Replays strategy, risk, and paper broker behavior on an isolated account."""

    def __init__(self, *, session: Session) -> None:
        self._session = session
        self._snapshots = BacktestDatasetSnapshotService(session=session)

    def run(self, *, config: BacktestConfig) -> BacktestReportDTO:
        snapshot = self._snapshots.create(config=config).snapshot
        clock = SimulatedClock(config.start_at)
        account = self._create_simulated_account(config=config, created_at=clock.now())
        run = BacktestRunModel(
            id=uuid4(),
            dataset_snapshot_id=snapshot.id,
            account_id=account.id,
            strategy_id=config.strategy_id,
            config_hash=_hash_payload(_config_payload(config)),
            status=BacktestRunStatus.COMPLETED.value,
            started_at=config.start_at.astimezone(UTC),
            completed_at=None,
            report_json={"status": "running"},
            created_at=config.start_at.astimezone(UTC),
        )
        self._session.add(run)
        self._session.flush()

        bank_instrument_id = _bank_instrument_id(self._session, config.execution_instrument_id)
        risk_policy = config.risk_policy or RiskPolicy()
        cost_model = config.cost_model or PaperCostModel()
        broker = PaperBroker(session=self._session, cost_model=cost_model)
        portfolio = _PortfolioState(initial_cash=config.initial_cash)
        rejected_trades: list[RejectedTradeDTO] = []
        no_trade_reasons: list[NoTradeDTO] = []
        curve = [
            self._portfolio_point(
                account_id=account.id,
                bank_instrument_id=bank_instrument_id,
                timestamp=config.start_at,
                initial_cash=config.initial_cash,
                previous_peak=portfolio.peak_value,
                quote=None,
            )
        ]
        portfolio = portfolio.update(curve[-1].total_value)

        for bar in self._session.scalars(_bars_query(config)).all():
            source_bar_end_at = _aware_utc(bar.bar_end_at)
            evaluated_at = source_bar_end_at + config.decision_latency
            clock.set(evaluated_at)
            strategy_result = StrategyEngine(session=self._session).run(
                strategy_id=config.strategy_id,
                account_id=account.id,
                instrument_type=config.instrument_type,
                instrument_id=config.instrument_id,
                source=config.source,
                timeframe=config.timeframe,
                source_bar_end_at=source_bar_end_at,
                run_at=clock.now(),
            )
            if not strategy_result.intents:
                no_trade_reasons.append(
                    NoTradeDTO(
                        evaluated_at=clock.now(),
                        source_bar_end_at=source_bar_end_at,
                        reasons=_reasons(strategy_result.run.evidence.get("reasons", [])),
                    )
                )

            for intent in strategy_result.intents:
                quote = _latest_quote(
                    self._session,
                    bank_instrument_id=bank_instrument_id,
                    source=config.quote_source,
                    evaluated_at=clock.now(),
                )
                position_cash = self._position_value(
                    account_id=account.id,
                    bank_instrument_id=bank_instrument_id,
                    quote=quote,
                )
                risk = RiskManager(session=self._session, policy=risk_policy).evaluate(
                    trade_intent_id=intent.id,
                    context=RiskContext(
                        execution_instrument_id=config.execution_instrument_id,
                        quote_source=config.quote_source,
                        evaluated_at=clock.now(),
                        current_position_cash=position_cash,
                        current_drawdown=portfolio.current_drawdown,
                        current_daily_loss=Decimal("0"),
                        expected_edge_after_costs=Decimal("0"),
                    ),
                )
                if risk.decision.decision in {"approve", "reduce"}:
                    broker.execute(
                        PaperOrderRequest(
                            risk_decision_id=risk.decision.id,
                            side=PaperOrderSide.BUY,
                            executed_at=clock.now(),
                        )
                    )
                else:
                    rejected_trades.append(
                        RejectedTradeDTO(
                            evaluated_at=clock.now(),
                            trade_intent_id=intent.id,
                            reasons=list(risk.decision.reasons),
                        )
                    )

            quote = _latest_quote(
                self._session,
                bank_instrument_id=bank_instrument_id,
                source=config.quote_source,
                evaluated_at=clock.now(),
            )
            point = self._portfolio_point(
                account_id=account.id,
                bank_instrument_id=bank_instrument_id,
                timestamp=clock.now(),
                initial_cash=config.initial_cash,
                previous_peak=portfolio.peak_value,
                quote=quote,
            )
            curve.append(point)
            portfolio = portfolio.update(point.total_value)

        total_costs = self._total_costs(account.id)
        final_value = curve[-1].total_value
        pnl_after_costs = _money(final_value - config.initial_cash)
        pnl_before_costs = _money(pnl_after_costs + total_costs)
        report = BacktestReportDTO(
            dataset_snapshot_id=snapshot.id,
            data_hash=snapshot.data_hash,
            backtest_run_id=run.id,
            account_id=account.id,
            start_at=config.start_at.astimezone(UTC),
            end_at=config.end_at.astimezone(UTC),
            initial_cash=_money(config.initial_cash),
            final_value=final_value,
            gross_pnl=pnl_before_costs,
            pnl_before_costs=pnl_before_costs,
            pnl_after_costs=pnl_after_costs,
            total_costs=total_costs,
            max_drawdown=max(point.drawdown for point in curve),
            trade_count=len(self._session.scalars(_trades_query(account.id)).all()),
            rejected_trades=rejected_trades,
            no_trade_reasons=no_trade_reasons,
            portfolio_curve=curve,
        )
        run.completed_at = curve[-1].timestamp
        run.report_json = report.to_json()
        self._session.flush()
        return report

    def _create_simulated_account(
        self,
        *,
        config: BacktestConfig,
        created_at: datetime,
    ) -> VirtualAccountModel:
        base = self._session.get(VirtualAccountModel, config.base_account_id)
        if base is None:
            raise ValueError(f"base account was not found: {config.base_account_id}")
        user = self._session.get(UserModel, base.user_id)
        if user is None:
            raise ValueError(f"base account user was not found: {base.user_id}")
        account = VirtualAccountModel(
            id=uuid4(),
            user_id=user.id,
            name=f"Backtest {config.start_at.date()} {uuid4().hex[:8]}",
            base_currency_id=base.base_currency_id,
            execution_venue_id=base.execution_venue_id,
            starting_balance=_money(config.initial_cash),
            status="active",
            created_at=created_at,
        )
        wallet = WalletModel(
            id=uuid4(),
            virtual_account=account,
            currency_id=base.base_currency_id,
            available_amount=_money(config.initial_cash),
            reserved_amount=Decimal("0"),
            created_at=created_at,
        )
        allowed = VirtualAccountInstrumentModel(
            id=uuid4(),
            virtual_account=account,
            execution_instrument_id=config.execution_instrument_id,
            status="active",
            created_at=created_at,
        )
        self._session.add_all([account, wallet, allowed])
        self._session.flush()
        return account

    def _portfolio_point(
        self,
        *,
        account_id: UUID,
        bank_instrument_id: UUID,
        timestamp: datetime,
        initial_cash: Decimal,
        previous_peak: Decimal,
        quote: PriceQuoteModel | None,
    ) -> PortfolioCurvePoint:
        wallet = self._wallet(account_id)
        position = self._position(account_id=account_id, bank_instrument_id=bank_instrument_id)
        cash = _money(Decimal(wallet.available_amount))
        quantity = Decimal("0")
        position_value = Decimal("0")
        unrealized_pnl = Decimal("0")
        realized_pnl = Decimal("0")
        if position is not None:
            quantity = _money(Decimal(position.quantity))
            realized_pnl = _money(Decimal(position.realized_pnl))
            if quote is not None:
                position_value = _money(quantity * Decimal(quote.bank_buy_price))
                unrealized_pnl = _money(
                    position_value - (quantity * Decimal(position.average_cost))
                )
        total_value = _money(cash + position_value)
        peak = max(previous_peak, initial_cash, total_value)
        drawdown = Decimal("0") if peak <= Decimal("0") else _money((peak - total_value) / peak)
        return PortfolioCurvePoint(
            timestamp=timestamp.astimezone(UTC),
            cash=cash,
            position_quantity=quantity,
            position_value=position_value,
            total_value=total_value,
            unrealized_pnl=unrealized_pnl,
            realized_pnl=realized_pnl,
            drawdown=drawdown,
        )

    def _wallet(self, account_id: UUID) -> WalletModel:
        account = self._session.get(VirtualAccountModel, account_id)
        if account is None:
            raise ValueError(f"account was not found: {account_id}")
        wallet = self._session.scalar(
            select(WalletModel).where(
                WalletModel.virtual_account_id == account.id,
                WalletModel.currency_id == account.base_currency_id,
            )
        )
        if wallet is None:
            raise ValueError("account wallet was not found")
        return wallet

    def _position(
        self,
        *,
        account_id: UUID,
        bank_instrument_id: UUID,
    ) -> PositionModel | None:
        return self._session.scalar(
            select(PositionModel).where(
                PositionModel.account_id == account_id,
                PositionModel.bank_instrument_id == bank_instrument_id,
            )
        )

    def _position_value(
        self,
        *,
        account_id: UUID,
        bank_instrument_id: UUID,
        quote: PriceQuoteModel | None,
    ) -> Decimal:
        position = self._position(account_id=account_id, bank_instrument_id=bank_instrument_id)
        if position is None or quote is None:
            return Decimal("0")
        return _money(Decimal(position.quantity) * Decimal(quote.bank_buy_price))

    def _total_costs(self, account_id: UUID) -> Decimal:
        total = Decimal("0")
        for trade in self._session.scalars(_trades_query(account_id)):
            total += Decimal(trade.fees) + Decimal(trade.taxes) + Decimal(trade.spread_cost)
        return _money(total)


@dataclass(frozen=True)
class _PortfolioState:
    initial_cash: Decimal
    peak_value: Decimal = Decimal("0")
    current_drawdown: Decimal = Decimal("0")

    def __post_init__(self) -> None:
        if self.peak_value == Decimal("0"):
            object.__setattr__(self, "peak_value", _money(self.initial_cash))

    def update(self, total_value: Decimal) -> "_PortfolioState":
        peak = max(self.peak_value, total_value)
        drawdown = Decimal("0") if peak <= Decimal("0") else _money((peak - total_value) / peak)
        return _PortfolioState(
            initial_cash=self.initial_cash,
            peak_value=peak,
            current_drawdown=drawdown,
        )


def _bars_query(config: BacktestConfig) -> Select[tuple[MarketBarModel]]:
    return (
        select(MarketBarModel)
        .where(
            MarketBarModel.instrument_type == config.instrument_type.value,
            MarketBarModel.instrument_id == config.instrument_id,
            MarketBarModel.source == config.source,
            MarketBarModel.timeframe == config.timeframe,
            MarketBarModel.bar_end_at >= config.start_at,
            MarketBarModel.bar_end_at <= config.end_at,
        )
        .order_by(MarketBarModel.bar_end_at, MarketBarModel.id)
    )


def _trades_query(account_id: UUID) -> Select[tuple[PaperTradeModel]]:
    return select(PaperTradeModel).where(PaperTradeModel.account_id == account_id)


def _latest_quote(
    session: Session,
    *,
    bank_instrument_id: UUID,
    source: str,
    evaluated_at: datetime,
) -> PriceQuoteModel | None:
    return session.scalar(
        select(PriceQuoteModel)
        .where(
            PriceQuoteModel.bank_instrument_id == bank_instrument_id,
            PriceQuoteModel.source == source,
            PriceQuoteModel.observed_at <= evaluated_at,
        )
        .order_by(PriceQuoteModel.observed_at.desc(), PriceQuoteModel.fetched_at.desc())
    )


def _bank_instrument_id(session: Session, execution_instrument_id: UUID) -> UUID:
    execution_instrument = session.get(ExecutionInstrumentModel, execution_instrument_id)
    if execution_instrument is None or execution_instrument.bank_instrument_id is None:
        raise ValueError("execution instrument has no bank instrument")
    return execution_instrument.bank_instrument_id


def _config_payload(config: BacktestConfig) -> dict[str, object]:
    risk_policy = config.risk_policy or RiskPolicy()
    cost_model = config.cost_model or PaperCostModel()
    return {
        "strategy_id": str(config.strategy_id),
        "base_account_id": str(config.base_account_id),
        "execution_instrument_id": str(config.execution_instrument_id),
        "instrument_type": config.instrument_type.value,
        "instrument_id": str(config.instrument_id),
        "source": config.source,
        "timeframe": config.timeframe,
        "quote_source": config.quote_source,
        "start_at": _iso(config.start_at),
        "end_at": _iso(config.end_at),
        "initial_cash": str(config.initial_cash),
        "decision_latency_seconds": int(config.decision_latency.total_seconds()),
        "risk_policy": _dataclass_payload(risk_policy),
        "cost_model": _dataclass_payload(cost_model),
    }


def _dataclass_payload(value: RiskPolicy | PaperCostModel) -> dict[str, object]:
    return {key: _json_value(item) for key, item in asdict(value).items()}


def _hash_payload(payload: object) -> str:
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=_json_value)
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def _json_value(value: object) -> object:
    if isinstance(value, datetime):
        return _iso(value)
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, timedelta):
        return int(value.total_seconds())
    if isinstance(value, UUID):
        return str(value)
    return value


def _iso(value: datetime) -> str:
    return _aware_utc(value).isoformat()


def _money(value: Decimal) -> Decimal:
    return value.quantize(_MONEY_QUANTUM)


def _aware_utc(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def _reasons(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item) for item in value]
