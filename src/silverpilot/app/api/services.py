from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from math import ceil
from typing import Any, TypeVar
from uuid import UUID

from sqlalchemy import Select, func, select
from sqlalchemy.orm import Session, joinedload

from silverpilot.app.api.schemas import (
    AccountDashboardReportResponse,
    AccountHealthReportResponse,
    AccountResponse,
    BacktestRunResponse,
    BacktestRunSummaryResponse,
    BankResponse,
    ExecutionInstrumentResponse,
    IndicatorSnapshotResponse,
    MarketRegimeSnapshotResponse,
    PageMeta,
    PaginatedResponse,
    PaperTradeResponse,
    PnlReportResponse,
    PortfolioReportResponse,
    PositionResponse,
    PositionValuationResponse,
    PriceQuoteResponse,
    ReportResponse,
    RiskReportResponse,
    WalletResponse,
)
from silverpilot.app.db.models import (
    BacktestRunModel,
    BankModel,
    ExecutionInstrumentModel,
    ExecutionPremiumSnapshotModel,
    IndicatorSnapshotModel,
    MarketRegimeSnapshotModel,
    PaperTradeModel,
    PositionModel,
    PriceQuoteModel,
    RiskDecisionModel,
    TradeIntentModel,
    VirtualAccountModel,
    WalletModel,
)

T = TypeVar("T")
_MONEY_QUANTUM = Decimal("0.00000001")
_INDICATIVE_PRICE_NOTE = (
    "Portfolio valuation uses public indicative bank buy quotes; executable parity is not "
    "guaranteed until manually verified against authenticated order screens."
)


@dataclass(frozen=True)
class Pagination:
    page: int
    page_size: int

    @property
    def offset(self) -> int:
        return (self.page - 1) * self.page_size


