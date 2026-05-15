from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Protocol

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.collectors.service import collector_health
from app.core.config import get_settings
from app.models import Asset, PaperTrade, Portfolio, RawGlobalPrice, RiskDecision
from app.schemas.paper_trading import PaperTradeRequest

CONFIDENCE = Decimal("1.0000")
PERCENT_QUANT = Decimal("0.000001")


@dataclass(frozen=True)
class TradeAmounts:
    quantity: Decimal
    price: Decimal
    gross_amount: Decimal
    net_amount: Decimal


class PositionLike(Protocol):
    quantity: Decimal


class RiskStatusError(Exception):
    pass


def evaluate_paper_trade_risk(
    db: Session,
    *,
    request: PaperTradeRequest,
    portfolio: Portfolio,
    asset: Asset,
    position: PositionLike,
    amounts: TradeAmounts,
) -> RiskDecision:
    settings = get_settings()

    if request.action == "hold":
        return _decision(
            db,
            decision="hold",
            reason_code="HOLD_REQUESTED",
            risk_level="low",
            details={"requested_action": request.action},
        )
    if request.action == "blocked":
        return _decision(
            db,
            decision="blocked",
            reason_code="BLOCKED_REQUESTED",
            risk_level="low",
            details={"requested_action": request.action},
        )

    spread_decision = _spread_block(db, request=request, max_spread_percent=settings.risk_max_spread_percent)
    if spread_decision is not None:
        return spread_decision

    data_decision = _execution_data_block(db, stale_after_minutes=settings.risk_data_stale_after_minutes)
    if data_decision is not None:
        return data_decision

    loss_decision = _loss_limit_block(
        db,
        portfolio_id=portfolio.id,
        asset_id=asset.id,
        max_daily_loss_usd=settings.risk_max_daily_loss_usd,
        max_weekly_loss_usd=settings.risk_max_weekly_loss_usd,
    )
    if loss_decision is not None:
        return loss_decision

    volatility_decision = _volatility_block(
        db,
        asset_id=asset.id,
        max_24h_percent=settings.risk_max_24h_volatility_percent,
        max_7d_percent=settings.risk_max_7d_volatility_percent,
    )
    if volatility_decision is not None:
        return volatility_decision

    fomo_decision = _fomo_block(
        db,
        request=request,
        asset_id=asset.id,
        lookback_minutes=settings.risk_fomo_lookback_minutes,
        max_rise_percent=settings.risk_fomo_rise_percent,
    )
    if fomo_decision is not None:
        return fomo_decision

    expected_gain_decision = _expected_gain_block(
        db,
        request=request,
        amounts=amounts,
        min_expected_net_gain_percent=settings.risk_min_expected_net_gain_percent,
    )
    if expected_gain_decision is not None:
        return expected_gain_decision

    if request.action == "paper_buy" and portfolio.cash_balance < amounts.net_amount:
        return _decision(
            db,
            decision="blocked",
            reason_code="INSUFFICIENT_CASH",
            risk_level="high",
            details={
                "cash_balance": str(portfolio.cash_balance),
                "required_cash": str(amounts.net_amount),
                "asset_symbol": asset.symbol,
            },
        )

    if request.action == "paper_sell" and position.quantity < amounts.quantity:
        return _decision(
            db,
            decision="blocked",
            reason_code="POSITION_LIMIT_REACHED",
            risk_level="high",
            details={
                "available_quantity": str(position.quantity),
                "requested_quantity": str(amounts.quantity),
                "asset_symbol": asset.symbol,
            },
        )

    return _decision(
        db,
        decision="allow",
        reason_code="RISK_CHECK_PASSED",
        risk_level="low",
        details={
            "asset_symbol": asset.symbol,
            "requested_action": request.action,
            "max_spread_percent": str(settings.risk_max_spread_percent),
            "data_stale_after_minutes": settings.risk_data_stale_after_minutes,
            "max_24h_volatility_percent": str(settings.risk_max_24h_volatility_percent),
            "max_7d_volatility_percent": str(settings.risk_max_7d_volatility_percent),
            "fomo_lookback_minutes": settings.risk_fomo_lookback_minutes,
            "fomo_rise_percent": str(settings.risk_fomo_rise_percent),
            "max_daily_loss_usd": str(settings.risk_max_daily_loss_usd),
            "max_weekly_loss_usd": str(settings.risk_max_weekly_loss_usd),
        },
    )


