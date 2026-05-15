from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import desc, select, text
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.core.db import get_db
from app.collectors.public_sources import (
    collect_global_xag_usd,
    collect_kuveyt_public_silver,
    collect_stooq_xag_usd,
    collect_tcmb_usd_try,
)
from app.collectors.service import (
    CollectorError,
    collector_health,
    collector_quality,
    collector_validation_gate,
    ingest_manual_price,
    latest_collector_run,
)
from app.models import Asset, CollectorRun, Portfolio, PortfolioSnapshot, PriceSnapshot, Report, Signal
from app.paper_trading.service import PaperTradingError, calculate_position, execute_paper_trade
from app.schemas.collectors import (
    CollectorHealthResponse,
    CollectorQualityResponse,
    CollectorRunResultResponse,
    CollectorRunPayload,
    CollectorValidationGateResponse,
    ManualPriceIngestRequest,
    ManualPriceIngestResponse,
)
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
            "id": snapshot.id,
            "asset_id": snapshot.asset_id,
            "source": snapshot.source,
            "buy_price": str(snapshot.buy_price),
            "sell_price": str(snapshot.sell_price),
            "mid_price": str(snapshot.mid_price),
            "currency": snapshot.currency,
            "spread_absolute": str(snapshot.spread_absolute),
            "spread_percent": str(snapshot.spread_percent),
            "observed_at": snapshot.observed_at,
        }
    }


@router.post("/collectors/manual-price", response_model=ManualPriceIngestResponse)
def create_manual_price(
    request: ManualPriceIngestRequest,
    db: Session = Depends(get_db),
) -> ManualPriceIngestResponse:
    try:
        run, raw_inserted, snapshot = ingest_manual_price(db, request)
    except CollectorError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return ManualPriceIngestResponse(
        collector_run=_collector_run_payload(run),
        raw_inserted=raw_inserted,
        price_snapshot=_price_snapshot_payload(snapshot) if snapshot is not None else None,
    )


@router.post("/collectors/kuveyt-silver/run", response_model=CollectorRunResultResponse)
def run_kuveyt_silver_collector(db: Session = Depends(get_db)) -> CollectorRunResultResponse:
    run, raw_inserted, snapshot = collect_kuveyt_public_silver(db)
    return CollectorRunResultResponse(
        collector_run=_collector_run_payload(run),
        raw_inserted=raw_inserted,
        price_snapshot=_price_snapshot_payload(snapshot) if snapshot is not None else None,
    )


@router.post("/collectors/stooq-xag-usd/run", response_model=CollectorRunResultResponse)
def run_stooq_xag_usd_collector(db: Session = Depends(get_db)) -> CollectorRunResultResponse:
    run, raw_inserted, snapshot = collect_stooq_xag_usd(db)
    return CollectorRunResultResponse(
        collector_run=_collector_run_payload(run),
        raw_inserted=raw_inserted,
        price_snapshot=_price_snapshot_payload(snapshot) if snapshot is not None else None,
    )


@router.post("/collectors/global-xag-usd/run", response_model=CollectorRunResultResponse)
def run_global_xag_usd_collector(db: Session = Depends(get_db)) -> CollectorRunResultResponse:
    run, raw_inserted, snapshot = collect_global_xag_usd(db)
    return CollectorRunResultResponse(
        collector_run=_collector_run_payload(run),
        raw_inserted=raw_inserted,
        price_snapshot=_price_snapshot_payload(snapshot) if snapshot is not None else None,
    )


@router.post("/collectors/tcmb-usd-try/run", response_model=CollectorRunResultResponse)
def run_tcmb_usd_try_collector(db: Session = Depends(get_db)) -> CollectorRunResultResponse:
    run, raw_inserted = collect_tcmb_usd_try(db)
    return CollectorRunResultResponse(
        collector_run=_collector_run_payload(run),
        raw_inserted=raw_inserted,
        price_snapshot=None,
    )


@router.get("/collectors/runs/latest", response_model=CollectorRunPayload | None)
def get_latest_collector_run(db: Session = Depends(get_db)) -> CollectorRunPayload | None:
    run = latest_collector_run(db)
    return _collector_run_payload(run) if run is not None else None


@router.get("/collectors/health", response_model=CollectorHealthResponse)
def get_collector_health(stale_after_minutes: int = 60, db: Session = Depends(get_db)) -> dict:
    if stale_after_minutes <= 0:
        raise HTTPException(status_code=400, detail="stale_after_minutes must be greater than zero")
    return collector_health(db, stale_after_minutes=stale_after_minutes)


@router.get("/collectors/quality", response_model=CollectorQualityResponse)
def get_collector_quality(
    window_hours: int = 24,
    expected_interval_minutes: int = 60,
    db: Session = Depends(get_db),
) -> dict:
    try:
        return collector_quality(db, window_hours=window_hours, expected_interval_minutes=expected_interval_minutes)
    except CollectorError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/collectors/validation-gate", response_model=CollectorValidationGateResponse)
def get_collector_validation_gate(
    window_hours: int = 24,
    expected_interval_minutes: int = 15,
    stale_after_minutes: int = 60,
    db: Session = Depends(get_db),
) -> dict:
    if stale_after_minutes <= 0:
        raise HTTPException(status_code=400, detail="stale_after_minutes must be greater than zero")
    try:
        return collector_validation_gate(
            db,
            window_hours=window_hours,
            expected_interval_minutes=expected_interval_minutes,
            stale_after_minutes=stale_after_minutes,
        )
    except CollectorError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


def _collector_run_payload(run: CollectorRun) -> dict:
    return {
        "id": run.id,
        "collector_name": run.collector_name,
        "source": run.source,
        "status": run.status,
        "records_seen": run.records_seen,
        "records_inserted": run.records_inserted,
        "duplicates": run.duplicates,
        "error_message": run.error_message,
        "started_at": run.started_at,
        "finished_at": run.finished_at,
    }


def _price_snapshot_payload(snapshot: PriceSnapshot) -> dict:
    return {
        "id": snapshot.id,
        "asset_id": snapshot.asset_id,
        "source": snapshot.source,
        "buy_price": snapshot.buy_price,
        "sell_price": snapshot.sell_price,
        "mid_price": snapshot.mid_price,
        "currency": snapshot.currency,
        "spread_absolute": snapshot.spread_absolute,
        "spread_percent": snapshot.spread_percent,
        "observed_at": snapshot.observed_at,
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