class ApiQueryService:
    def __init__(self, session: Session) -> None:
        self._session = session

    def list_accounts(
        self,
        pagination: Pagination,
        status: str | None = None,
    ) -> PaginatedResponse[AccountResponse]:
        query = (
            select(VirtualAccountModel)
            .options(
                joinedload(VirtualAccountModel.base_currency),
                joinedload(VirtualAccountModel.execution_venue),
            )
            .order_by(VirtualAccountModel.created_at.desc(), VirtualAccountModel.id)
        )
        if status is not None:
            query = query.where(VirtualAccountModel.status == status)
        accounts, total = self._page(query, pagination)
        return _paginated([_account_response(account) for account in accounts], pagination, total)

    def get_account(self, account_id: UUID) -> AccountResponse | None:
        account = self._session.scalar(
            select(VirtualAccountModel)
            .options(
                joinedload(VirtualAccountModel.base_currency),
                joinedload(VirtualAccountModel.execution_venue),
            )
            .where(VirtualAccountModel.id == account_id)
        )
        return _account_response(account) if account else None

    def list_wallets(self, account_id: UUID) -> list[WalletResponse] | None:
        if self._session.get(VirtualAccountModel, account_id) is None:
            return None
        wallets = self._session.scalars(
            select(WalletModel)
            .options(joinedload(WalletModel.currency))
            .where(WalletModel.virtual_account_id == account_id)
            .order_by(WalletModel.created_at.desc(), WalletModel.id)
        ).all()
        return [_wallet_response(wallet) for wallet in wallets]

    def list_banks(
        self,
        pagination: Pagination,
        status: str | None = None,
    ) -> PaginatedResponse[BankResponse]:
        query = select(BankModel).order_by(BankModel.created_at.desc(), BankModel.id)
        if status is not None:
            query = query.where(BankModel.status == status)
        banks, total = self._page(query, pagination)
        return _paginated([_bank_response(bank) for bank in banks], pagination, total)

    def list_execution_instruments(
        self,
        pagination: Pagination,
        status: str | None = None,
    ) -> PaginatedResponse[ExecutionInstrumentResponse]:
        query = (
            select(ExecutionInstrumentModel)
            .options(
                joinedload(ExecutionInstrumentModel.execution_venue),
                joinedload(ExecutionInstrumentModel.metal),
                joinedload(ExecutionInstrumentModel.currency),
                joinedload(ExecutionInstrumentModel.unit),
            )
            .order_by(ExecutionInstrumentModel.created_at.desc(), ExecutionInstrumentModel.id)
        )
        if status is not None:
            query = query.where(ExecutionInstrumentModel.status == status)
        instruments, total = self._page(query, pagination)
        return _paginated(
            [_execution_instrument_response(instrument) for instrument in instruments],
            pagination,
            total,
        )

    def list_latest_prices(
        self,
        pagination: Pagination,
        bank_instrument_id: UUID | None = None,
    ) -> PaginatedResponse[PriceQuoteResponse]:
        query = select(PriceQuoteModel).order_by(
            PriceQuoteModel.observed_at.desc(), PriceQuoteModel.id
        )
        if bank_instrument_id is not None:
            query = query.where(PriceQuoteModel.bank_instrument_id == bank_instrument_id)
        prices, total = self._page(query, pagination)
        return _paginated([_price_response(price) for price in prices], pagination, total)

    def list_latest_indicators(
        self,
        pagination: Pagination,
        instrument_type: str | None = None,
        instrument_id: UUID | None = None,
        timeframe: str | None = None,
        indicator_name: str | None = None,
    ) -> PaginatedResponse[IndicatorSnapshotResponse]:
        query = select(IndicatorSnapshotModel).order_by(
            IndicatorSnapshotModel.source_bar_end_at.desc(), IndicatorSnapshotModel.id
        )
        query = _apply_market_filters(
            query,
            IndicatorSnapshotModel,
            instrument_type=instrument_type,
            instrument_id=instrument_id,
            timeframe=timeframe,
        )
        if indicator_name is not None:
            query = query.where(IndicatorSnapshotModel.indicator_name == indicator_name)
        indicators, total = self._page(query, pagination)
        return _paginated(
            [_indicator_response(indicator) for indicator in indicators],
            pagination,
            total,
        )

    def list_latest_regimes(
        self,
        pagination: Pagination,
        instrument_type: str | None = None,
        instrument_id: UUID | None = None,
        timeframe: str | None = None,
    ) -> PaginatedResponse[MarketRegimeSnapshotResponse]:
        query = select(MarketRegimeSnapshotModel).order_by(
            MarketRegimeSnapshotModel.source_bar_end_at.desc(), MarketRegimeSnapshotModel.id
        )
        query = _apply_market_filters(
            query,
            MarketRegimeSnapshotModel,
            instrument_type=instrument_type,
            instrument_id=instrument_id,
            timeframe=timeframe,
        )
        regimes, total = self._page(query, pagination)
        return _paginated([_regime_response(regime) for regime in regimes], pagination, total)

    def list_trades(
        self,
        pagination: Pagination,
        account_id: UUID | None = None,
    ) -> PaginatedResponse[PaperTradeResponse]:
        query = select(PaperTradeModel).order_by(
            PaperTradeModel.executed_at.desc(),
            PaperTradeModel.id,
        )
        if account_id is not None:
            query = query.where(PaperTradeModel.account_id == account_id)
        trades, total = self._page(query, pagination)
        return _paginated([_trade_response(trade) for trade in trades], pagination, total)

    def list_positions(
        self,
        pagination: Pagination,
        account_id: UUID | None = None,
    ) -> PaginatedResponse[PositionResponse]:
        query = select(PositionModel).order_by(PositionModel.created_at.desc(), PositionModel.id)
        if account_id is not None:
            query = query.where(PositionModel.account_id == account_id)
        positions, total = self._page(query, pagination)
        return _paginated(
            [_position_response(position) for position in positions],
            pagination,
            total,
        )

    def list_backtests(
        self,
        pagination: Pagination,
    ) -> PaginatedResponse[BacktestRunSummaryResponse]:
        query = select(BacktestRunModel).order_by(
            BacktestRunModel.started_at.desc(),
            BacktestRunModel.id,
        )
        runs, total = self._page(query, pagination)
        return _paginated([_backtest_summary_response(run) for run in runs], pagination, total)

    def get_backtest(self, run_id: UUID) -> BacktestRunResponse | None:
        run = self._session.get(BacktestRunModel, run_id)
        return _backtest_response(run) if run else None

    def get_backtest_report(self, run_id: UUID) -> ReportResponse | None:
        run = self._session.get(BacktestRunModel, run_id)
        if run is None:
            return None
        return ReportResponse(id=run.id, report_type="backtest", payload=run.report_json)

    def get_account_dashboard_report(
        self,
        *,
        account_id: UUID,
        captured_at: datetime | None = None,
    ) -> AccountDashboardReportResponse | None:
        account = self._session.scalar(
            select(VirtualAccountModel)
            .options(
                joinedload(VirtualAccountModel.base_currency),
                joinedload(VirtualAccountModel.execution_venue),
            )
            .where(VirtualAccountModel.id == account_id)
        )
        if account is None:
            return None

        captured = _aware_datetime(captured_at or datetime.now(UTC))
        wallets = self._session.scalars(
            select(WalletModel)
            .options(joinedload(WalletModel.currency))
            .where(WalletModel.virtual_account_id == account.id)
        ).all()
        positions = self._session.scalars(
            select(PositionModel).where(PositionModel.account_id == account.id)
        ).all()
        trades = self._session.scalars(
            select(PaperTradeModel)
            .options(joinedload(PaperTradeModel.quote))
            .where(PaperTradeModel.account_id == account.id)
            .order_by(PaperTradeModel.executed_at.desc(), PaperTradeModel.id)
        ).all()
        risk_decisions = self._session.scalars(
            select(RiskDecisionModel)
            .join(TradeIntentModel, RiskDecisionModel.trade_intent_id == TradeIntentModel.id)
            .where(TradeIntentModel.account_id == account.id)
            .order_by(RiskDecisionModel.evaluated_at.desc(), RiskDecisionModel.id)
        ).all()
        latest_quotes = self._latest_quotes_by_bank_instrument(
            [position.bank_instrument_id for position in positions],
            captured_at=captured,
        )

        portfolio = _portfolio_report(
            account=account,
            wallets=wallets,
            positions=positions,
            latest_quotes=latest_quotes,
            captured_at=captured,
        )
        pnl = _pnl_report(account_id=account.id, trades=trades, portfolio=portfolio)
        risk = _risk_report(
            account_id=account.id,
            risk_decisions=risk_decisions,
            pending_intent_count=self._pending_intent_count(account.id),
            latest_premium_snapshot=self._latest_premium_snapshot(
                [decision.execution_instrument_id for decision in risk_decisions]
            ),
        )
        health = _account_health_report(
            account=account,
            wallets=wallets,
            positions=positions,
            portfolio=portfolio,
            trades=trades,
            risk=risk,
        )
        return AccountDashboardReportResponse(
            account=_account_response(account),
            portfolio=portfolio,
            pnl=pnl,
            risk=risk,
            health=health,
        )

    def _page(
        self,
        query: Select[tuple[T]],
        pagination: Pagination,
    ) -> tuple[Sequence[T], int]:
        total = self._session.scalar(
            select(func.count()).select_from(query.order_by(None).subquery())
        )
        rows = self._session.scalars(
            query.limit(pagination.page_size).offset(pagination.offset)
        ).all()
        return rows, int(total or 0)

    def _latest_quotes_by_bank_instrument(
        self,
        bank_instrument_ids: list[UUID],
        *,
        captured_at: datetime,
    ) -> dict[UUID, PriceQuoteModel]:
        if not bank_instrument_ids:
            return {}
        quotes = self._session.scalars(
            select(PriceQuoteModel)
            .where(
                PriceQuoteModel.bank_instrument_id.in_(bank_instrument_ids),
                PriceQuoteModel.observed_at <= captured_at,
            )
            .order_by(
                PriceQuoteModel.bank_instrument_id,
                PriceQuoteModel.observed_at.desc(),
                PriceQuoteModel.fetched_at.desc(),
                PriceQuoteModel.id,
            )
        ).all()
        latest: dict[UUID, PriceQuoteModel] = {}
        for quote in quotes:
            latest.setdefault(quote.bank_instrument_id, quote)
        return latest

    def _pending_intent_count(self, account_id: UUID) -> int:
        count = self._session.scalar(
            select(func.count())
            .select_from(TradeIntentModel)
            .where(
                TradeIntentModel.account_id == account_id,
                TradeIntentModel.status == "pending_risk",
            )
        )
        return int(count or 0)

    def _latest_premium_snapshot(
        self,
        execution_instrument_ids: Sequence[UUID | None],
    ) -> ExecutionPremiumSnapshotModel | None:
        ids = [instrument_id for instrument_id in execution_instrument_ids if instrument_id]
        if not ids:
            return None
        return self._session.scalar(
            select(ExecutionPremiumSnapshotModel)
            .where(ExecutionPremiumSnapshotModel.execution_instrument_id.in_(ids))
            .order_by(
                ExecutionPremiumSnapshotModel.captured_at.desc(),
                ExecutionPremiumSnapshotModel.id,
            )
        )


