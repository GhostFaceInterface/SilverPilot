from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any, Literal

from sqlalchemy.orm import Session

from app.models import RiskDecision, TradeIntentRecord
from app.paper_trading.service import (
    PaperTradingError,
    _calculate_trade_amounts,
    _get_asset,
    _get_portfolio,
    calculate_position,
    execute_paper_trade_with_risk_decision,
)
from app.risk.service import TradeAmounts, _decision, evaluate_paper_trade_risk
from app.schemas.paper_trading import PaperTradeRequest


@dataclass(frozen=True)
class TradeIntent:
    portfolio_name: str
    asset_symbol: str
    action: Literal["BUY", "SELL"]
    confidence: Decimal
    reason_code: str
    stop_loss_price: Decimal | None = None
    take_profit_price: Decimal | None = None
    expected_exit_price: Decimal | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


def execute_trade_intent(
    db: Session,
    *,
    intent: TradeIntent,
    buy_price: Decimal,
    sell_price: Decimal,
    fee_amount: Decimal = Decimal("0"),
):
    request = _intent_to_request(
        db,
        intent=intent,
        buy_price=buy_price,
        sell_price=sell_price,
        fee_amount=fee_amount,
    )
    intent_record = persist_trade_intent(db, intent=intent, request=request)
    risk_decision = evaluate_trade_intent_risk(db, intent=intent, request=request)
    intent_record.risk_decision_id = risk_decision.id
    intent_record.status = "risk_allowed" if risk_decision.decision == "allow" else "risk_blocked"
    db.flush()
    trade, snapshot = execute_paper_trade_with_risk_decision(
        db,
        request,
        risk_decision,
        trade_intent_record=intent_record,
    )
    intent_record.status = "executed" if trade.action in ("paper_buy", "paper_sell") else "blocked"
    db.flush()
    db.commit()
    db.refresh(intent_record)
    return trade, snapshot


def persist_trade_intent(db: Session, *, intent: TradeIntent, request: PaperTradeRequest) -> TradeIntentRecord:
    portfolio = _get_portfolio(db, intent.portfolio_name, lock=False)
    asset = _get_asset(db, intent.asset_symbol)
    signal_id = intent.metadata.get("signal_id")
    trading_decision_run_id = intent.metadata.get("trading_decision_run_id")
    record = TradeIntentRecord(
        trading_decision_run_id=trading_decision_run_id if isinstance(trading_decision_run_id, int) else None,
        signal_id=signal_id if isinstance(signal_id, int) else None,
        portfolio_id=portfolio.id,
        asset_id=asset.id,
        action=intent.action,
        confidence=intent.confidence,
        reason_code=intent.reason_code,
        stop_loss_price=intent.stop_loss_price,
        take_profit_price=intent.take_profit_price,
        expected_exit_price=intent.expected_exit_price,
        status="created",
        metadata_json={
            **intent.metadata,
            "trading_decision_run_id": trading_decision_run_id,
            "request_action": request.action,
            "request_buy_price": str(request.buy_price),
            "request_sell_price": str(request.sell_price),
        },
    )
    db.add(record)
    db.flush()
    return record


def evaluate_trade_intent_risk(db: Session, *, intent: TradeIntent, request: PaperTradeRequest) -> RiskDecision:
    if intent.action == "BUY":
        if intent.stop_loss_price is None or intent.take_profit_price is None or intent.expected_exit_price is None:
            return _decision(
                db,
                decision="blocked",
                reason_code="INTENT_METADATA_MISSING",
                risk_level="high",
                details={
                    "intent_action": intent.action,
                    "reason_code": intent.reason_code,
                    "missing_fields": [
                        name
                        for name, value in (
                            ("stop_loss_price", intent.stop_loss_price),
                            ("take_profit_price", intent.take_profit_price),
                            ("expected_exit_price", intent.expected_exit_price),
                        )
                        if value is None
                    ],
                },
            )
        if not (intent.stop_loss_price < request.buy_price < intent.take_profit_price):
            return _decision(
                db,
                decision="blocked",
                reason_code="INTENT_INVALID_PRICE_LADDER",
                risk_level="high",
                details={
                    "intent_action": intent.action,
                    "buy_price": str(request.buy_price),
                    "stop_loss_price": str(intent.stop_loss_price),
                    "take_profit_price": str(intent.take_profit_price),
                },
            )

    portfolio = _get_portfolio(db, request.portfolio_name, lock=True)
    asset = _get_asset(db, request.asset_symbol)
    position = calculate_position(db, portfolio.id, asset.id)
    quantity, price, gross_amount, net_amount = _calculate_trade_amounts(request)

    return evaluate_paper_trade_risk(
        db,
        request=request,
        portfolio=portfolio,
        asset=asset,
        position=position,
        amounts=TradeAmounts(
            quantity=quantity,
            price=price,
            gross_amount=gross_amount,
            net_amount=net_amount,
        ),
    )


def _intent_to_request(
    db: Session,
    *,
    intent: TradeIntent,
    buy_price: Decimal,
    sell_price: Decimal,
    fee_amount: Decimal,
) -> PaperTradeRequest:
    portfolio = _get_portfolio(db, intent.portfolio_name, lock=False)
    asset = _get_asset(db, intent.asset_symbol)
    position = calculate_position(db, portfolio.id, asset.id)

    if intent.action == "BUY":
        cash_amount = portfolio.cash_balance
        if cash_amount <= fee_amount:
            raise PaperTradingError("Insufficient cash balance to execute buy intent")
        return PaperTradeRequest(
            portfolio_name=intent.portfolio_name,
            asset_symbol=intent.asset_symbol,
            action="paper_buy",
            quantity=None,
            cash_amount=cash_amount,
            buy_price=buy_price,
            sell_price=sell_price,
            expected_exit_price=intent.expected_exit_price,
            fees=fee_amount,
            taxes=Decimal("0"),
        )

    if position.quantity <= 0:
        raise PaperTradingError("No open position to execute sell intent")

    return PaperTradeRequest(
        portfolio_name=intent.portfolio_name,
        asset_symbol=intent.asset_symbol,
        action="paper_sell",
        quantity=position.quantity,
        buy_price=buy_price,
        sell_price=sell_price,
        fees=fee_amount,
        taxes=Decimal("0"),
    )
