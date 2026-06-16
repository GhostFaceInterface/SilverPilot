from datetime import UTC, datetime
from decimal import Decimal

from fastapi.testclient import TestClient

from app.agents.telegram_bot import handle_telegram_command
from app.core.db import get_db
from app.main import create_app
from app.models import Asset, CollectorRun, Portfolio, PriceSnapshot, Signal
from app.services.runtime import (
    finish_trading_decision_run,
    record_runtime_heartbeat,
    start_trading_decision_run,
    trading_status,
)


def _seed_signal(db_session):
    asset = Asset(symbol="XAG_GRAM", name="Gram Silver", asset_type="metal", is_active=True)
    portfolio = Portfolio(
        name="gram-paper",
        base_currency="USD",
        initial_cash=Decimal("2500.000000"),
        cash_balance=Decimal("2500.000000"),
        is_real_money=False,
    )
    collector_run = CollectorRun(
        collector_name="global_xag_usd",
        source="yahoo-si-f",
        status="success",
        records_seen=1,
        records_inserted=1,
        duplicates=0,
        started_at=datetime.now(UTC),
        finished_at=datetime.now(UTC),
        details_json={},
    )
    db_session.add_all([asset, portfolio, collector_run])
    db_session.flush()
    snapshot = PriceSnapshot(
        collector_run_id=collector_run.id,
        asset_id=asset.id,
        source="global-xag-usd",
        buy_price=Decimal("30.000000"),
        sell_price=Decimal("30.100000"),
        mid_price=Decimal("30.050000"),
        currency="USD",
        spread_absolute=Decimal("0.100000"),
        spread_percent=Decimal("0.332779"),
        observed_at=datetime.now(UTC),
    )
    db_session.add(snapshot)
    db_session.flush()
    signal = Signal(
        observed_at=snapshot.observed_at,
        price_snapshot_id=snapshot.id,
        action="HOLD",
        reason_code="BLENDED_NEUTRAL",
        price_usd_oz=snapshot.mid_price,
        details_json={},
    )
    db_session.add(signal)
    db_session.flush()
    return signal, collector_run


def test_runtime_heartbeat_upserts_and_trading_status_reports_why_no_trade(db_session):
    signal, collector_run = _seed_signal(db_session)
    record_runtime_heartbeat(db_session, component="auto_trader", expected_interval_seconds=900)
    record_runtime_heartbeat(db_session, component="auto_trader", status="ok", expected_interval_seconds=900)
    run = start_trading_decision_run(
        db_session,
        mode="diagnostic",
        asset_symbol="XAG_GRAM",
        strategy_name="blended",
        trigger_collector_run_id=collector_run.id,
    )
    finish_trading_decision_run(
        db_session,
        run,
        status="completed",
        action="HOLD",
        reason_code="BLENDED_NEUTRAL",
        signal_id=signal.id,
        source_health={"status": "ok"},
        indicator_readiness={"1d": {"status": "ready"}},
        execution_result={"status": "skipped", "skipped_reason": "diagnostic_mode", "trade_id": None},
        notification_result={"sent": False, "skipped_reason": "hold_cooldown"},
    )
    db_session.commit()

    payload = trading_status(db_session)

    assert payload["runtime"]["status"] == "ok"
    assert len(payload["runtime"]["heartbeats"]) == 1
    assert payload["latest_decision"]["reason_code"] == "BLENDED_NEUTRAL"
    assert payload["latest_decision"]["source_health"]["status"] == "ok"
    assert payload["why_no_trade"] == "BLENDED_NEUTRAL"


def test_runtime_routes_expose_decision_runs(db_session):
    signal, _collector_run = _seed_signal(db_session)
    run = start_trading_decision_run(
        db_session,
        mode="diagnostic",
        asset_symbol="XAG_GRAM",
        strategy_name="strategy_v2",
    )
    finish_trading_decision_run(
        db_session,
        run,
        status="completed",
        action="HOLD",
        reason_code="DAILY_TREND_MISSING",
        signal_id=signal.id,
        execution_result={"status": "skipped", "skipped_reason": "not_actionable", "trade_id": None},
        notification_result={"sent": True},
    )
    db_session.commit()

    app = create_app()

    def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    client = TestClient(app)

    status_response = client.get("/runtime/trading-status")
    runs_response = client.get("/runtime/decision-runs", params={"limit": 10})

    assert status_response.status_code == 200
    assert status_response.json()["latest_decision"]["reason_code"] == "DAILY_TREND_MISSING"
    assert runs_response.status_code == 200
    assert runs_response.json()["decision_runs"][0]["signal_id"] == signal.id

    proof_response = client.get("/runtime/proof-report", params={"window_days": 30})
    assert proof_response.status_code == 200
    proof_payload = proof_response.json()
    assert proof_payload["mode"] == "paper_proof"
    assert proof_payload["real_money_enabled"] is False
    assert proof_payload["block_reason_distribution"]["DAILY_TREND_MISSING"] == 1
    assert proof_payload["skipped_execution_distribution"]["not_actionable"] == 1

    client.close()
    app.dependency_overrides.clear()