def _apply_market_filters(  # noqa: UP047
    query: Select[tuple[T]],
    model: type[Any],
    *,
    instrument_type: str | None,
    instrument_id: UUID | None,
    timeframe: str | None,
) -> Select[tuple[T]]:
    if instrument_type is not None:
        query = query.where(model.instrument_type == instrument_type)
    if instrument_id is not None:
        query = query.where(model.instrument_id == instrument_id)
    if timeframe is not None:
        query = query.where(model.timeframe == timeframe)
    return query


def _paginated(  # noqa: UP047
    items: list[T],
    pagination: Pagination,
    total: int,
) -> PaginatedResponse[T]:
    return PaginatedResponse(
        items=items,
        meta=PageMeta(
            page=pagination.page,
            page_size=pagination.page_size,
            total=total,
            pages=ceil(total / pagination.page_size) if total else 0,
        ),
    )


def _account_response(account: VirtualAccountModel) -> AccountResponse:
    return AccountResponse(
        id=account.id,
        user_id=account.user_id,
        name=account.name,
        base_currency_id=account.base_currency_id,
        base_currency_code=account.base_currency.code,
        execution_venue_id=account.execution_venue_id,
        execution_venue_code=account.execution_venue.code,
        starting_balance=account.starting_balance,
        status=account.status,
        created_at=account.created_at,
    )


