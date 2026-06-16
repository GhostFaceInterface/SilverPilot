from __future__ import annotations

from collections import Counter, deque
from datetime import UTC, datetime, timedelta
from decimal import Decimal

from sqlalchemy import desc, select
from sqlalchemy.orm import Session

from app.models import Asset, PaperTrade, PortfolioSnapshot, PriceSnapshot, TradingDecisionRun


def runtime_proof_report(db: Session, *, window_days: int = 30, asset_symbol: str = "XAG_GRAM") -> dict:
    window_days = min(max(window_days, 1), 366)
    now = datetime.now(UTC)
    since = now - timedelta(days=window_days)
    asset = db.execute(select(Asset).where(Asset.symbol == asset_symbol)).scalar_one_or_none()

    trade_stmt = select(PaperTrade).where(PaperTrade.created_at >= since).order_by(PaperTrade.created_at.asc())
    if asset is not None:
        trade_stmt = trade_stmt.where(PaperTrade.asset_id == asset.id)
    trades = list(db.execute(trade_stmt).scalars().all())

    realized_pnl, gross_buy, wins, closed = _fifo_trade_stats(trades)
    snapshots = _portfolio_snapshots(db, since=since)
    max_drawdown = _max_drawdown(snapshots)
    latest_snapshot = _latest_price_snapshot(db, asset_id=asset.id if asset is not None else None)
    benchmark = _buy_and_hold_benchmark(trades, latest_snapshot)
    block_distribution = _block_distribution(db, since=since, asset_symbol=asset_symbol)

    expectancy = (realized_pnl / Decimal(closed)) if closed else Decimal("0")
    win_rate = (Decimal(wins) / Decimal(closed)) if closed else Decimal("0")
    return {
        "window_days": window_days,
        "asset_symbol": asset_symbol,
        "mode": "paper_proof",
        "real_money_enabled": False,
        "trade_count": len(trades),
        "closed_trade_count": closed,
        "net_pnl": realized_pnl,
        "max_drawdown": max_drawdown,
        "win_rate": win_rate,
        "expectancy": expectancy,
        "fee_spread_adjusted_performance": {
            "realized_pnl": realized_pnl,
            "gross_buy_notional": gross_buy,
            "return_percent": (realized_pnl / gross_buy * Decimal("100")) if gross_buy > 0 else Decimal("0"),
        },
        "buy_and_hold_benchmark": benchmark,
        "block_reason_distribution": block_distribution,
    }


def _fifo_trade_stats(trades: list[PaperTrade]) -> tuple[Decimal, Decimal, int, int]:
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
    return realized, gross_buy, wins, closed


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
