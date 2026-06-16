from __future__ import annotations

from collections import Counter, deque
from datetime import UTC, datetime, timedelta
from decimal import Decimal

from sqlalchemy import desc, select
from sqlalchemy.orm import Session

from app.models import (
    AccountLedgerEntry,
    AgentMemoryEvent,
    Asset,
    PaperTrade,
    PortfolioSnapshot,
    PriceSnapshot,
    RuntimeHeartbeat,
    TradeIntentRecord,
    TradingDecisionRun,
)


def runtime_proof_report(db: Session, *, window_days: int = 30, asset_symbol: str = "XAG_GRAM") -> dict:
    window_days = min(max(window_days, 1), 366)
    now = datetime.now(UTC)
    since = now - timedelta(days=window_days)
    asset = db.execute(select(Asset).where(Asset.symbol == asset_symbol)).scalar_one_or_none()

    trade_stmt = select(PaperTrade).where(PaperTrade.created_at >= since).order_by(PaperTrade.created_at.asc())
    if asset is not None:
        trade_stmt = trade_stmt.where(PaperTrade.asset_id == asset.id)
    trades = list(db.execute(trade_stmt).scalars().all())

    realized_pnl, gross_buy, wins, closed, open_cost, open_qty = _fifo_trade_stats(trades)
    snapshots = _portfolio_snapshots(db, since=since)
    max_drawdown = _max_drawdown(snapshots)
    latest_snapshot = _latest_price_snapshot(db, asset_id=asset.id if asset is not None else None)
    latest_sell_price = Decimal(str(latest_snapshot.sell_price)) if latest_snapshot is not None else Decimal("0")
    unrealized_pnl = (open_qty * latest_sell_price) - open_cost if latest_snapshot is not None else Decimal("0")
    net_pnl = realized_pnl + unrealized_pnl
    benchmark = _buy_and_hold_benchmark(trades, latest_snapshot)
    block_distribution = _block_distribution(db, since=since, asset_symbol=asset_symbol)
    skipped_execution_distribution = _skipped_execution_distribution(db, since=since, asset_symbol=asset_symbol)
    audit_chain = _audit_chain_summary(db, trades=trades, since=since, asset_symbol=asset_symbol)
    acceptance_gate = _acceptance_gate(db, since=now - timedelta(hours=48), audit_chain=audit_chain)

    expectancy = (realized_pnl / Decimal(closed)) if closed else Decimal("0")
    win_rate = (Decimal(wins) / Decimal(closed)) if closed else Decimal("0")
    return {
        "window_days": window_days,
        "asset_symbol": asset_symbol,
        "mode": "paper_proof",
        "real_money_enabled": False,
        "trade_count": len(trades),
        "closed_trade_count": closed,
        "net_pnl": net_pnl,
        "realized_pnl": realized_pnl,
        "unrealized_pnl": unrealized_pnl,
        "max_drawdown": max_drawdown,
        "win_rate": win_rate,
        "expectancy": expectancy,
        "fee_spread_adjusted_performance": {
            "realized_pnl": realized_pnl,
            "unrealized_pnl": unrealized_pnl,
            "net_pnl": net_pnl,
            "gross_buy_notional": gross_buy,
            "return_percent": (net_pnl / gross_buy * Decimal("100")) if gross_buy > 0 else Decimal("0"),
        },
        "buy_and_hold_benchmark": benchmark,
        "block_reason_distribution": block_distribution,
        "skipped_execution_distribution": skipped_execution_distribution,
        "audit_chain_summary": audit_chain,
        "acceptance_gate": acceptance_gate,
    }


def _fifo_trade_stats(trades: list[PaperTrade]) -> tuple[Decimal, Decimal, int, int, Decimal, Decimal]:
    lots: deque[tuple[Decimal, Decimal]] = deque()
    realized = Decimal("0")
    gross_buy = Decimal("0")
    wins = 0
    closed = 0
    for trade in trades:
        quantity = Decimal(str(trade.quantity))
        if quantity <= 0:
            continue
        if trade.action == "paper_buy":
            cost_per_unit = Decimal(str(trade.net_amount)) / quantity
            lots.append((quantity, cost_per_unit))
            gross_buy += Decimal(str(trade.net_amount))
        elif trade.action == "paper_sell":
            remaining = quantity
            proceeds_per_unit = Decimal(str(trade.net_amount)) / quantity
            trade_pnl = Decimal("0")
            while remaining > 0 and lots:
                lot_qty, lot_cost = lots.popleft()
                matched = min(remaining, lot_qty)
                trade_pnl += (proceeds_per_unit - lot_cost) * matched
                remaining -= matched
                if lot_qty > matched:
                    lots.appendleft((lot_qty - matched, lot_cost))
            realized += trade_pnl
            closed += 1
            if trade_pnl > 0:
                wins += 1
    open_qty = sum((lot_qty for lot_qty, _lot_cost in lots), Decimal("0"))
    open_cost = sum((lot_qty * lot_cost for lot_qty, lot_cost in lots), Decimal("0"))
    return realized, gross_buy, wins, closed, open_cost, open_qty