def _wallet_response(wallet: WalletModel) -> WalletResponse:
    return WalletResponse(
        id=wallet.id,
        account_id=wallet.virtual_account_id,
        currency_id=wallet.currency_id,
        currency_code=wallet.currency.code,
        available_amount=wallet.available_amount,
        reserved_amount=wallet.reserved_amount,
        created_at=wallet.created_at,
    )


def _bank_response(bank: BankModel) -> BankResponse:
    return BankResponse(
        id=bank.id,
        code=bank.code,
        name=bank.name,
        country_code=bank.country_code,
        status=bank.status,
        source_policy=bank.source_policy,
        created_at=bank.created_at,
    )


def _execution_instrument_response(
    instrument: ExecutionInstrumentModel,
) -> ExecutionInstrumentResponse:
    return ExecutionInstrumentResponse(
        id=instrument.id,
        execution_venue_id=instrument.execution_venue_id,
        execution_venue_code=instrument.execution_venue.code,
        bank_instrument_id=instrument.bank_instrument_id,
        symbol=instrument.symbol,
        metal_code=instrument.metal.code,
        currency_code=instrument.currency.code,
        unit_code=instrument.unit.code,
        status=instrument.status,
        created_at=instrument.created_at,
    )


def _price_response(price: PriceQuoteModel) -> PriceQuoteResponse:
    return PriceQuoteResponse(
        id=price.id,
        bank_instrument_id=price.bank_instrument_id,
        bank_buy_price=price.bank_buy_price,
        bank_sell_price=price.bank_sell_price,
        observed_at=price.observed_at,
        fetched_at=price.fetched_at,
        source=price.source,
        freshness_status=price.freshness_status,
    )


def _indicator_response(indicator: IndicatorSnapshotModel) -> IndicatorSnapshotResponse:
    return IndicatorSnapshotResponse(
        id=indicator.id,
        instrument_type=indicator.instrument_type,
        instrument_id=indicator.instrument_id,
        source=indicator.source,
        timeframe=indicator.timeframe,
        indicator_name=indicator.indicator_name,
        parameters=indicator.parameters,
        value=indicator.value,
        calculated_at=indicator.calculated_at,
        source_bar_end_at=indicator.source_bar_end_at,
    )


def _regime_response(regime: MarketRegimeSnapshotModel) -> MarketRegimeSnapshotResponse:
    return MarketRegimeSnapshotResponse(
        id=regime.id,
        instrument_type=regime.instrument_type,
        instrument_id=regime.instrument_id,
        source=regime.source,
        timeframe=regime.timeframe,
        regime=regime.regime,
        confidence=regime.confidence,
        evidence=regime.evidence,
        config_version=regime.config_version,
        starts_at=regime.starts_at,
        confirmed_at=regime.confirmed_at,
        source_bar_end_at=regime.source_bar_end_at,
    )