def test_runtime_status_and_proof_report_surface_source_divergence_stale_block(db_session):
    signal, _collector_run = _seed_signal(db_session)
    run = start_trading_decision_run(
        db_session,
        mode="diagnostic",
        asset_symbol="XAG_GRAM",
        strategy_name="blended",
    )
    finish_trading_decision_run(
        db_session,
        run,
        status="completed",
        action="HOLD",
        reason_code="SOURCE_DIVERGENCE_STALE_DATA",
        signal_id=signal.id,
        execution_result={"status": "skipped", "skipped_reason": "diagnostic_mode", "trade_id": None},
        notification_result={"sent": True},
    )
    db_session.commit()

    status_payload = trading_status(db_session)
    assert status_payload["why_no_trade"] == "SOURCE_DIVERGENCE_STALE_DATA"
    assert status_payload["latest_critical_block"]["reason_code"] == "SOURCE_DIVERGENCE_STALE_DATA"
    assert status_payload["latest_decision"]["execution_result"]["skipped_reason"] == "diagnostic_mode"

    app = create_app()

    def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    client = TestClient(app)
    status_response = client.get("/runtime/trading-status")
    proof_response = client.get("/runtime/proof-report", params={"window_days": 30})

    assert status_response.status_code == 200
    assert status_response.json()["latest_critical_block"]["reason_code"] == "SOURCE_DIVERGENCE_STALE_DATA"
    assert proof_response.status_code == 200
    proof_payload = proof_response.json()
    assert proof_payload["block_reason_distribution"]["SOURCE_DIVERGENCE_STALE_DATA"] == 1
    assert proof_payload["skipped_execution_distribution"]["diagnostic_mode"] == 1
    assert proof_payload["acceptance_gate"]["critical_block_48h"] is True

    client.close()
    app.dependency_overrides.clear()


def test_runtime_status_and_proof_report_surface_non_executed_actions(db_session):
    signal, _collector_run = _seed_signal(db_session)
    run = start_trading_decision_run(
        db_session,
        mode="diagnostic",
        asset_symbol="XAG_GRAM",
        strategy_name="strategy_v2",
    )
    finish_trading_decision_run(
        db_session,
        run,
        status="completed",
        action="BUY",
        reason_code="STRATEGY_V2_BUY_CONFIRMED",
        signal_id=signal.id,
        execution_result={"status": "skipped", "skipped_reason": "diagnostic_mode", "trade_id": None},
        notification_result={"sent": True},
    )
    db_session.commit()

    status_payload = trading_status(db_session)
    assert status_payload["why_no_trade"] == "diagnostic_mode"
    assert status_payload["latest_decision"]["execution_result"]["skipped_reason"] == "diagnostic_mode"

    app = create_app()

    def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    client = TestClient(app)
    proof_response = client.get("/runtime/proof-report", params={"window_days": 30})
    assert proof_response.status_code == 200
    proof_payload = proof_response.json()
    assert proof_payload["skipped_execution_distribution"]["diagnostic_mode"] == 1
    assert proof_payload["acceptance_gate"]["non_executed_actions_48h"] is True
    assert proof_payload["acceptance_gate"]["non_executed_action_distribution"]["diagnostic_mode"] == 1

    client.close()
    app.dependency_overrides.clear()


def test_telegram_sistem_command_uses_runtime_status(db_session):
    signal, _collector_run = _seed_signal(db_session)
    record_runtime_heartbeat(db_session, component="auto_trader", expected_interval_seconds=900)
    run = start_trading_decision_run(
        db_session,
        mode="diagnostic",
        asset_symbol="XAG_GRAM",
        strategy_name="blended",
    )
    finish_trading_decision_run(
        db_session,
        run,
        status="completed",
        action="HOLD",
        reason_code="BLENDED_NEUTRAL",
        signal_id=signal.id,
        execution_result={"status": "skipped", "skipped_reason": "diagnostic_mode", "trade_id": None},
        notification_result={"sent": False, "skipped_reason": "hold_cooldown"},
    )
    db_session.commit()

    text = handle_telegram_command("/sistem", db_session)

    assert "SilverPilot Sistem Özeti" in text
    assert "BLENDED_NEUTRAL" in text
    assert "Auto-trader heartbeat" in text
