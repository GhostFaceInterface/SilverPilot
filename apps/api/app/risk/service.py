from dataclasses import dataclass
from decimal import Decimal
from typing import Protocol

from sqlalchemy.orm import Session

from app.collectors.service import collector_health
from app.core.config import get_settings
from app.models import Asset, Portfolio, RiskDecision
from app.schemas.paper_trading import PaperTradeRequest

CONFIDENCE = Decimal("1.0000")


@dataclass(frozen=True)
class TradeAmounts:
    quantity: Decimal
    price: Decimal
    gross_amount: Decimal
    net_amount: Decimal


class PositionLike(Protocol):
    quantity: Decimal


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
        },
    )


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