def _trade_response(trade: PaperTradeModel) -> PaperTradeResponse:
    return PaperTradeResponse(
        id=trade.id,
        order_id=trade.order_id,
        account_id=trade.account_id,
        execution_instrument_id=trade.execution_instrument_id,
        bank_instrument_id=trade.bank_instrument_id,
        quote_id=trade.quote_id,
        side=trade.side,
        quantity=trade.quantity,
        execution_price=trade.execution_price,
        gross_cash_amount=trade.gross_cash_amount,
        fees=trade.fees,
        taxes=trade.taxes,
        spread_cost=trade.spread_cost,
        net_cash_amount=trade.net_cash_amount,
        realized_pnl=trade.realized_pnl,
        cost_breakdown=trade.cost_breakdown,
        executed_at=trade.executed_at,
    )


def _position_response(position: PositionModel) -> PositionResponse:
    return PositionResponse(
        id=position.id,
        account_id=position.account_id,
        bank_instrument_id=position.bank_instrument_id,
        quantity=position.quantity,
        average_cost=position.average_cost,
        realized_pnl=position.realized_pnl,
        created_at=position.created_at,
    )


def _backtest_summary_response(run: BacktestRunModel) -> BacktestRunSummaryResponse:
    return BacktestRunSummaryResponse(
        id=run.id,
        dataset_snapshot_id=run.dataset_snapshot_id,
        account_id=run.account_id,
        strategy_id=run.strategy_id,
        config_hash=run.config_hash,
        status=run.status,
        started_at=run.started_at,
        completed_at=run.completed_at,
        pnl_after_costs=run.report_json.get("pnl_after_costs"),
        trade_count=run.report_json.get("trade_count"),
        max_drawdown=run.report_json.get("max_drawdown"),
    )


def _backtest_response(run: BacktestRunModel) -> BacktestRunResponse:
    summary = _backtest_summary_response(run)
    return BacktestRunResponse(**summary.model_dump(), report=run.report_json)


def _portfolio_report(
    *,
    account: VirtualAccountModel,
    wallets: Sequence[WalletModel],
    positions: Sequence[PositionModel],
    latest_quotes: dict[UUID, PriceQuoteModel],
    captured_at: datetime,
) -> PortfolioReportResponse:
    base_wallets = [wallet for wallet in wallets if wallet.currency_id == account.base_currency_id]
    cash_available = _sum_money(Decimal(wallet.available_amount) for wallet in base_wallets)
    cash_reserved = _sum_money(Decimal(wallet.reserved_amount) for wallet in base_wallets)

    position_reports = [
        _position_valuation(position, latest_quotes.get(position.bank_instrument_id))
        for position in positions
    ]
    positions_market_value = _sum_money(position.market_value for position in position_reports)
    realized_pnl = _sum_money(position.realized_pnl for position in position_reports)
    unrealized_pnl = _sum_money(position.unrealized_pnl for position in position_reports)
    total_value = _money(cash_available + cash_reserved + positions_market_value)
    net_pnl = _money(total_value - Decimal(account.starting_balance))
    return_pct = (
        (net_pnl / Decimal(account.starting_balance)).quantize(_MONEY_QUANTUM)
        if Decimal(account.starting_balance) > Decimal("0")
        else None
    )
    return PortfolioReportResponse(
        account_id=account.id,
        captured_at=captured_at,
        base_currency_code=account.base_currency.code,
        cash_available=cash_available,
        cash_reserved=cash_reserved,
        positions_market_value=positions_market_value,
        total_value=total_value,
        starting_balance=account.starting_balance,
        realized_pnl=realized_pnl,
        unrealized_pnl=unrealized_pnl,
        net_pnl=net_pnl,
        return_pct=return_pct,
        indicative_pricing_note=_INDICATIVE_PRICE_NOTE,
        positions=position_reports,
    )