def risk_policy_status(
    db: Session,
    *,
    portfolio_name: str = "default-paper",
    asset_symbol: str = "XAG",
) -> dict:
    settings = get_settings()
    portfolio = db.execute(select(Portfolio).where(Portfolio.name == portfolio_name)).scalar_one_or_none()
    if portfolio is None:
        raise RiskStatusError("Portfolio not found")
    asset = db.execute(select(Asset).where(Asset.symbol == asset_symbol)).scalar_one_or_none()
    if asset is None:
        raise RiskStatusError("Asset not found")

    now = datetime.now(UTC)
    daily_loss = _realized_loss_since(db, portfolio_id=portfolio.id, asset_id=asset.id, since=now - timedelta(days=1))
    weekly_loss = _realized_loss_since(db, portfolio_id=portfolio.id, asset_id=asset.id, since=now - timedelta(days=7))
    volatility_24h = _global_price_range_percent(db, asset_id=asset.id, since=now - timedelta(hours=24))
    volatility_7d = _global_price_range_percent(db, asset_id=asset.id, since=now - timedelta(days=7))
    fomo_rise = _global_price_rise_percent(
        db,
        asset_id=asset.id,
        since=now - timedelta(minutes=settings.risk_fomo_lookback_minutes),
    )

    would_block_now = []
    if daily_loss >= settings.risk_max_daily_loss_usd:
        would_block_now.append(
            {
                "reason_code": "DAILY_LOSS_LIMIT_REACHED",
                "risk_level": "high",
                "metric": str(daily_loss),
                "threshold": str(settings.risk_max_daily_loss_usd),
            }
        )
    if weekly_loss >= settings.risk_max_weekly_loss_usd:
        would_block_now.append(
            {
                "reason_code": "WEEKLY_LOSS_LIMIT_REACHED",
                "risk_level": "high",
                "metric": str(weekly_loss),
                "threshold": str(settings.risk_max_weekly_loss_usd),
            }
        )
    if volatility_24h is not None and volatility_24h > settings.risk_max_24h_volatility_percent:
        would_block_now.append(
            {
                "reason_code": "VOLATILITY_TOO_HIGH",
                "risk_level": "high",
                "metric": str(volatility_24h),
                "threshold": str(settings.risk_max_24h_volatility_percent),
                "window_hours": 24,
            }
        )
    if volatility_7d is not None and volatility_7d > settings.risk_max_7d_volatility_percent:
        would_block_now.append(
            {
                "reason_code": "VOLATILITY_TOO_HIGH",
                "risk_level": "high",
                "metric": str(volatility_7d),
                "threshold": str(settings.risk_max_7d_volatility_percent),
                "window_hours": 168,
            }
        )
    if fomo_rise is not None and fomo_rise > settings.risk_fomo_rise_percent:
        would_block_now.append(
            {
                "reason_code": "FOMO_RISK",
                "risk_level": "medium",
                "metric": str(fomo_rise),
                "threshold": str(settings.risk_fomo_rise_percent),
                "lookback_minutes": settings.risk_fomo_lookback_minutes,
            }
        )

    return {
        "portfolio_name": portfolio.name,
        "asset_symbol": asset.symbol,
        "thresholds": {
            "data_stale_after_minutes": settings.risk_data_stale_after_minutes,
            "max_spread_percent": settings.risk_max_spread_percent,
            "max_24h_volatility_percent": settings.risk_max_24h_volatility_percent,
            "max_7d_volatility_percent": settings.risk_max_7d_volatility_percent,
            "fomo_lookback_minutes": settings.risk_fomo_lookback_minutes,
            "fomo_rise_percent": settings.risk_fomo_rise_percent,
            "max_daily_loss_usd": settings.risk_max_daily_loss_usd,
            "max_weekly_loss_usd": settings.risk_max_weekly_loss_usd,
            "min_expected_net_gain_percent": settings.risk_min_expected_net_gain_percent,
        },
        "current_metrics": {
            "global_xag_volatility_24h_percent": volatility_24h,
            "global_xag_volatility_7d_percent": volatility_7d,
            "fomo_rise_percent": fomo_rise,
            "daily_realized_loss_usd": daily_loss,
            "weekly_realized_loss_usd": weekly_loss,
        },
        "would_block_now": would_block_now,
        "recent_decisions": _recent_risk_decision_counts(db, since=now - timedelta(hours=24)),
    }


def _spread_block(db: Session, *, request: PaperTradeRequest, max_spread_percent: Decimal) -> RiskDecision | None:
    if request.buy_price <= 0 or request.sell_price <= 0:
        return None
    mid_price = (request.buy_price + request.sell_price) / Decimal("2")
    if mid_price <= 0:
        return None
    spread_percent = ((request.buy_price - request.sell_price) / mid_price) * Decimal("100")
    if spread_percent <= max_spread_percent:
        return None
    return _decision(
        db,
        decision="blocked",
        reason_code="SPREAD_TOO_HIGH",
        risk_level="high",
        details={
            "spread_percent": str(spread_percent.quantize(Decimal("0.000001"))),
            "max_spread_percent": str(max_spread_percent),
        },
    )


