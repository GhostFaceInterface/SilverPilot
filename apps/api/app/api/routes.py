from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import desc, select, text
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.core.db import get_db
from app.models import Asset, Portfolio, PortfolioSnapshot, PriceSnapshot, Report, Signal
from app.paper_trading.service import PaperTradingError, calculate_position, execute_paper_trade
from app.schemas.health import HealthResponse
from app.schemas.paper_trading import PaperTradeRequest, PaperTradeResponse

router = APIRouter()


@router.get("/health", response_model=HealthResponse)
def health(db: Session = Depends(get_db), settings: Settings = Depends(get_settings)) -> HealthResponse:
    db.execute(text("SELECT 1"))
    return HealthResponse(
        status="ok",
        app=settings.app_name,
        environment=settings.app_env,
        database="ok",
        real_money_enabled=settings.real_money_enabled,
    )


@router.get("/portfolio")
def get_portfolio(db: Session = Depends(get_db)):
    portfolio = db.execute(select(Portfolio).order_by(desc(Portfolio.created_at)).limit(1)).scalar_one_or_none()
    if portfolio is None:
        return {"portfolio": None}
    latest_snapshot = db.execute(
        select(PortfolioSnapshot)
        .where(PortfolioSnapshot.portfolio_id == portfolio.id)
        .order_by(desc(PortfolioSnapshot.observed_at))
        .limit(1)
    ).scalar_one_or_none()
    return {
        "portfolio": {
            "id": portfolio.id,
            "name": portfolio.name,
            "base_currency": portfolio.base_currency,
            "initial_cash": str(portfolio.initial_cash),
            "cash_balance": str(portfolio.cash_balance),
            "is_real_money": portfolio.is_real_money,
            "latest_snapshot": {
                "asset_quantity": str(latest_snapshot.asset_quantity),
                "portfolio_value": str(latest_snapshot.portfolio_value),
                "realized_pnl": str(latest_snapshot.realized_pnl),
                "unrealized_pnl": str(latest_snapshot.unrealized_pnl),
                "observed_at": latest_snapshot.observed_at,
            }
            if latest_snapshot
            else None,
        }
    }


@router.post("/paper-trades", response_model=PaperTradeResponse)
def create_paper_trade(request: PaperTradeRequest, db: Session = Depends(get_db)) -> PaperTradeResponse:
    try:
        trade, snapshot = execute_paper_trade(db, request)
    except PaperTradingError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return PaperTradeResponse(
        trade={
            "id": trade.id,
            "portfolio_id": trade.portfolio_id,
            "asset_id": trade.asset_id,
            "action": trade.action,
            "quantity": trade.quantity,
            "price": trade.price,
            "gross_amount": trade.gross_amount,
            "fees": trade.fees,
            "taxes": trade.taxes,
            "net_amount": trade.net_amount,
        },
        snapshot={
            "id": snapshot.id,
            "portfolio_id": snapshot.portfolio_id,
            "cash_balance": snapshot.cash_balance,
            "asset_quantity": snapshot.asset_quantity,
            "portfolio_value": snapshot.portfolio_value,
            "realized_pnl": snapshot.realized_pnl,
            "unrealized_pnl": snapshot.unrealized_pnl,
        },
    )


@router.get("/paper-trades/position")
def get_paper_position(portfolio_name: str = "default-paper", asset_symbol: str = "XAG", db: Session = Depends(get_db)):
    portfolio = db.execute(select(Portfolio).where(Portfolio.name == portfolio_name)).scalar_one_or_none()
    if portfolio is None:
        raise HTTPException(status_code=404, detail="Portfolio not found")
    asset_row = db.execute(select(Asset).where(Asset.symbol == asset_symbol)).scalar_one_or_none()
    if asset_row is None:
        raise HTTPException(status_code=404, detail="Asset not found")
    position = calculate_position(db, portfolio.id, asset_row.id)
    return {
        "portfolio_name": portfolio.name,
        "asset_symbol": asset_row.symbol,
        "asset_quantity": str(position.quantity),
        "average_buy_cost": str(position.average_buy_cost),
        "cash_balance": str(portfolio.cash_balance),
    }


@router.get("/prices/latest")
def get_latest_price(db: Session = Depends(get_db)):
    snapshot = db.execute(select(PriceSnapshot).order_by(desc(PriceSnapshot.observed_at)).limit(1)).scalar_one_or_none()
    if snapshot is None:
        return {"price": None}
    return {
        "price": {
            "asset_id": snapshot.asset_id,
            "source": snapshot.source,
            "buy_price": str(snapshot.buy_price),
            "sell_price": str(snapshot.sell_price),
            "currency": snapshot.currency,
            "observed_at": snapshot.observed_at,
        }
    }


@router.get("/signals/latest")
def get_latest_signal(db: Session = Depends(get_db)):
    signal = db.execute(select(Signal).order_by(desc(Signal.created_at)).limit(1)).scalar_one_or_none()
    if signal is None:
        return {"signal": None}
    return {
        "signal": {
            "source": signal.source,
            "asset_id": signal.asset_id,
            "signal": signal.signal,
            "confidence": str(signal.confidence),
            "created_at": signal.created_at,
        }
    }


@router.get("/reports/daily/latest")
def get_latest_daily_report(db: Session = Depends(get_db)):
    report = db.execute(
        select(Report).where(Report.report_type == "daily").order_by(desc(Report.created_at)).limit(1)
    ).scalar_one_or_none()
    if report is None:
        return {"report": None}
    return {
        "report": {
            "id": report.id,
            "period_start": report.period_start,
            "period_end": report.period_end,
            "payload": report.payload_json,
            "created_at": report.created_at,
        }
    }
