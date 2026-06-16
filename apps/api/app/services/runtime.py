from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any

from sqlalchemy import desc, select
from sqlalchemy.orm import Session

from app.collectors.service import collector_health
from app.models import AgentMemoryEvent, CollectorRun, RuntimeHeartbeat, Signal, TradingDecisionRun


AUTO_TRADER_COMPONENT = "auto_trader"


def utc_now() -> datetime:
    return datetime.now(UTC)


def to_jsonable(value: Any) -> Any:
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, dict):
        return {str(key): to_jsonable(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [to_jsonable(item) for item in value]
    return value


def record_runtime_heartbeat(
    db: Session,
    *,
    component: str,
    status: str = "ok",
    expected_interval_seconds: int | None = None,
    details: dict | None = None,
    seen_at: datetime | None = None,
) -> RuntimeHeartbeat:
    seen_at = seen_at or utc_now()
    expected_next_at = (
        seen_at + timedelta(seconds=expected_interval_seconds) if expected_interval_seconds is not None else None
    )
    heartbeat = db.execute(select(RuntimeHeartbeat).where(RuntimeHeartbeat.component == component)).scalar_one_or_none()
    if heartbeat is None:
        heartbeat = RuntimeHeartbeat(component=component, last_seen_at=seen_at)
        db.add(heartbeat)
    heartbeat.last_seen_at = seen_at
    heartbeat.expected_next_at = expected_next_at
    heartbeat.status = status
    heartbeat.details_json = to_jsonable(details or {})
    db.flush()
    return heartbeat


def source_health_snapshot(db: Session) -> dict:
    try:
        health = collector_health(db)
    except Exception as exc:
        return {"status": "unknown", "error": type(exc).__name__}
    return {
        "status": health.get("status"),
        "collectors": [
            {
                "collector_name": item.get("collector_name"),
                "source": item.get("source"),
                "status": item.get("status"),
                "age_minutes": item.get("age_minutes"),
            }
            for item in health.get("collectors", [])
        ],
    }


def start_trading_decision_run(
    db: Session,
    *,
    mode: str,
    asset_symbol: str,
    strategy_name: str | None = None,
    trigger_collector_run_id: int | None = None,
    details: dict | None = None,
) -> TradingDecisionRun:
    run = TradingDecisionRun(
        trigger_collector_run_id=trigger_collector_run_id,
        mode=mode,
        strategy_name=strategy_name,
        asset_symbol=asset_symbol,
        source_health_json={},
        indicator_readiness_json={},
        execution_result_json={},
        notification_result_json={},
        status="running",
        details_json=to_jsonable(details or {}),
    )
    db.add(run)
    db.flush()
    return run


def finish_trading_decision_run(
    db: Session,
    run: TradingDecisionRun,
    *,
    status: str,
    action: str | None = None,
    reason_code: str | None = None,
    signal_id: int | None = None,
    source_health: dict | None = None,
    indicator_readiness: dict | None = None,
    execution_result: dict | None = None,
    notification_result: dict | None = None,
    details: dict | None = None,
    error_message: str | None = None,
) -> TradingDecisionRun:
    run.status = status
    run.finished_at = utc_now()
    run.action = action
    run.reason_code = reason_code
    run.signal_id = signal_id
    run.source_health_json = to_jsonable(source_health or {})
    run.indicator_readiness_json = to_jsonable(indicator_readiness or {})
    run.execution_result_json = to_jsonable(execution_result or {})
    run.notification_result_json = to_jsonable(notification_result or {})
    run.error_message = error_message
    run.details_json = to_jsonable({**(run.details_json or {}), **(details or {})})
    db.flush()
    return run


def latest_decision_runs(db: Session, *, limit: int = 50, asset_symbol: str | None = None) -> list[dict]:
    limit = min(max(limit, 1), 200)
    stmt = (
        select(TradingDecisionRun)
        .order_by(desc(TradingDecisionRun.started_at), desc(TradingDecisionRun.id))
        .limit(limit)
    )
    if asset_symbol:
        stmt = stmt.where(TradingDecisionRun.asset_symbol == asset_symbol)
    return [_decision_run_payload(row) for row in db.execute(stmt).scalars().all()]


def trading_status(db: Session, *, asset_symbol: str = "XAG_GRAM") -> dict:
    latest_decision = db.execute(
        select(TradingDecisionRun)
        .where(TradingDecisionRun.asset_symbol == asset_symbol)
        .order_by(desc(TradingDecisionRun.started_at), desc(TradingDecisionRun.id))
        .limit(1)
    ).scalar_one_or_none()
    latest_signal = db.execute(select(Signal).order_by(desc(Signal.created_at)).limit(1)).scalar_one_or_none()
    latest_collector = db.execute(
        select(CollectorRun).order_by(desc(CollectorRun.started_at), desc(CollectorRun.id)).limit(1)
    ).scalar_one_or_none()
    heartbeats = db.execute(select(RuntimeHeartbeat).order_by(RuntimeHeartbeat.component.asc())).scalars().all()
    latest_critical = db.execute(
        select(TradingDecisionRun)
        .where(TradingDecisionRun.asset_symbol == asset_symbol)
        .where(TradingDecisionRun.action == "HOLD")
        .where(TradingDecisionRun.reason_code.in_(_critical_hold_reasons()))
        .order_by(desc(TradingDecisionRun.started_at), desc(TradingDecisionRun.id))
        .limit(1)
    ).scalar_one_or_none()
    latest_hermes = db.execute(
        select(AgentMemoryEvent)
        .where(AgentMemoryEvent.agent_name == "hermes-agent")
        .where(AgentMemoryEvent.event_type == "hermes_sentiment")
        .order_by(desc(AgentMemoryEvent.created_at), desc(AgentMemoryEvent.id))
        .limit(1)
    ).scalar_one_or_none()

    try:
        health = collector_health(db)
    except Exception as exc:
        health = {"status": "unknown", "error": type(exc).__name__}

    no_trade_reason = None
    if latest_decision is None:
        no_trade_reason = "NO_DECISION_RUNS"
    elif latest_decision.status in {"failed", "error"}:
        no_trade_reason = latest_decision.error_message or latest_decision.reason_code or "DECISION_FAILED"
    elif (
        latest_decision.action in {"BUY", "SELL"} and latest_decision.execution_result_json.get("status") != "executed"
    ):
        no_trade_reason = latest_decision.execution_result_json.get("skipped_reason") or latest_decision.reason_code
    elif latest_decision.action == "HOLD":
        no_trade_reason = latest_decision.reason_code or "HOLD"
    elif latest_decision.execution_result_json.get("status") != "executed":
        no_trade_reason = latest_decision.execution_result_json.get("skipped_reason") or latest_decision.reason_code

    return {
        "asset_symbol": asset_symbol,
        "runtime": {
            "status": _runtime_status(heartbeats, latest_decision),
            "heartbeats": [_heartbeat_payload(row) for row in heartbeats],
        },
        "heartbeat_overdue": [_heartbeat_payload(row) for row in _overdue_heartbeats(heartbeats)],
        "latest_critical_block": _decision_run_payload(latest_critical) if latest_critical else None,
        "hermes_status": _hermes_status_payload(latest_hermes),
        "latest_decision": _decision_run_payload(latest_decision) if latest_decision else None,
        "latest_signal": _signal_payload(latest_signal) if latest_signal else None,
        "latest_collector_run": _collector_run_payload(latest_collector) if latest_collector else None,
        "collector_health": health,
        "why_no_trade": no_trade_reason,
    }


def _runtime_status(heartbeats: list[RuntimeHeartbeat], latest_decision: TradingDecisionRun | None) -> str:
    failing = [row for row in heartbeats if row.status in {"degraded", "failing", "failed", "error"}]
    overdue = _overdue_heartbeats(heartbeats)
    if failing:
        return "degraded"
    if overdue:
        return "overdue"
    if latest_decision is not None and latest_decision.status in {"failed", "error"}:
        return "degraded"
    return "ok"


def _overdue_heartbeats(heartbeats: list[RuntimeHeartbeat]) -> list[RuntimeHeartbeat]:
    now = utc_now()
    return [row for row in heartbeats if row.expected_next_at is not None and _aware(row.expected_next_at) < now]


def _critical_hold_reasons() -> set[str]:
    return {
        "SOURCE_DIVERGENCE_BLOCK",
        "DAILY_BAR_DELAYED",
        "ENTRY_TIMEFRAME_STALE",
        "EXECUTION_TIMEFRAME_STALE",
        "PORTFOLIO_NOT_FOUND",
        "ASSET_NOT_FOUND",
        "PRICE_SNAPSHOT_MISSING",
        "BLOCKED_CONFIG_INVALID",
    }


def _aware(value: datetime) -> datetime:
    return value if value.tzinfo is not None else value.replace(tzinfo=UTC)


def _heartbeat_payload(row: RuntimeHeartbeat) -> dict:
    return {
        "component": row.component,
        "last_seen_at": row.last_seen_at,
        "expected_next_at": row.expected_next_at,
        "status": row.status,
        "details": row.details_json,
    }


def _decision_run_payload(row: TradingDecisionRun) -> dict:
    return {
        "id": row.id,
        "trigger_collector_run_id": row.trigger_collector_run_id,
        "signal_id": row.signal_id,
        "started_at": row.started_at,
        "finished_at": row.finished_at,
        "mode": row.mode,
        "strategy_name": row.strategy_name,
        "asset_symbol": row.asset_symbol,
        "action": row.action,
        "reason_code": row.reason_code,
        "status": row.status,
        "source_health": row.source_health_json,
        "indicator_readiness": row.indicator_readiness_json,
        "execution_result": row.execution_result_json,
        "notification_result": row.notification_result_json,
        "error_message": row.error_message,
        "details": row.details_json,
    }


def _signal_payload(row: Signal) -> dict:
    return {
        "id": row.id,
        "observed_at": row.observed_at,
        "action": row.action,
        "reason_code": row.reason_code,
        "price_usd_oz": str(row.price_usd_oz),
        "created_at": row.created_at,
    }


def _collector_run_payload(row: CollectorRun) -> dict:
    return {
        "id": row.id,
        "collector_name": row.collector_name,
        "source": row.source,
        "status": row.status,
        "records_seen": row.records_seen,
        "records_inserted": row.records_inserted,
        "duplicates": row.duplicates,
        "error_message": row.error_message,
        "started_at": row.started_at,
        "finished_at": row.finished_at,
    }


def _hermes_status_payload(row: AgentMemoryEvent | None) -> dict | None:
    if row is None:
        return None
    value = row.value_json or {}
    return {
        "event_id": row.id,
        "created_at": row.created_at,
        "llm_status": value.get("llm_status", "unknown"),
        "fallback_reason": value.get("fallback_reason"),
        "confidence": value.get("confidence"),
        "source_coverage": value.get("source_coverage"),
    }