def _execution_data_block(db: Session, *, stale_after_minutes: int) -> RiskDecision | None:
    health = collector_health(db, stale_after_minutes=stale_after_minutes)
    execution_status = health["execution_critical_status"]
    if execution_status not in {"blocked", "stale"}:
        return None

    execution_critical = health["execution_critical"]
    reason_code = "MISSING_DATA" if execution_status == "blocked" else "STALE_DATA"
    return _decision(
        db,
        decision="blocked",
        reason_code=reason_code,
        risk_level="high",
        details={
            "execution_critical_status": execution_status,
            "bank_price": execution_critical["bank_price"],
            "global_xag_usd": execution_critical["global_xag_usd"],
            "usd_try": execution_critical["usd_try"],
            "stale_after_minutes": stale_after_minutes,
        },
    )


def _loss_limit_block(
    db: Session,
    *,
    portfolio_id: int,
    asset_id: int,
    max_daily_loss_usd: Decimal,
    max_weekly_loss_usd: Decimal,
) -> RiskDecision | None:
    now = datetime.now(UTC)
    daily_loss = _realized_loss_since(db, portfolio_id=portfolio_id, asset_id=asset_id, since=now - timedelta(days=1))
    if daily_loss >= max_daily_loss_usd:
        return _decision(
            db,
            decision="blocked",
            reason_code="DAILY_LOSS_LIMIT_REACHED",
            risk_level="high",
            details={
                "realized_loss_usd": str(daily_loss),
                "max_daily_loss_usd": str(max_daily_loss_usd),
                "window_hours": 24,
            },
        )

    weekly_loss = _realized_loss_since(db, portfolio_id=portfolio_id, asset_id=asset_id, since=now - timedelta(days=7))
    if weekly_loss >= max_weekly_loss_usd:
        return _decision(
            db,
            decision="blocked",
            reason_code="WEEKLY_LOSS_LIMIT_REACHED",
            risk_level="high",
            details={
                "realized_loss_usd": str(weekly_loss),
                "max_weekly_loss_usd": str(max_weekly_loss_usd),
                "window_days": 7,
            },
        )
    return None


def _volatility_block(
    db: Session,
    *,
    asset_id: int,
    max_24h_percent: Decimal,
    max_7d_percent: Decimal,
) -> RiskDecision | None:
    for hours, max_percent in ((24, max_24h_percent), (24 * 7, max_7d_percent)):
        volatility = _global_price_range_percent(db, asset_id=asset_id, since=datetime.now(UTC) - timedelta(hours=hours))
        if volatility is None or volatility <= max_percent:
            continue
        return _decision(
            db,
            decision="blocked",
            reason_code="VOLATILITY_TOO_HIGH",
            risk_level="high",
            details={
                "window_hours": hours,
                "volatility_percent": str(volatility),
                "max_volatility_percent": str(max_percent),
            },
        )
    return None


def _fomo_block(
    db: Session,
    *,
    request: PaperTradeRequest,
    asset_id: int,
    lookback_minutes: int,
    max_rise_percent: Decimal,
) -> RiskDecision | None:
    if request.action != "paper_buy":
        return None

    since = datetime.now(UTC) - timedelta(minutes=lookback_minutes)
    prices = _global_mid_prices_since(db, asset_id=asset_id, since=since)
    rise_percent = _price_rise_percent(prices)
    if rise_percent is None:
        return None
    if rise_percent <= max_rise_percent:
        return None
    first_price = prices[0]
    latest_price = prices[-1]
    return _decision(
        db,
        decision="blocked",
        reason_code="FOMO_RISK",
        risk_level="medium",
        details={
            "lookback_minutes": lookback_minutes,
            "rise_percent": str(rise_percent.quantize(PERCENT_QUANT)),
            "max_rise_percent": str(max_rise_percent),
            "first_price": str(first_price),
            "latest_price": str(latest_price),
        },
    )


