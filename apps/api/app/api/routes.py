from fastapi import APIRouter, Depends
from sqlalchemy import desc, select, text
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.core.db import get_db
from app.models import Portfolio, PriceSnapshot, Report, Signal
from app.schemas.health import HealthResponse

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
    return {
        "portfolio": {
            "id": portfolio.id,
            "name": portfolio.name,
            "base_currency": portfolio.base_currency,
            "initial_cash": str(portfolio.initial_cash),
            "cash_balance": str(portfolio.cash_balance),
            "is_real_money": portfolio.is_real_money,
        }
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