def _position_valuation(
    position: PositionModel,
    latest_quote: PriceQuoteModel | None,
) -> PositionValuationResponse:
    quantity = Decimal(position.quantity)
    average_cost = Decimal(position.average_cost)
    cost_basis = _money(quantity * average_cost)
    realized_pnl = _money(Decimal(position.realized_pnl))
    if latest_quote is None:
        market_value = Decimal("0.00000000")
        unrealized_pnl = Decimal("0.00000000")
        latest_bank_buy_price = None
        valuation_status = "missing_quote"
    elif latest_quote.freshness_status != "fresh":
        market_value = Decimal("0.00000000")
        unrealized_pnl = Decimal("0.00000000")
        latest_bank_buy_price = Decimal(latest_quote.bank_buy_price)
        valuation_status = "stale_quote"
    else:
        latest_bank_buy_price = Decimal(latest_quote.bank_buy_price)
        market_value = _money(quantity * latest_bank_buy_price)
        unrealized_pnl = _money(market_value - cost_basis)
        valuation_status = "valued"
    return PositionValuationResponse(
        position_id=position.id,
        bank_instrument_id=position.bank_instrument_id,
        quantity=quantity,
        average_cost=average_cost,
        latest_bank_buy_price=latest_bank_buy_price,
        market_value=market_value,
        cost_basis=cost_basis,
        unrealized_pnl=unrealized_pnl,
        realized_pnl=realized_pnl,
        valuation_status=valuation_status,
    )


def _pnl_report(
    *,
    account_id: UUID,
    trades: Sequence[PaperTradeModel],
    portfolio: PortfolioReportResponse,
) -> PnlReportResponse:
    return PnlReportResponse(
        account_id=account_id,
        gross_trade_cash=_sum_money(Decimal(trade.gross_cash_amount) for trade in trades),
        fees=_sum_money(Decimal(trade.fees) for trade in trades),
        taxes=_sum_money(Decimal(trade.taxes) for trade in trades),
        spread_cost=_sum_money(Decimal(trade.spread_cost) for trade in trades),
        realized_pnl=portfolio.realized_pnl,
        unrealized_pnl=portfolio.unrealized_pnl,
        net_pnl=portfolio.net_pnl,
        trade_count=len(trades),
    )


def _risk_report(
    *,
    account_id: UUID,
    risk_decisions: Sequence[RiskDecisionModel],
    pending_intent_count: int,
    latest_premium_snapshot: ExecutionPremiumSnapshotModel | None = None,
) -> RiskReportResponse:
    decision_counts = {"approve": 0, "reduce": 0, "reject": 0}
    rejection_reasons: dict[str, int] = {}
    for decision in risk_decisions:
        if decision.decision in decision_counts:
            decision_counts[decision.decision] += 1
        if decision.decision == "reject":
            for reason in decision.reasons:
                rejection_reasons[reason] = rejection_reasons.get(reason, 0) + 1
    latest_decision_at = risk_decisions[0].evaluated_at if risk_decisions else None
    return RiskReportResponse(
        account_id=account_id,
        pending_intent_count=pending_intent_count,
        approved_decision_count=decision_counts["approve"],
        reduced_decision_count=decision_counts["reduce"],
        rejected_decision_count=decision_counts["reject"],
        latest_decision_at=latest_decision_at,
        rejection_reasons=rejection_reasons,
        latest_execution_premium_snapshot_id=(
            latest_premium_snapshot.id if latest_premium_snapshot is not None else None
        ),
        latest_execution_premium_status=(
            latest_premium_snapshot.status if latest_premium_snapshot is not None else None
        ),
    )


def _account_health_report(
    *,
    account: VirtualAccountModel,
    wallets: Sequence[WalletModel],
    positions: Sequence[PositionModel],
    portfolio: PortfolioReportResponse,
    trades: Sequence[PaperTradeModel],
    risk: RiskReportResponse,
) -> AccountHealthReportResponse:
    stale_count = sum(
        1 for position in portfolio.positions if position.valuation_status != "valued"
    )
    latest_quote_dates = [
        _aware_datetime(trade.quote.observed_at) for trade in trades if trade.quote is not None
    ]
    latest_quote_at = max(latest_quote_dates) if latest_quote_dates else None
    latest_trade_at = trades[0].executed_at if trades else None
    status = "ok"
    if account.status != "active":
        status = "account_inactive"
    elif stale_count:
        status = "degraded"
    return AccountHealthReportResponse(
        account_id=account.id,
        account_status=account.status,
        wallet_count=len(wallets),
        open_position_count=len(positions),
        stale_position_price_count=stale_count,
        latest_quote_at=latest_quote_at,
        latest_trade_at=latest_trade_at,
        latest_risk_decision_at=risk.latest_decision_at,
        status=status,
    )


def _money(value: Decimal) -> Decimal:
    return value.quantize(_MONEY_QUANTUM)


def _sum_money(values: Iterable[Decimal]) -> Decimal:
    return _money(sum(values, Decimal("0")))


def _aware_datetime(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        return value.replace(tzinfo=UTC)
    return value
