from fastapi import APIRouter, Depends, HTTPException, Header, BackgroundTasks
from sqlalchemy import desc, select, text, func
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.core.db import get_db
from app.collectors.public_sources import (
    collect_global_xag_usd,
    collect_kuveyt_public_silver,
    collect_yahoo_usd_try,
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
from app.models import (
    Asset,
    CollectorRun,
    Portfolio,
    PortfolioSnapshot,
    PriceSnapshot,
    Report,
    Signal,
    LLMCallTrace,
    AgentMemoryEvent,
)
from app.paper_trading.service import PaperTradingError, calculate_position, execute_paper_trade
from app.risk.service import RiskStatusError, risk_policy_status
from app.agents.hermes import run_hermes_sentiment_analysis
from app.agents.risk import run_signal_critique
from app.agents.report import run_daily_performance_report
from app.agents.telegram_bot import process_telegram_update
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
from app.schemas.risk import RiskPolicyStatusResponse
from app.schemas.agent import (
    LLMTraceCreate,
    LLMTraceResponse,
    AgentMemoryCreate,
    AgentMemoryResponse,
    RiskCritiqueRequest,
    ReportResponse,
    OrchestrateRunRequest,
)

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
        db.rollback()
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        db.rollback()
        raise exc
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
            "risk_decision_id": trade.risk_decision_id,
        },
        risk_decision={
            "id": trade.risk_decision.id,
            "decision": trade.risk_decision.decision,
            "reason_code": trade.risk_decision.reason_code,
            "risk_level": trade.risk_decision.risk_level,
            "confidence": trade.risk_decision.confidence,
            "details": trade.risk_decision.details_json,
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
def get_paper_position(
    portfolio_name: str = "gram-paper", asset_symbol: str = "XAG_GRAM", db: Session = Depends(get_db)
):
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


@router.get("/risk/status", response_model=RiskPolicyStatusResponse)
def get_risk_status(
    portfolio_name: str = "gram-paper",
    asset_symbol: str = "XAG_GRAM",
    db: Session = Depends(get_db),
) -> RiskPolicyStatusResponse:
    try:
        return RiskPolicyStatusResponse.model_validate(
            risk_policy_status(db, portfolio_name=portfolio_name, asset_symbol=asset_symbol)
        )
    except RiskStatusError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


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


@router.post("/collectors/yahoo-usd-try/run", response_model=CollectorRunResultResponse)
def run_yahoo_usd_try_collector(db: Session = Depends(get_db)) -> CollectorRunResultResponse:
    run, raw_inserted = collect_yahoo_usd_try(db)
    return CollectorRunResultResponse(
        collector_run=_collector_run_payload(run),
        raw_inserted=raw_inserted,
        price_snapshot=None,
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
            "id": signal.id,
            "observed_at": signal.observed_at,
            "price_snapshot_id": signal.price_snapshot_id,
            "indicator_id": signal.indicator_id,
            "action": signal.action,
            "reason_code": signal.reason_code,
            "price_usd_oz": str(signal.price_usd_oz),
            "details": signal.details_json,
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


def verify_agent_token(x_agent_token: str | None = Header(None), settings: Settings = Depends(get_settings)) -> None:
    if not settings.agent_api_token:
        return
    if x_agent_token != settings.agent_api_token:
        raise HTTPException(status_code=401, detail="Access Denied: Invalid Agent API Token")


@router.post("/agent/trace", response_model=LLMTraceResponse)
def create_agent_trace(
    request: LLMTraceCreate, db: Session = Depends(get_db), _: None = Depends(verify_agent_token)
) -> LLMTraceResponse:
    try:
        trace = LLMCallTrace(
            agent_name=request.agent_name,
            model_name=request.model_name,
            prompt_tokens=request.prompt_tokens,
            completion_tokens=request.completion_tokens,
            total_cost_usd=request.total_cost_usd,
            latency_ms=request.latency_ms,
            status=request.status,
            prompt_raw=request.prompt_raw,
            response_raw=request.response_raw,
            error_message=request.error_message,
        )
        db.add(trace)
        db.commit()
        db.refresh(trace)
        return trace
    except Exception as exc:
        db.rollback()
        raise exc


@router.get("/agent/traces", response_model=list[LLMTraceResponse])
def get_agent_traces(
    limit: int = 50,
    offset: int = 0,
    agent_name: str | None = None,
    db: Session = Depends(get_db),
    _: None = Depends(verify_agent_token),
) -> list[LLMCallTrace]:
    stmt = select(LLMCallTrace)
    if agent_name:
        stmt = stmt.where(LLMCallTrace.agent_name == agent_name)
    stmt = stmt.order_by(desc(LLMCallTrace.created_at)).limit(limit).offset(offset)
    traces = db.execute(stmt).scalars().all()
    return list(traces)


@router.get("/agent/traces/stats")
def get_agent_traces_stats(db: Session = Depends(get_db), _: None = Depends(verify_agent_token)):
    # 1. Total Cost & Count
    total_stats = db.execute(
        select(
            func.sum(LLMCallTrace.total_cost_usd).label("total_cost"),
            func.count(LLMCallTrace.id).label("total_calls"),
            func.avg(LLMCallTrace.latency_ms).label("avg_latency"),
        )
    ).first()

    total_cost = float(total_stats.total_cost or 0)
    total_calls = total_stats.total_calls or 0
    avg_latency = float(total_stats.avg_latency or 0)

    # 2. Break-down by Agent
    agent_stats_rows = db.execute(
        select(
            LLMCallTrace.agent_name,
            func.count(LLMCallTrace.id).label("calls"),
            func.sum(LLMCallTrace.total_cost_usd).label("cost"),
            func.avg(LLMCallTrace.latency_ms).label("latency"),
        ).group_by(LLMCallTrace.agent_name)
    ).all()

    agent_breakdown = []
    for row in agent_stats_rows:
        agent_breakdown.append(
            {
                "agent_name": row.agent_name,
                "calls": row.calls,
                "total_cost_usd": float(row.cost or 0),
                "avg_latency_ms": float(row.latency or 0),
            }
        )

    # 3. Break-down by Model
    model_stats_rows = db.execute(
        select(
            LLMCallTrace.model_name,
            func.count(LLMCallTrace.id).label("calls"),
            func.sum(LLMCallTrace.total_cost_usd).label("cost"),
            func.avg(LLMCallTrace.latency_ms).label("latency"),
        ).group_by(LLMCallTrace.model_name)
    ).all()

    model_breakdown = []
    for row in model_stats_rows:
        model_breakdown.append(
            {
                "model_name": row.model_name,
                "calls": row.calls,
                "total_cost_usd": float(row.cost or 0),
                "avg_latency_ms": float(row.latency or 0),
            }
        )

    return {
        "total_cost_usd": total_cost,
        "total_calls": total_calls,
        "avg_latency_ms": avg_latency,
        "by_agent": agent_breakdown,
        "by_model": model_breakdown,
    }


@router.post("/agent/memory", response_model=AgentMemoryResponse)
def create_agent_memory(
    request: AgentMemoryCreate, db: Session = Depends(get_db), _: None = Depends(verify_agent_token)
) -> AgentMemoryResponse:
    try:
        memory_event = AgentMemoryEvent(
            agent_name=request.agent_name, event_type=request.event_type, key=request.key, value_json=request.value_json
        )
        db.add(memory_event)
        db.commit()
        db.refresh(memory_event)
        return memory_event
    except Exception as exc:
        db.rollback()
        raise exc


@router.get("/agent/memory", response_model=list[AgentMemoryResponse])
def get_agent_memory(
    agent_name: str,
    key: str | None = None,
    event_type: str | None = None,
    limit: int = 100,
    offset: int = 0,
    db: Session = Depends(get_db),
    _: None = Depends(verify_agent_token),
) -> list[AgentMemoryEvent]:
    stmt = select(AgentMemoryEvent).where(AgentMemoryEvent.agent_name == agent_name)
    if key:
        stmt = stmt.where(AgentMemoryEvent.key == key)
    if event_type:
        stmt = stmt.where(AgentMemoryEvent.event_type == event_type)

    stmt = stmt.order_by(desc(AgentMemoryEvent.created_at)).limit(limit).offset(offset)
    results = db.execute(stmt).scalars().all()
    return list(results)


@router.post("/agent/news/trigger", response_model=AgentMemoryResponse)
async def trigger_news_agent(
    db: Session = Depends(get_db), _: None = Depends(verify_agent_token)
) -> AgentMemoryResponse:
    return await run_hermes_sentiment_analysis(db)


@router.post("/agent/report/trigger", response_model=ReportResponse)
async def trigger_report_agent(
    db: Session = Depends(get_db),
    _: None = Depends(verify_agent_token),
) -> Report:
    return await run_daily_performance_report(db)


@router.post("/agent/risk/critique", response_model=AgentMemoryResponse)
async def critique_risk_agent(
    payload: RiskCritiqueRequest = RiskCritiqueRequest(),
    db: Session = Depends(get_db),
    _: None = Depends(verify_agent_token),
) -> AgentMemoryResponse:
    try:
        return await run_signal_critique(db, signal_id=payload.signal_id)
    except ValueError as exc:
        db.rollback()
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except Exception as exc:
        db.rollback()
        raise exc


def run_dataset_build_task(version: str) -> None:
    """Helper to run the dataset pipeline in a background task thread."""
    try:
        from scripts.build_dataset import build_dataset

        build_dataset(version=version, dry_run=False)
    except Exception as e:
        import logging

        logger = logging.getLogger("silverpilot.ml.dataset")
        logger.error(f"Error building dataset version {version}: {e}", exc_info=True)


@router.post("/datasets/build")
def build_dataset_endpoint(
    background_tasks: BackgroundTasks, version: str = "1.0.0", _: None = Depends(verify_agent_token)
):
    """Triggers the ML dataset generation pipeline in the background."""
    background_tasks.add_task(run_dataset_build_task, version)
    return {"status": "accepted", "message": f"Dataset build for version {version} started in background."}


@router.get("/datasets/list")
def list_datasets_endpoint(_: None = Depends(verify_agent_token)):
    """Lists metadata for all built datasets."""
    import os
    import json

    # Locate project root dynamically
    current_dir = os.path.dirname(os.path.abspath(__file__))
    root_path = current_dir
    for _ in range(10):
        if os.path.exists(os.path.join(root_path, "apps")) or os.path.exists(os.path.join(root_path, "data")):
            break
        root_path = os.path.dirname(root_path)

    datasets_dir = os.path.join(root_path, "data", "datasets")
    if not os.path.exists(datasets_dir):
        return []

    datasets = []
    for item in os.listdir(datasets_dir):
        item_path = os.path.join(datasets_dir, item)
        if os.path.isdir(item_path):
            meta_path = os.path.join(item_path, "metadata.json")
            if os.path.exists(meta_path):
                try:
                    with open(meta_path, "r") as f:
                        meta_data = json.load(f)
                    datasets.append(meta_data)
                except Exception as e:
                    import logging

                    logger = logging.getLogger("silverpilot.ml.dataset")
                    logger.warning(f"Failed to read metadata for {item}: {e}")

    return datasets


@router.get("/ml/model/active")
def get_active_model(_: None = Depends(verify_agent_token)):
    """
    Returns the metadata of the active champion model from disk (fail-secure).
    """
    from app.ml.inference import get_active_model_metadata

    return get_active_model_metadata()


async def run_orchestrate_background(signal_id: int | None = None) -> None:
    from app.core.db import SessionLocal
    from app.agents.orchestrator import run_multi_agent_analysis
    import logging

    logger = logging.getLogger("silverpilot.agents.orchestrator.background")
    db = SessionLocal()
    try:
        logger.info(f"Running multi-agent analysis background task for signal_id={signal_id}")
        await run_multi_agent_analysis(db, signal_id=signal_id)
        logger.info("Multi-agent analysis background task completed successfully")
    except Exception as e:
        db.rollback()
        logger.error(f"Error running multi-agent analysis in background: {e}", exc_info=True)
    finally:
        db.close()


@router.post("/agent/orchestrate/run", status_code=202)
async def trigger_orchestrator(
    payload: OrchestrateRunRequest = OrchestrateRunRequest(),
    background_tasks: BackgroundTasks = BackgroundTasks(),
    _: None = Depends(verify_agent_token),
):
    """
    Triggers the multi-agent analysis orchestrator in the background.
    """
    background_tasks.add_task(run_orchestrate_background, payload.signal_id)
    return {"status": "accepted", "message": "Multi-agent analysis triggered in background."}


@router.post("/agent/telegram/webhook")
async def telegram_webhook(update: dict, background_tasks: BackgroundTasks, settings: Settings = Depends(get_settings)):
    """
    Telegram webhook endpoint. Receives incoming updates asynchronously.
    Runs verification and processing in a background task to prevent timeouts.
    """
    if not settings.telegram_bot_token:
        return {"status": "ignored", "reason": "bot not configured"}

    background_tasks.add_task(process_telegram_update, update, settings)
    return {"status": "accepted"}