def _portfolio_snapshots(db: Session, *, since: datetime) -> list[PortfolioSnapshot]:
    return list(
        db.execute(
            select(PortfolioSnapshot)
            .where(PortfolioSnapshot.observed_at >= since)
            .order_by(PortfolioSnapshot.observed_at)
        )
        .scalars()
        .all()
    )


def _max_drawdown(snapshots: list[PortfolioSnapshot]) -> Decimal:
    peak: Decimal | None = None
    max_dd = Decimal("0")
    for snapshot in snapshots:
        value = Decimal(str(snapshot.portfolio_value))
        peak = value if peak is None else max(peak, value)
        if peak > 0:
            drawdown = (peak - value) / peak
            max_dd = max(max_dd, drawdown)
    return max_dd


def _latest_price_snapshot(db: Session, *, asset_id: int | None) -> PriceSnapshot | None:
    stmt = select(PriceSnapshot).order_by(desc(PriceSnapshot.observed_at), desc(PriceSnapshot.id)).limit(1)
    if asset_id is not None:
        stmt = stmt.where(PriceSnapshot.asset_id == asset_id)
    return db.execute(stmt).scalar_one_or_none()


def _buy_and_hold_benchmark(trades: list[PaperTrade], latest_snapshot: PriceSnapshot | None) -> dict:
    buy_trades = [trade for trade in trades if trade.action == "paper_buy"]
    invested = sum((Decimal(str(trade.net_amount)) for trade in buy_trades), Decimal("0"))
    quantity = sum((Decimal(str(trade.quantity)) for trade in buy_trades), Decimal("0"))
    sell_price = Decimal(str(latest_snapshot.sell_price)) if latest_snapshot is not None else Decimal("0")
    current_value = quantity * sell_price
    pnl = current_value - invested
    return {
        "invested": invested,
        "quantity": quantity,
        "latest_sell_price": sell_price if latest_snapshot is not None else None,
        "current_value": current_value,
        "pnl": pnl,
        "return_percent": (pnl / invested * Decimal("100")) if invested > 0 else Decimal("0"),
    }


def _block_distribution(db: Session, *, since: datetime, asset_symbol: str) -> dict[str, int]:
    rows = (
        db.execute(
            select(TradingDecisionRun.reason_code)
            .where(TradingDecisionRun.asset_symbol == asset_symbol)
            .where(TradingDecisionRun.started_at >= since)
            .where(TradingDecisionRun.action == "HOLD")
        )
        .scalars()
        .all()
    )
    return dict(Counter(reason or "UNKNOWN" for reason in rows))


def _skipped_execution_distribution(db: Session, *, since: datetime, asset_symbol: str) -> dict[str, int]:
    rows = (
        db.execute(
            select(TradingDecisionRun.execution_result_json)
            .where(TradingDecisionRun.asset_symbol == asset_symbol)
            .where(TradingDecisionRun.started_at >= since)
        )
        .scalars()
        .all()
    )
    reasons = []
    for execution in rows:
        execution = execution or {}
        if execution.get("status") == "executed":
            continue
        reasons.append(execution.get("skipped_reason") or execution.get("status") or "UNKNOWN")
    return dict(Counter(reasons))