def _expected_gain_block(
    db: Session,
    *,
    request: PaperTradeRequest,
    amounts: TradeAmounts,
    min_expected_net_gain_percent: Decimal,
) -> RiskDecision | None:
    if request.action != "paper_buy" or request.expected_exit_price is None:
        return None
    expected_exit_amount = amounts.quantity * request.expected_exit_price
    expected_net_gain = expected_exit_amount - amounts.net_amount
    if amounts.net_amount <= 0:
        return None
    expected_net_gain_percent = (expected_net_gain / amounts.net_amount) * Decimal("100")
    if expected_net_gain_percent > min_expected_net_gain_percent:
        return None
    return _decision(
        db,
        decision="blocked",
        reason_code="EXPECTED_GAIN_BELOW_COST",
        risk_level="medium",
        details={
            "expected_exit_price": str(request.expected_exit_price),
            "expected_net_gain": str(expected_net_gain.quantize(Decimal("0.000001"))),
            "expected_net_gain_percent": str(expected_net_gain_percent.quantize(PERCENT_QUANT)),
            "min_expected_net_gain_percent": str(min_expected_net_gain_percent),
        },
    )


def _global_price_range_percent(db: Session, *, asset_id: int, since: datetime) -> Decimal | None:
    prices = _global_mid_prices_since(db, asset_id=asset_id, since=since)
    if len(prices) < 2:
        return None
    high_price = max(prices)
    low_price = min(prices)
    mid_price = (high_price + low_price) / Decimal("2")
    if mid_price <= 0:
        return None
    return (((high_price - low_price) / mid_price) * Decimal("100")).quantize(PERCENT_QUANT)


def _global_price_rise_percent(db: Session, *, asset_id: int, since: datetime) -> Decimal | None:
    prices = _global_mid_prices_since(db, asset_id=asset_id, since=since)
    return _price_rise_percent(prices)


def _price_rise_percent(prices: list[Decimal]) -> Decimal | None:
    if len(prices) < 2:
        return None
    first_price = prices[0]
    latest_price = prices[-1]
    if first_price <= 0:
        return None
    return (((latest_price - first_price) / first_price) * Decimal("100")).quantize(PERCENT_QUANT)


def _global_mid_prices_since(db: Session, *, asset_id: int, since: datetime) -> list[Decimal]:
    rows = db.execute(
        select(RawGlobalPrice)
        .where(RawGlobalPrice.asset_id == asset_id, RawGlobalPrice.observed_at >= since)
        .order_by(RawGlobalPrice.observed_at.asc(), RawGlobalPrice.id.asc())
    ).scalars()
    return [((row.buy_price + row.sell_price) / Decimal("2")).quantize(Decimal("0.000001")) for row in rows]


def _realized_loss_since(db: Session, *, portfolio_id: int, asset_id: int, since: datetime) -> Decimal:
    trades = db.execute(
        select(PaperTrade)
        .where(
            PaperTrade.portfolio_id == portfolio_id,
            PaperTrade.asset_id == asset_id,
            PaperTrade.action.in_(("paper_buy", "paper_sell")),
        )
        .order_by(PaperTrade.created_at.asc(), PaperTrade.id.asc())
    ).scalars()

    buy_quantity = Decimal("0")
    buy_net_amount = Decimal("0")
    realized_loss = Decimal("0")
    for trade in trades:
        if trade.action == "paper_buy":
            buy_quantity += trade.quantity
            buy_net_amount += trade.net_amount
            continue
        if trade.action != "paper_sell" or buy_quantity <= 0:
            continue

        sell_quantity = min(trade.quantity, buy_quantity)
        average_buy_cost = buy_net_amount / buy_quantity
        sell_net_amount = trade.net_amount * (sell_quantity / trade.quantity)
        pnl = sell_net_amount - (average_buy_cost * sell_quantity)
        if _as_utc(trade.created_at) >= since and pnl < 0:
            realized_loss += abs(pnl)
        buy_quantity -= sell_quantity
        buy_net_amount -= average_buy_cost * sell_quantity

    return realized_loss.quantize(Decimal("0.000001"))


def _recent_risk_decision_counts(db: Session, *, since: datetime) -> list[dict]:
    rows = db.execute(
        select(RiskDecision.decision, RiskDecision.reason_code, func.count(RiskDecision.id))
        .where(RiskDecision.created_at >= since)
        .group_by(RiskDecision.decision, RiskDecision.reason_code)
        .order_by(func.count(RiskDecision.id).desc(), RiskDecision.reason_code.asc())
    ).all()
    return [
        {
            "decision": decision,
            "reason_code": reason_code,
            "count": count,
        }
        for decision, reason_code, count in rows
    ]


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def _decision(
    db: Session,
    *,
    decision: str,
    reason_code: str,
    risk_level: str,
    details: dict,
) -> RiskDecision:
    risk_decision = RiskDecision(
        decision=decision,
        reason_code=reason_code,
        risk_level=risk_level,
        confidence=CONFIDENCE,
        details_json=details,
    )
    db.add(risk_decision)
    db.flush()
    return risk_decision