def _audit_chain_summary(
    db: Session, *, trades: list[PaperTrade], since: datetime, asset_symbol: str
) -> dict[str, int]:
    trade_ids = [trade.id for trade in trades]
    intent_ids = [trade.trade_intent_id for trade in trades if trade.trade_intent_id is not None]
    signal_ids = (
        [
            intent.signal_id
            for intent in db.execute(select(TradeIntentRecord).where(TradeIntentRecord.id.in_(intent_ids)))
            .scalars()
            .all()
            if intent.signal_id is not None
        ]
        if intent_ids
        else []
    )
    runs_by_signal = (
        set(
            db.execute(select(TradingDecisionRun.signal_id).where(TradingDecisionRun.signal_id.in_(signal_ids)))
            .scalars()
            .all()
        )
        if signal_ids
        else set()
    )
    ledger_trade_ids = (
        set(
            db.execute(
                select(AccountLedgerEntry.paper_trade_id).where(AccountLedgerEntry.paper_trade_id.in_(trade_ids))
            )
            .scalars()
            .all()
        )
        if trade_ids
        else set()
    )
    decision_runs = (
        db.execute(
            select(TradingDecisionRun)
            .where(TradingDecisionRun.asset_symbol == asset_symbol)
            .where(TradingDecisionRun.started_at >= since)
        )
        .scalars()
        .all()
    )

    return {
        "decision_run_count": len(decision_runs),
        "paper_trade_count": len(trades),
        "missing_trade_intent_fk": sum(1 for trade in trades if trade.trade_intent_id is None),
        "missing_risk_decision_fk": sum(1 for trade in trades if trade.risk_decision_id is None),
        "missing_ledger_entry": sum(1 for trade in trades if trade.id not in ledger_trade_ids),
        "missing_decision_run_fk": sum(
            1
            for intent in db.execute(select(TradeIntentRecord).where(TradeIntentRecord.id.in_(intent_ids)))
            .scalars()
            .all()
            if intent.trading_decision_run_id is None
        )
        if intent_ids
        else 0,
        "missing_decision_run_for_signal": sum(1 for signal_id in signal_ids if signal_id not in runs_by_signal),
    }


def _acceptance_gate(db: Session, *, since: datetime, audit_chain: dict[str, int]) -> dict:
    critical_reasons = {
        "SOURCE_DIVERGENCE_BLOCK",
        "SOURCE_DIVERGENCE_STALE_DATA",
        "DAILY_BAR_DELAYED",
        "ENTRY_TIMEFRAME_STALE",
        "EXECUTION_TIMEFRAME_STALE",
        "PORTFOLIO_NOT_FOUND",
        "ASSET_NOT_FOUND",
        "PRICE_SNAPSHOT_MISSING",
        "BLOCKED_CONFIG_INVALID",
    }
    critical_block = db.execute(
        select(TradingDecisionRun.id)
        .where(TradingDecisionRun.started_at >= since)
        .where(TradingDecisionRun.action == "HOLD")
        .where(TradingDecisionRun.reason_code.in_(critical_reasons))
        .limit(1)
    ).scalar_one_or_none()
    stale_execution = db.execute(
        select(TradingDecisionRun.id)
        .where(TradingDecisionRun.started_at >= since)
        .where(TradingDecisionRun.reason_code == "EXECUTION_TIMEFRAME_STALE")
        .limit(1)
    ).scalar_one_or_none()
    non_executed_action_runs = (
        db.execute(
            select(TradingDecisionRun.execution_result_json)
            .where(TradingDecisionRun.started_at >= since)
            .where(TradingDecisionRun.action.in_(("BUY", "SELL")))
        )
        .scalars()
        .all()
    )
    non_executed_action_distribution = Counter()
    for execution in non_executed_action_runs:
        execution = execution or {}
        if execution.get("status") == "executed":
            continue
        non_executed_action_distribution[execution.get("skipped_reason") or execution.get("status") or "UNKNOWN"] += 1
    now = datetime.now(UTC)
    overdue = db.execute(select(RuntimeHeartbeat)).scalars().all()
    heartbeat_overdue = [
        row.component for row in overdue if row.expected_next_at is not None and _aware(row.expected_next_at) < now
    ]
    latest_hermes = db.execute(
        select(AgentMemoryEvent)
        .where(AgentMemoryEvent.agent_name == "hermes-agent")
        .where(AgentMemoryEvent.event_type == "hermes_sentiment")
        .order_by(AgentMemoryEvent.created_at.desc(), AgentMemoryEvent.id.desc())
        .limit(1)
    ).scalar_one_or_none()
    hermes_degraded = bool(
        latest_hermes
        and (latest_hermes.value_json or {}).get("llm_status") in {"degraded", "fallback"}
        and _aware(latest_hermes.created_at) >= since
    )
    audit_gaps = sum(value for key, value in audit_chain.items() if key.startswith("missing_"))
    blockers = {
        "critical_block_48h": critical_block is not None,
        "stale_execution_data_48h": stale_execution is not None,
        "heartbeat_overdue": bool(heartbeat_overdue),
        "hermes_degraded_48h": hermes_degraded,
        "audit_chain_gaps": audit_gaps > 0,
        "non_executed_actions_48h": bool(non_executed_action_distribution),
    }
    return {
        **blockers,
        "heartbeat_overdue_components": heartbeat_overdue,
        "non_executed_action_distribution": dict(non_executed_action_distribution),
        "paper_mode_eligible": not any(blockers.values()),
        "real_money_eligible": False,
    }


def _aware(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)
