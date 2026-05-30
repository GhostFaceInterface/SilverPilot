from datetime import UTC, datetime, timedelta
from decimal import Decimal
from types import SimpleNamespace
import time

from fastapi.testclient import TestClient
import httpx
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.collectors.public_sources import (
    collect_fed_rss,
    collect_fred_macro,
    collect_global_xag_usd,
    collect_kuveyt_public_silver,
    collect_yahoo_usd_try,
    collect_tcmb_usd_try,
    discover_kuveyt_core_script_url,
    parse_fed_rss,
    parse_fred_observations,
    parse_kuveyt_finance_portal_endpoint,
    parse_kuveyt_finance_portal_json,
    parse_kuveyt_finance_portal_json_usd_try,
    collect_kuveyt_usd_try,
    parse_kuveyt_public_silver_html,
)
from app.collectors.service import ingest_fx_rate
from app.collectors.runner import parse_collector_jobs, run_jobs
from app.core.config import Settings
from app.core.db import Base, get_db
from app.main import create_app
from app.models import Asset, CollectorRun, PriceSnapshot, RawBankPrice, RawEvent, RawFxRate, RawGlobalPrice, RawNews


def make_client():
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    testing_session = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    Base.metadata.create_all(bind=engine)

    db = testing_session()
    db.add(Asset(symbol="XAG", name="Silver", asset_type="metal", is_active=True))
    db.commit()
    db.close()

    def override_get_db():
        session = testing_session()
        try:
            yield session
        finally:
            session.close()

    app = create_app()
    app.dependency_overrides[get_db] = override_get_db
    return TestClient(app), testing_session


def seed_fresh_global_xag_and_usd_try(testing_session, *, now: datetime | None = None) -> None:
    now = now or datetime.now(UTC)
    db = testing_session()
    try:
        asset = db.execute(select(Asset).where(Asset.symbol == "XAG")).scalar_one()
        global_run = CollectorRun(
            collector_name="global_xag_usd",
            source="yahoo-si-f",
            status="success",
            records_seen=1,
            records_inserted=1,
            duplicates=0,
            started_at=now - timedelta(minutes=10),
            finished_at=now - timedelta(minutes=10),
            details_json={},
        )
        fx_run = CollectorRun(
            collector_name="yahoo_usd_try",
            source="yahoo-usd-try",
            status="success",
            records_seen=1,
            records_inserted=1,
            duplicates=0,
            started_at=now - timedelta(minutes=10),
            finished_at=now - timedelta(minutes=10),
            details_json={},
        )
        db.add_all([global_run, fx_run])
        db.flush()
        db.add(
            RawGlobalPrice(
                collector_run_id=global_run.id,
                asset_id=asset.id,
                source="yahoo-si-f",
                buy_price=Decimal("78.00"),
                sell_price=Decimal("78.00"),
                currency="USD",
                observed_at=now - timedelta(minutes=10),
                fetched_at=now - timedelta(minutes=10),
                raw_payload_hash="test-global",
                parser_version="yahoo-finance-chart-v1",
                payload_json={},
            )
        )
        db.add(
            RawFxRate(
                collector_run_id=fx_run.id,
                source="yahoo-usd-try",
                base_currency="USD",
                quote_currency="TRY",
                rate=Decimal("38.75"),
                observed_at=now - timedelta(minutes=10),
                fetched_at=now - timedelta(minutes=10),
                raw_payload_hash="test-fx",
                parser_version="yahoo-finance-chart-v1",
                payload_json={},
            )
        )
        db.commit()
    finally:
        db.close()


def seed_fresh_bank_price(testing_session, *, now: datetime | None = None) -> None:
    now = now or datetime.now(UTC)
    db = testing_session()
    try:
        asset = db.execute(select(Asset).where(Asset.symbol == "XAG")).scalar_one()
        run = CollectorRun(
            collector_name="kuveyt_public_silver",
            source="kuveyt-public-silver-page",
            status="success",
            records_seen=1,
            records_inserted=1,
            duplicates=0,
            started_at=now - timedelta(minutes=10),
            finished_at=now - timedelta(minutes=10),
            details_json={},
        )
        db.add(run)
        db.flush()
        db.add(
            RawBankPrice(
                collector_run_id=run.id,
                asset_id=asset.id,
                source="kuveyt-public-silver-page",
                buy_price=Decimal("130.00"),
                sell_price=Decimal("126.00"),
                currency="TRY",
                observed_at=now - timedelta(minutes=10),
                fetched_at=now - timedelta(minutes=10),
                raw_payload_hash="test-bank",
                parser_version="kuveyt-public-finance-portal-v2",
                payload_json={},
            )
        )
        db.commit()
    finally:
        db.close()


def test_manual_bank_price_ingest_writes_raw_and_normalized_rows():
    client, testing_session = make_client()

    response = client.post(
        "/collectors/manual-price",
        json={
            "source_type": "bank",
            "source": "manual-test-bank",
            "asset_symbol": "XAG",
            "buy_price": "10.00",
            "sell_price": "9.80",
            "currency": "USD",
            "observed_at": "2026-05-13T12:00:00Z",
            "payload": {"sample": True},
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["raw_inserted"] is True
    assert body["collector_run"]["status"] == "success"
    assert body["collector_run"]["records_seen"] == 1
    assert body["collector_run"]["records_inserted"] == 1
    assert body["price_snapshot"]["mid_price"] == "9.900000"
    assert body["price_snapshot"]["spread_absolute"] == "0.200000"

    db = testing_session()
    try:
        assert db.query(CollectorRun).count() == 1
        raw = db.query(RawBankPrice).one()
        assert raw.raw_payload_hash
        assert raw.parser_version == "manual-v1"
        assert db.query(PriceSnapshot).count() == 1
    finally:
        db.close()


def test_manual_price_duplicate_is_counted_without_new_snapshot():
    client, testing_session = make_client()
    payload = {
        "source_type": "bank",
        "source": "manual-test-bank",
        "asset_symbol": "XAG",
        "buy_price": "10.00",
        "sell_price": "9.80",
        "currency": "USD",
        "observed_at": "2026-05-13T12:00:00Z",
        "payload": {},
    }

    first = client.post("/collectors/manual-price", json=payload)
    second = client.post("/collectors/manual-price", json=payload)

    assert first.status_code == 200
    assert second.status_code == 200
    assert second.json()["raw_inserted"] is False
    assert second.json()["collector_run"]["duplicates"] == 1
    assert second.json()["price_snapshot"] is None

    db = testing_session()
    try:
        assert db.query(CollectorRun).count() == 2
        assert db.query(RawBankPrice).count() == 1
        assert db.query(PriceSnapshot).count() == 1
    finally:
        db.close()


def test_manual_price_rejects_inverted_spread():
    client, _ = make_client()

    response = client.post(
        "/collectors/manual-price",
        json={
            "source_type": "bank",
            "source": "manual-test-bank",
            "asset_symbol": "XAG",
            "buy_price": "9.80",
            "sell_price": "10.00",
            "currency": "USD",
            "observed_at": "2026-05-13T12:00:00Z",
        },
    )

    assert response.status_code == 422


def test_collector_health_reports_empty_without_runs():
    client, _ = make_client()

    response = client.get("/collectors/health")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "empty"
    assert body["execution_critical_status"] == "blocked"
    assert body["context_status"] == "empty"
    assert body["execution_critical"]["bank_price"] == "missing"
    assert body["execution_critical"]["global_xag_usd"] == "missing"
    assert body["execution_critical"]["usd_try"] == "missing"
    assert body["collectors"] == []


def test_collector_health_reports_manual_bank_price_as_degraded_fallback():
    client, testing_session = make_client()
    seed_fresh_global_xag_and_usd_try(testing_session)
    client.post(
        "/collectors/manual-price",
        json={
            "source_type": "bank",
            "source": "manual-test-bank",
            "asset_symbol": "XAG",
            "buy_price": "10.00",
            "sell_price": "9.80",
            "currency": "USD",
            "observed_at": "2026-05-13T12:00:00Z",
        },
    )

    response = client.get("/collectors/health?stale_after_minutes=60")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "degraded"
    assert body["execution_critical_status"] == "degraded"
    assert body["execution_critical"]["bank_price"] == "manual_fallback"
    assert body["execution_critical"]["manual_fallback"] is True
    assert body["collectors"][0]["collector_name"] == "manual_bank_price"
    assert body["collectors"][0]["source"] == "manual-test-bank"
    assert body["collectors"][0]["stale"] is False


def test_collector_health_ignores_stale_manual_when_official_bank_price_is_fresh():
    client, testing_session = make_client()
    seed_fresh_global_xag_and_usd_try(testing_session)
    client.post(
        "/collectors/manual-price",
        json={
            "source_type": "bank",
            "source": "manual-test-bank",
            "asset_symbol": "XAG",
            "buy_price": "10.00",
            "sell_price": "9.80",
            "currency": "USD",
            "observed_at": "2026-05-13T12:00:00Z",
        },
    )

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/canli-gumus-fiyatlari-ve-gram-gumus-hesaplama"):
            return httpx.Response(200, text='<script src="/magiclick.core.min.js?v=abc"></script>')
        if request.url.path == "/magiclick.core.min.js":
            return httpx.Response(200, text='const ApiEndpoints={financePortal:"/ck0d84?financePortal"};')
        if request.url.path == "/ck0d84":
            return httpx.Response(
                200,
                json=[
                    {"Title": "GMS (gr)", "CurrencyDescription": "Gümüş", "BuyRate": 125.0, "SellRate": 129.0},
                ],
            )
        return httpx.Response(404)

    mock_client = httpx.Client(transport=httpx.MockTransport(handler))
    db = testing_session()
    try:
        collect_kuveyt_public_silver(db, settings=Settings(), client=mock_client)
    finally:
        mock_client.close()
        db.close()

    response = client.get("/collectors/health?stale_after_minutes=60")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "healthy"
    assert body["execution_critical_status"] == "healthy"
    assert body["execution_critical"]["bank_price"] == "fresh"
    assert body["execution_critical"]["source"] == "kuveyt-public-silver-page"


def test_collector_health_rejects_invalid_stale_threshold():
    client, _ = make_client()

    response = client.get("/collectors/health?stale_after_minutes=0")

    assert response.status_code == 400


def test_collector_quality_reports_missing_and_duplicate_ratios():
    client, _ = make_client()
    payload = {
        "source_type": "bank",
        "source": "manual-test-bank",
        "asset_symbol": "XAG",
        "buy_price": "10.00",
        "sell_price": "9.80",
        "currency": "USD",
        "observed_at": "2026-05-13T12:00:00Z",
        "payload": {},
    }
    client.post("/collectors/manual-price", json=payload)
    client.post("/collectors/manual-price", json=payload)

    response = client.get("/collectors/quality?window_hours=2&expected_interval_minutes=60")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["expected_runs_per_collector"] == 2
    assert body["expected_runs_so_far_per_collector"] == 1
    assert body["validation_window_complete"] is False
    assert body["collectors"][0]["runs"] == 2
    assert body["collectors"][0]["duplicates"] == 1
    assert body["collectors"][0]["duplicate_ratio"] == 0.5
    assert body["collectors"][0]["missing_ratio"] == 0.0


def test_collector_quality_does_not_count_future_validation_window_as_missing():
    client, _ = make_client()
    payload = {
        "source_type": "bank",
        "source": "manual-test-bank",
        "asset_symbol": "XAG",
        "buy_price": "10.00",
        "sell_price": "9.80",
        "currency": "USD",
        "observed_at": "2026-05-13T12:00:00Z",
        "payload": {},
    }
    client.post("/collectors/manual-price", json=payload)

    response = client.get("/collectors/quality?window_hours=24&expected_interval_minutes=60")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["expected_runs_per_collector"] == 24
    assert body["expected_runs_so_far_per_collector"] == 1
    assert body["validation_window_complete"] is False
    assert body["collectors"][0]["missing_runs"] == 0
    assert body["collectors"][0]["missing_ratio"] == 0.0


def test_collector_quality_completes_after_continuous_history_exceeds_sliding_window():
    client, testing_session = make_client()
    now = datetime.now(UTC)
    db = testing_session()
    try:
        db.add(
            CollectorRun(
                collector_name="kuveyt_public_silver",
                source="kuveyt-public-silver-page",
                status="success",
                records_seen=1,
                records_inserted=1,
                duplicates=0,
                started_at=now - timedelta(minutes=90),
                finished_at=now - timedelta(minutes=90),
                details_json={},
            )
        )
        for minutes_ago in (45, 30, 15, 1):
            db.add(
                CollectorRun(
                    collector_name="kuveyt_public_silver",
                    source="kuveyt-public-silver-page",
                    status="success",
                    records_seen=1,
                    records_inserted=1,
                    duplicates=0,
                    started_at=now - timedelta(minutes=minutes_ago),
                    finished_at=now - timedelta(minutes=minutes_ago),
                    details_json={},
                )
            )
        db.commit()
    finally:
        db.close()

    response = client.get("/collectors/quality?window_hours=1&expected_interval_minutes=15")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["elapsed_minutes"] == 60
    assert body["validation_window_complete"] is True
    assert body["expected_runs_so_far_per_collector"] == 4
    assert body["collectors"][0]["runs"] == 4
    assert body["collectors"][0]["missing_runs"] == 0


def test_collector_quality_excludes_inactive_manual_fallback_when_public_collector_exists():
    client, testing_session = make_client()
    payload = {
        "source_type": "bank",
        "source": "manual-test-bank",
        "asset_symbol": "XAG",
        "buy_price": "10.00",
        "sell_price": "9.80",
        "currency": "USD",
        "observed_at": "2026-05-13T12:00:00Z",
        "payload": {},
    }
    client.post("/collectors/manual-price", json=payload)
    now = datetime.now(UTC)
    db = testing_session()
    db.add(
        CollectorRun(
            collector_name="kuveyt_public_silver",
            source="kuveyt-public-silver-page",
            status="success",
            records_seen=1,
            records_inserted=1,
            duplicates=0,
            started_at=now,
            finished_at=now,
            details_json={},
        )
    )
    db.commit()
    db.close()

    response = client.get("/collectors/quality?window_hours=1&expected_interval_minutes=60")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert [item["collector_name"] for item in body["collectors"]] == ["kuveyt_public_silver"]


def test_collector_quality_rejects_invalid_window():
    client, _ = make_client()

    response = client.get("/collectors/quality?window_hours=0")

    assert response.status_code == 400


def test_collector_validation_gate_reports_empty_without_runs():
    client, _ = make_client()

    response = client.get("/collectors/validation-gate")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "empty"
    assert body["phase4_allowed"] is False
    assert "EXECUTION_CRITICAL_BANK_PRICE_NOT_FRESH" in body["blocking_reasons"]
    assert "EXECUTION_CRITICAL_GLOBAL_XAG_NOT_FRESH" in body["blocking_reasons"]
    assert "EXECUTION_CRITICAL_USD_TRY_NOT_FRESH" in body["blocking_reasons"]


def test_collector_validation_gate_reports_warming_up_before_window_completes():
    client, testing_session = make_client()
    now = datetime.now(UTC)
    seed_fresh_global_xag_and_usd_try(testing_session, now=now)
    db = testing_session()
    asset = db.execute(select(Asset).where(Asset.symbol == "XAG")).scalar_one()
    run = CollectorRun(
        collector_name="kuveyt_public_silver",
        source="kuveyt-public-silver-page",
        status="success",
        records_seen=1,
        records_inserted=1,
        duplicates=0,
        started_at=now - timedelta(minutes=10),
        finished_at=now - timedelta(minutes=10),
        details_json={},
    )
    db.add(run)
    db.flush()
    db.add(
        RawBankPrice(
            collector_run_id=run.id,
            asset_id=asset.id,
            source="kuveyt-public-silver-page",
            buy_price=Decimal("130.00"),
            sell_price=Decimal("126.00"),
            currency="TRY",
            observed_at=now - timedelta(minutes=10),
            fetched_at=now - timedelta(minutes=10),
            raw_payload_hash="test",
            parser_version="kuveyt-public-finance-portal-v2",
            payload_json={},
        )
    )
    db.commit()
    db.close()

    response = client.get("/collectors/validation-gate?window_hours=24&expected_interval_minutes=15")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "warming_up"
    assert body["health_status"] == "healthy"
    assert body["quality_status"] == "ok"
    assert body["phase4_allowed"] is False
    assert body["validation_window_complete"] is False
    assert body["reasons"] == ["VALIDATION_WINDOW_INCOMPLETE"]


def test_runner_parse_collector_jobs_uses_comma_list_or_fallback():
    assert parse_collector_jobs("", fallback_job="manual") == ["manual"]
    assert parse_collector_jobs("kuveyt-silver, yahoo-usd-try", fallback_job="manual") == [
        "kuveyt-silver",
        "yahoo-usd-try",
    ]


def test_runner_parse_collector_jobs_rejects_unknown_job():
    try:
        parse_collector_jobs("kuveyt-silver,unknown", fallback_job="manual")
    except ValueError as exc:
        assert "unknown" in str(exc)
    else:
        raise AssertionError("unknown collector job should be rejected")


def test_runner_reports_failed_collector_job(monkeypatch):
    class FakeDb:
        def close(self):
            return None

    failed_run = SimpleNamespace(id=1, status="failed")
    monkeypatch.setattr("app.collectors.runner.SessionLocal", lambda: FakeDb())
    monkeypatch.setattr(
        "app.collectors.runner.collect_kuveyt_public_silver",
        lambda db: (failed_run, False, None),
    )
    args = SimpleNamespace(job="kuveyt-silver", jobs="")

    assert run_jobs(args) is False


def test_yahoo_xag_usd_collector_writes_global_price_and_snapshot():
    _, testing_session = make_client()
    observed_at = datetime.now(UTC) - timedelta(minutes=1)
    observed_timestamp = int(observed_at.timestamp())

    yahoo_json = {
        "chart": {
            "result": [
                {
                    "meta": {"symbol": "SI=F", "currency": "USD"},
                    "timestamp": [observed_timestamp],
                    "indicators": {
                        "quote": [
                            {"close": [28.45], "open": [28.40], "high": [28.50], "low": [28.35], "volume": [1000]}
                        ]
                    },
                }
            ],
            "error": None,
        }
    }

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=yahoo_json)

    client = httpx.Client(transport=httpx.MockTransport(handler))
    db = testing_session()
    try:
        run, raw_inserted, snapshot = collect_global_xag_usd(
            db,
            settings=Settings(global_xag_source_priority="yahoo-si-f"),
            client=client,
        )

        assert run.status == "success"
        assert raw_inserted is True
        assert snapshot is not None
        assert str(snapshot.mid_price) == "28.450000"
        raw = db.query(RawGlobalPrice).one()
        assert raw.source == "yahoo-si-f"
        assert raw.raw_payload_hash
        assert raw.parser_version == "yahoo-finance-chart-v1"
    finally:
        client.close()
        db.close()


def test_yahoo_timeout_does_not_write_fake_global_price():
    _, testing_session = make_client()

    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("timed out", request=request)

    client = httpx.Client(transport=httpx.MockTransport(handler))
    db = testing_session()
    try:
        run, raw_inserted, snapshot = collect_global_xag_usd(
            db,
            settings=Settings(
                global_xag_source_priority="yahoo-si-f",
                yahoo_xag_usd_retries=0,
                yahoo_xag_usd_backoff_seconds=0,
            ),
            client=client,
        )

        assert run.status == "failed"
        assert raw_inserted is False
        assert snapshot is None
        assert db.query(RawGlobalPrice).count() == 0
        assert db.query(PriceSnapshot).count() == 0
    finally:
        client.close()
        db.close()


def test_global_xag_fallback_uses_metals_dev_when_yahoo_times_out():
    _, testing_session = make_client()
    observed_at = datetime.now(UTC) - timedelta(minutes=1)

    def handler(request: httpx.Request) -> httpx.Response:
        if "SI=F" in str(request.url):
            raise httpx.ReadTimeout("timed out", request=request)
        return httpx.Response(
            200,
            json={
                "status": "success",
                "rate": {
                    "price": 28.55,
                },
                "timestamp": observed_at.isoformat(),
                "currency": "USD",
            },
        )

    client = httpx.Client(transport=httpx.MockTransport(handler))
    db = testing_session()
    try:
        run, raw_inserted, snapshot = collect_global_xag_usd(
            db,
            settings=Settings(
                global_xag_source_priority="yahoo-si-f,metals-dev",
                yahoo_xag_usd_retries=0,
                yahoo_xag_usd_backoff_seconds=0,
                metals_dev_api_key="test-key",
            ),
            client=client,
        )

        assert run.status == "success"
        assert raw_inserted is True
        assert snapshot is not None
        assert run.details_json["selected_global_xag_source"] == "metals-dev-silver-spot"
        assert db.query(RawGlobalPrice).one().source == "metals-dev-silver-spot"
        failed_yahoo = db.execute(
            select(CollectorRun).where(CollectorRun.collector_name == "yahoo_xag_usd")
        ).scalar_one()
        assert failed_yahoo.status == "failed"
        assert failed_yahoo.details_json["failure_reason_code"] == "TIMEOUT"
    finally:
        client.close()
        db.close()


def test_gold_api_xag_usd_collector_writes_global_price_and_snapshot():
    _, testing_session = make_client()
    observed_at = datetime.now(UTC) - timedelta(minutes=1)

    gold_json = {
        "currency": "USD",
        "currencySymbol": "$",
        "exchangeRate": 1.0,
        "name": "Silver",
        "price": 28.55,
        "symbol": "XAG",
        "updatedAt": observed_at.isoformat().replace("+00:00", "Z"),
    }

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=gold_json)

    client = httpx.Client(transport=httpx.MockTransport(handler))
    db = testing_session()
    try:
        run, raw_inserted, snapshot = collect_global_xag_usd(
            db,
            settings=Settings(global_xag_source_priority="gold-api-xag-usd"),
            client=client,
        )

        assert run.status == "success"
        assert raw_inserted is True
        assert snapshot is not None
        assert str(snapshot.mid_price) == "28.550000"
        raw = db.query(RawGlobalPrice).one()
        assert raw.source == "gold-api-xag-usd"
        assert raw.raw_payload_hash
        assert raw.parser_version == "gold-api-xag-usd-v1"
    finally:
        client.close()
        db.close()


def test_global_xag_fallback_uses_gold_api_when_yahoo_fails():
    _, testing_session = make_client()
    observed_at = datetime.now(UTC) - timedelta(minutes=1)

    def handler(request: httpx.Request) -> httpx.Response:
        if "SI=F" in str(request.url):
            # Simulate blocked IP: returns non-JSON HTML with 200 OK
            return httpx.Response(200, text="<html>Blocked by Yahoo Finance consent portal</html>")
        return httpx.Response(
            200,
            json={
                "currency": "USD",
                "price": 28.60,
                "symbol": "XAG",
                "updatedAt": observed_at.isoformat().replace("+00:00", "Z"),
            },
        )

    client = httpx.Client(transport=httpx.MockTransport(handler))
    db = testing_session()
    try:
        run, raw_inserted, snapshot = collect_global_xag_usd(
            db,
            settings=Settings(
                global_xag_source_priority="yahoo-si-f,gold-api-xag-usd",
                yahoo_xag_usd_retries=0,
                yahoo_xag_usd_backoff_seconds=0,
            ),
            client=client,
        )

        assert run.status == "success"
        assert raw_inserted is True
        assert snapshot is not None
        assert run.details_json["selected_global_xag_source"] == "gold-api-xag-usd"
        assert db.query(RawGlobalPrice).one().source == "gold-api-xag-usd"
        failed_yahoo = db.execute(
            select(CollectorRun).where(CollectorRun.collector_name == "yahoo_xag_usd")
        ).scalar_one()
        assert failed_yahoo.status == "failed"
        assert failed_yahoo.details_json["failure_reason_code"] == "PARSE_ERROR"
    finally:
        client.close()
        db.close()


def test_yahoo_usd_try_collector_writes_fx_rate():
    _, testing_session = make_client()
    observed_at = datetime.now(UTC) - timedelta(minutes=1)
    observed_timestamp = int(observed_at.timestamp())

    yahoo_json = {
        "chart": {
            "result": [
                {
                    "meta": {"symbol": "USDTRY=X", "currency": "TRY"},
                    "timestamp": [observed_timestamp],
                    "indicators": {"quote": [{"close": [32.50]}]},
                }
            ],
            "error": None,
        }
    }

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=yahoo_json)

    client = httpx.Client(transport=httpx.MockTransport(handler))
    db = testing_session()
    try:
        run, raw_inserted = collect_yahoo_usd_try(db, settings=Settings(), client=client)

        assert run.status == "success"
        assert raw_inserted is True
        raw = db.query(RawFxRate).one()
        assert raw.source == "yahoo-usd-try"
        assert raw.base_currency == "USD"
        assert raw.quote_currency == "TRY"
        assert str(raw.rate) == "32.500000"
        assert raw.raw_payload_hash
        assert raw.parser_version == "yahoo-finance-chart-v1"
    finally:
        client.close()
        db.close()


def test_validation_gate_blocks_when_global_xag_is_missing():
    client, testing_session = make_client()
    seed_fresh_bank_price(testing_session)
    db = testing_session()
    try:
        now = datetime.now(UTC)
        run = CollectorRun(
            collector_name="tcmb_usd_try",
            source="tcmb-today-xml",
            status="success",
            records_seen=1,
            records_inserted=1,
            duplicates=0,
            started_at=now - timedelta(minutes=10),
            finished_at=now - timedelta(minutes=10),
            details_json={},
        )
        db.add(run)
        db.flush()
        db.add(
            RawFxRate(
                collector_run_id=run.id,
                source="tcmb-today-xml",
                base_currency="USD",
                quote_currency="TRY",
                rate=Decimal("38.75"),
                observed_at=now - timedelta(minutes=10),
                fetched_at=now - timedelta(minutes=10),
                raw_payload_hash="test-fx",
                parser_version="tcmb-today-xml-v1",
                payload_json={},
            )
        )
        db.commit()
    finally:
        db.close()

    response = client.get("/collectors/validation-gate?window_hours=1&expected_interval_minutes=60")

    assert response.status_code == 200
    body = response.json()
    assert body["phase4_allowed"] is False
    assert body["status"] == "blocked"
    assert "EXECUTION_CRITICAL_GLOBAL_XAG_NOT_FRESH" in body["blocking_reasons"]


def test_context_failure_does_not_block_phase4_when_critical_sources_are_ready():
    client, testing_session = make_client()
    now = datetime.now(UTC)
    seed_fresh_bank_price(testing_session, now=now)
    seed_fresh_global_xag_and_usd_try(testing_session, now=now)
    db = testing_session()
    try:
        for collector_name, source in (
            ("kuveyt_public_silver", "kuveyt-public-silver-page"),
            ("global_xag_usd", "yahoo-si-f"),
            ("tcmb_usd_try", "yahoo-usd-try"),
        ):
            db.add(
                CollectorRun(
                    collector_name=collector_name,
                    source=source,
                    status="success",
                    records_seen=1,
                    records_inserted=1,
                    duplicates=0,
                    started_at=now - timedelta(minutes=61),
                    finished_at=now - timedelta(minutes=61),
                    details_json={},
                )
            )
        db.add(
            CollectorRun(
                collector_name="fed_rss",
                source="federal-reserve-rss",
                status="failed",
                records_seen=0,
                records_inserted=0,
                duplicates=0,
                started_at=now - timedelta(minutes=10),
                finished_at=now - timedelta(minutes=10),
                error_message="transient context failure",
                details_json={},
            )
        )
        db.commit()
    finally:
        db.close()

    response = client.get("/collectors/validation-gate?window_hours=1&expected_interval_minutes=60")

    assert response.status_code == 200
    body = response.json()
    assert body["phase4_allowed"] is True
    assert body["status"] == "ready"
    assert "CONTEXT_COLLECTOR_FAILURES_PRESENT" in body["degraded_reasons"]


def test_tcmb_usd_try_collector_writes_fx_rate():
    _, testing_session = make_client()
    xml = """<?xml version="1.0" encoding="UTF-8"?>
<Tarih_Date Tarih="12.05.2026">
  <Currency CurrencyCode="USD">
    <ForexBuying>38.7000</ForexBuying>
    <ForexSelling>38.8000</ForexSelling>
  </Currency>
</Tarih_Date>
"""

    client = httpx.Client(transport=httpx.MockTransport(lambda request: httpx.Response(200, text=xml)))
    db = testing_session()
    try:
        run, raw_inserted = collect_tcmb_usd_try(db, settings=Settings(), client=client)

        assert run.status == "success"
        assert raw_inserted is True
        raw = db.query(RawFxRate).one()
        assert raw.source == "tcmb-today-xml"
        assert raw.base_currency == "USD"
        assert raw.quote_currency == "TRY"
        assert str(raw.rate) == "38.750000"
        assert raw.raw_payload_hash
        assert raw.parser_version == "tcmb-today-xml-v1"
    finally:
        client.close()
        db.close()


def test_fed_rss_parser_reads_items():
    items = parse_fed_rss(
        """<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0">
  <channel>
    <title>Federal Reserve</title>
    <item>
      <title>Federal Reserve issues FOMC statement</title>
      <link>https://www.federalreserve.gov/newsevents/pressreleases/monetary20260513a.htm</link>
      <guid>monetary20260513a</guid>
      <pubDate>Wed, 13 May 2026 18:00:00 GMT</pubDate>
      <description>Policy statement.</description>
      <category>Monetary Policy</category>
    </item>
  </channel>
</rss>
"""
    )

    assert len(items) == 1
    assert items[0].title == "Federal Reserve issues FOMC statement"
    assert items[0].url.endswith("monetary20260513a.htm")
    assert items[0].published_at == datetime(2026, 5, 13, 18, 0, tzinfo=UTC)
    assert items[0].payload["categories"] == ["Monetary Policy"]


def test_fed_rss_collector_writes_news_items_and_counts_duplicates():
    _, testing_session = make_client()
    rss = """<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0">
  <channel>
    <title>Federal Reserve</title>
    <item>
      <title>Federal Reserve issues FOMC statement</title>
      <link>https://www.federalreserve.gov/newsevents/pressreleases/monetary20260513a.htm</link>
      <guid>monetary20260513a</guid>
      <pubDate>Wed, 13 May 2026 18:00:00 GMT</pubDate>
      <description>Policy statement.</description>
    </item>
  </channel>
</rss>
"""

    client = httpx.Client(transport=httpx.MockTransport(lambda request: httpx.Response(200, text=rss)))
    db = testing_session()
    try:
        first_run, first_inserted = collect_fed_rss(db, settings=Settings(), client=client)
        second_run, second_inserted = collect_fed_rss(db, settings=Settings(), client=client)

        assert first_run.status == "success"
        assert first_inserted == 1
        assert second_run.status == "success"
        assert second_inserted == 0
        assert second_run.duplicates == 1
        raw = db.query(RawNews).one()
        assert raw.source == "federal-reserve-rss"
        assert raw.raw_payload_hash
        assert raw.parser_version == "fed-rss-v1"
        assert raw.payload_json["source_type"] == "official_rss"
    finally:
        client.close()
        db.close()


def test_fred_observations_parser_skips_missing_latest_value():
    parsed = parse_fred_observations(
        """
{
  "observations": [
    {"realtime_start": "2026-05-13", "realtime_end": "2026-05-13", "date": "2026-05-01", "value": "."},
    {"realtime_start": "2026-05-13", "realtime_end": "2026-05-13", "date": "2026-04-01", "value": "2.45"}
  ]
}
""",
        series_id="DGS10",
    )

    assert parsed.series_id == "DGS10"
    assert parsed.value == Decimal("2.45")
    assert parsed.observed_at == datetime(2026, 4, 1, tzinfo=UTC)
    assert parsed.payload["missing_value_semantics"] == "dot_values_skipped"


def test_fred_macro_collector_writes_raw_events_and_counts_duplicates():
    _, testing_session = make_client()

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.headers["user-agent"].startswith("SilverPilot/")
        assert request.url.params["api_key"] == "test-fred-key"
        series_id = request.url.params["series_id"]
        payload = {
            "observations": [
                {
                    "realtime_start": "2026-05-13",
                    "realtime_end": "2026-05-13",
                    "date": "2026-04-01",
                    "value": "3.10" if series_id == "CPIAUCSL" else "4.20",
                }
            ]
        }
        return httpx.Response(200, json=payload)

    client = httpx.Client(transport=httpx.MockTransport(handler))
    db = testing_session()
    settings = Settings(fred_api_key="test-fred-key", fred_series_ids="CPIAUCSL,DGS10")
    try:
        first_run, first_inserted = collect_fred_macro(db, settings=settings, client=client)
        second_run, second_inserted = collect_fred_macro(db, settings=settings, client=client)

        assert first_run.status == "success"
        assert first_inserted == 2
        assert second_run.status == "success"
        assert second_inserted == 0
        assert second_run.duplicates == 2
        rows = db.query(RawEvent).all()
        assert len(rows) == 2
        assert {row.payload_json["series_id"] for row in rows} == {"CPIAUCSL", "DGS10"}
        assert {row.event_type for row in rows} == {"fred_macro_observation"}
        assert all(row.source == "fred-api" for row in rows)
        assert all(row.raw_payload_hash for row in rows)
        assert all(row.parser_version == "fred-observations-v1" for row in rows)
    finally:
        client.close()
        db.close()


def test_kuveyt_public_silver_parser_maps_bank_spread_to_user_prices():
    parsed = parse_kuveyt_public_silver_html(
        """
        <html>
          <body>
            <span>Gram Gümüş Alış</span><strong>42,10</strong>
            <span>Gram Gümüş Satış</span><strong>43,25</strong>
          </body>
        </html>
        """,
        fetched_at=datetime(2026, 5, 13, 12, 0, tzinfo=UTC),
    )

    assert parsed.currency == "TRY"
    assert parsed.buy_price == Decimal("43.25")
    assert parsed.sell_price == Decimal("42.10")


def test_kuveyt_finance_portal_parser_reads_gms_json():
    parsed = parse_kuveyt_finance_portal_json(
        """
[
  {"Title":"USD","CurrencyCode":"USD","BuyRate":44.1,"SellRate":45.2},
  {"Title":"GMS (gr)","CurrencyCode":"GMS (gr)","CurrencyDescription":"Gümüş","BuyRate":125.87879,"SellRate":129.63761,"ChangeRate":3.46,"ChangeRateNegative":false}
]
""",
        fetched_at=datetime(2026, 5, 13, 12, 0, tzinfo=UTC),
        finance_portal_url="https://www.kuveytturk.com.tr/ck0d84?public",
    )

    assert parsed.currency == "TRY"
    assert parsed.buy_price == Decimal("129.63761")
    assert parsed.sell_price == Decimal("125.87879")
    assert parsed.observed_at == datetime(2026, 5, 13, 12, 0, tzinfo=UTC)
    assert parsed.payload["source_type"] == "official_public_browser_loaded_json"
    assert parsed.payload["timestamp_semantics"] == "no source timestamp in response; observed_at uses fetched_at"


def test_kuveyt_discovery_reads_public_script_and_endpoint():
    page = '<script src="/magiclick.core.min.js?v=abc"></script>'
    script_url = discover_kuveyt_core_script_url(page, base_url="https://www.kuveytturk.com.tr/path/page")
    endpoint_url = parse_kuveyt_finance_portal_endpoint(
        'const ApiEndpoints={financePortal:"ck0d84?B83A"};',
        base_url="https://www.kuveytturk.com.tr/path/page",
    )

    assert script_url == "https://www.kuveytturk.com.tr/magiclick.core.min.js?v=abc"
    assert endpoint_url == "https://www.kuveytturk.com.tr/ck0d84?B83A"


def test_kuveyt_public_collector_uses_public_browser_loaded_json():
    _, testing_session = make_client()
    db = testing_session()

    # Seed USDTRY FX rate first
    fx_run = CollectorRun(
        collector_name="yahoo_usd_try",
        source="yahoo-usd-try",
        status="success",
        records_seen=1,
        records_inserted=1,
        started_at=datetime.now(UTC) - timedelta(minutes=5),
        finished_at=datetime.now(UTC) - timedelta(minutes=5),
    )
    db.add(fx_run)
    db.flush()
    db.add(
        RawFxRate(
            collector_run_id=fx_run.id,
            source="yahoo-usd-try",
            base_currency="USD",
            quote_currency="TRY",
            rate=Decimal("32.50"),
            observed_at=datetime.now(UTC) - timedelta(minutes=5),
            fetched_at=datetime.now(UTC) - timedelta(minutes=5),
            raw_payload_hash="test-fx-rate",
            parser_version="yahoo-finance-chart-v1",
        )
    )
    db.commit()

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/canli-gumus-fiyatlari-ve-gram-gumus-hesaplama"):
            return httpx.Response(200, text='<script src="/magiclick.core.min.js?v=abc"></script>')
        if request.url.path == "/magiclick.core.min.js":
            return httpx.Response(200, text='const ApiEndpoints={financePortal:"/ck0d84?financePortal"};')
        if request.url.path == "/ck0d84":
            return httpx.Response(
                200,
                json=[
                    {"Title": "USD", "CurrencyCode": "USD", "BuyRate": 44.1, "SellRate": 45.2},
                    {
                        "Title": "GMS (gr)",
                        "CurrencyCode": "GMS (gr)",
                        "CurrencyDescription": "Gümüş",
                        "BuyRate": 125.87879,
                        "SellRate": 129.63761,
                    },
                ],
            )
        return httpx.Response(404)

    client = httpx.Client(transport=httpx.MockTransport(handler))
    try:
        run, raw_inserted, snapshot = collect_kuveyt_public_silver(db, settings=Settings(), client=client)

        assert run.status == "success"
        assert raw_inserted is True
        assert snapshot is not None
        # Converted to USD/oz: try_price / USDTRY * 31.1035
        # 129.63761 / 32.50 * 31.1035 = 124.067332
        # 125.87879 / 32.50 * 31.1035 = 120.467883
        assert str(snapshot.buy_price) == "124.067182"
        assert str(snapshot.sell_price) == "120.469875"
        raw = db.query(RawBankPrice).one()
        assert raw.raw_payload_hash
        assert raw.parser_version == "kuveyt-public-finance-portal-v2"
        assert raw.payload_json["source_type"] == "official_public_browser_loaded_json"
    finally:
        client.close()
        db.close()


def test_kuveyt_anomaly_inverted_spread():
    _, testing_session = make_client()
    db = testing_session()

    # Seed USDTRY FX rate first
    fx_run = CollectorRun(
        collector_name="yahoo_usd_try",
        source="yahoo-usd-try",
        status="success",
        records_seen=1,
        records_inserted=1,
        started_at=datetime.now(UTC) - timedelta(minutes=5),
        finished_at=datetime.now(UTC) - timedelta(minutes=5),
    )
    db.add(fx_run)
    db.flush()
    db.add(
        RawFxRate(
            collector_run_id=fx_run.id,
            source="yahoo-usd-try",
            base_currency="USD",
            quote_currency="TRY",
            rate=Decimal("32.00"),
            observed_at=datetime.now(UTC) - timedelta(minutes=5),
            fetched_at=datetime.now(UTC) - timedelta(minutes=5),
            raw_payload_hash="test-fx-rate",
            parser_version="yahoo-finance-chart-v1",
        )
    )
    db.commit()

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/canli-gumus-fiyatlari-ve-gram-gumus-hesaplama"):
            return httpx.Response(200, text='<script src="/magiclick.core.min.js?v=abc"></script>')
        if request.url.path == "/magiclick.core.min.js":
            return httpx.Response(200, text='const ApiEndpoints={financePortal:"/ck0d84?financePortal"};')
        if request.url.path == "/ck0d84":
            return httpx.Response(
                200,
                json=[
                    {"Title": "USD", "CurrencyCode": "USD", "BuyRate": 44.1, "SellRate": 45.2},
                    {
                        "Title": "GMS (gr)",
                        "CurrencyCode": "GMS (gr)",
                        "CurrencyDescription": "Gümüş",
                        "BuyRate": 130.0,
                        "SellRate": 125.0,
                    },
                ],
            )
        if "SI=F" in str(request.url):
            raise httpx.ReadTimeout("timed out", request=request)
        return httpx.Response(404)

    client = httpx.Client(transport=httpx.MockTransport(handler))
    try:
        run, raw_inserted, snapshot = collect_kuveyt_public_silver(db, settings=Settings(), client=client)
        assert run.status == "failed"
        assert "inverted silver spread" in run.error_message
        assert raw_inserted is False
        assert snapshot is None
    finally:
        client.close()
        db.close()


def test_kuveyt_anomaly_spread_out_of_bounds():
    _, testing_session = make_client()
    db = testing_session()

    # Seed USDTRY FX rate first
    fx_run = CollectorRun(
        collector_name="yahoo_usd_try",
        source="yahoo-usd-try",
        status="success",
        records_seen=1,
        records_inserted=1,
        started_at=datetime.now(UTC) - timedelta(minutes=5),
        finished_at=datetime.now(UTC) - timedelta(minutes=5),
    )
    db.add(fx_run)
    db.flush()
    db.add(
        RawFxRate(
            collector_run_id=fx_run.id,
            source="yahoo-usd-try",
            base_currency="USD",
            quote_currency="TRY",
            rate=Decimal("32.00"),
            observed_at=datetime.now(UTC) - timedelta(minutes=5),
            fetched_at=datetime.now(UTC) - timedelta(minutes=5),
            raw_payload_hash="test-fx-rate",
            parser_version="yahoo-finance-chart-v1",
        )
    )
    db.commit()

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/canli-gumus-fiyatlari-ve-gram-gumus-hesaplama"):
            return httpx.Response(200, text='<script src="/magiclick.core.min.js?v=abc"></script>')
        if request.url.path == "/magiclick.core.min.js":
            return httpx.Response(200, text='const ApiEndpoints={financePortal:"/ck0d84?financePortal"};')
        if request.url.path == "/ck0d84":
            return httpx.Response(
                200,
                json=[
                    {"Title": "USD", "CurrencyCode": "USD", "BuyRate": 44.1, "SellRate": 45.2},
                    {
                        "Title": "GMS (gr)",
                        "CurrencyCode": "GMS (gr)",
                        "CurrencyDescription": "Gümüş",
                        "BuyRate": 100.0,
                        "SellRate": 130.0,
                    },
                ],
            )
        if "SI=F" in str(request.url):
            raise httpx.ReadTimeout("timed out", request=request)
        return httpx.Response(404)

    client = httpx.Client(transport=httpx.MockTransport(handler))
    try:
        run, raw_inserted, snapshot = collect_kuveyt_public_silver(db, settings=Settings(), client=client)
        assert run.status == "failed"
        assert "spread percent" in run.error_message and "outside of safe range" in run.error_message
        assert raw_inserted is False
        assert snapshot is None
    finally:
        client.close()
        db.close()


def test_kuveyt_anomaly_mid_price_deviation():
    _, testing_session = make_client()
    db = testing_session()

    # Seed USDTRY FX rate first
    fx_run = CollectorRun(
        collector_name="yahoo_usd_try",
        source="yahoo-usd-try",
        status="success",
        records_seen=1,
        records_inserted=1,
        started_at=datetime.now(UTC) - timedelta(minutes=5),
        finished_at=datetime.now(UTC) - timedelta(minutes=5),
    )
    db.add(fx_run)
    db.flush()
    db.add(
        RawFxRate(
            collector_run_id=fx_run.id,
            source="yahoo-usd-try",
            base_currency="USD",
            quote_currency="TRY",
            rate=Decimal("30.00"),
            observed_at=datetime.now(UTC) - timedelta(minutes=5),
            fetched_at=datetime.now(UTC) - timedelta(minutes=5),
            raw_payload_hash="test-fx-rate",
            parser_version="yahoo-finance-chart-v1",
        )
    )

    asset = db.execute(select(Asset).where(Asset.symbol == "XAG")).scalar_one()
    for i in range(5):
        db.add(
            PriceSnapshot(
                asset_id=asset.id,
                source="kuveyt-public-silver-page",
                buy_price=Decimal("28.5"),
                sell_price=Decimal("27.5"),
                mid_price=Decimal("28.0"),
                spread_absolute=Decimal("1.0"),
                spread_percent=Decimal("3.5"),
                currency="USD",
                observed_at=datetime.now(UTC) - timedelta(hours=i + 1),
            )
        )
    db.commit()

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/canli-gumus-fiyatlari-ve-gram-gumus-hesaplama"):
            return httpx.Response(200, text='<script src="/magiclick.core.min.js?v=abc"></script>')
        if request.url.path == "/magiclick.core.min.js":
            return httpx.Response(200, text='const ApiEndpoints={financePortal:"/ck0d84?financePortal"};')
        if request.url.path == "/ck0d84":
            return httpx.Response(
                200,
                json=[
                    {"Title": "USD", "CurrencyCode": "USD", "BuyRate": 44.1, "SellRate": 45.2},
                    {
                        "Title": "GMS (gr)",
                        "CurrencyCode": "GMS (gr)",
                        "CurrencyDescription": "Gümüş",
                        "BuyRate": 33.0,
                        "SellRate": 34.5,
                    },
                ],
            )
        if "SI=F" in str(request.url):
            raise httpx.ReadTimeout("timed out", request=request)
        return httpx.Response(404)

    client = httpx.Client(transport=httpx.MockTransport(handler))
    try:
        run, raw_inserted, snapshot = collect_kuveyt_public_silver(db, settings=Settings(), client=client)
        assert run.status == "failed"
        assert "deviates by" in run.error_message
        assert raw_inserted is False
        assert snapshot is None
    finally:
        client.close()
        db.close()


def test_kuveyt_proxy_degraded_fallback():
    _, testing_session = make_client()
    db = testing_session()

    observed_at = datetime.now(UTC) - timedelta(minutes=1)
    observed_timestamp = int(observed_at.timestamp())

    yahoo_json = {
        "chart": {
            "result": [
                {
                    "meta": {"symbol": "SI=F", "currency": "USD"},
                    "timestamp": [observed_timestamp],
                    "indicators": {
                        "quote": [
                            {"close": [28.45], "open": [28.40], "high": [28.50], "low": [28.35], "volume": [1000]}
                        ]
                    },
                }
            ],
            "error": None,
        }
    }

    def handler(request: httpx.Request) -> httpx.Response:
        if "kuveytturk.com.tr" in str(request.url):
            return httpx.Response(500, text="Internal Server Error")
        if "SI=F" in str(request.url):
            return httpx.Response(200, json=yahoo_json)
        return httpx.Response(404)

    client = httpx.Client(transport=httpx.MockTransport(handler))
    try:
        run, raw_inserted, snapshot = collect_kuveyt_public_silver(db, settings=Settings(), client=client)

        assert run.status == "success"
        assert raw_inserted is True
        assert snapshot is not None
        assert str(snapshot.buy_price) == "28.450000"
        assert str(snapshot.sell_price) == "28.450000"
        raw = db.query(RawBankPrice).one()
        assert raw.payload_json["degraded_mode"] is True
        assert raw.payload_json["proxy_source"] == "yahoo-si-f"
    finally:
        client.close()
        db.close()


def test_yahoo_usd_try_deviation_logged_when_gt_2_percent(caplog):
    import logging

    client_app, testing_session = make_client()
    now = datetime.now(UTC)

    # First ingest a TCMB rate
    db = testing_session()
    try:
        tcmb_run, _ = ingest_fx_rate(
            db,
            source="tcmb-today-xml",
            base_currency="USD",
            quote_currency="TRY",
            rate=Decimal("30.00"),
            observed_at=now - timedelta(minutes=10),
            fetched_at=now - timedelta(minutes=10),
            payload={"test": "tcmb"},
            raw_payload="test",
            parser_version="v1",
            collector_name="tcmb_usd_try",
        )
    finally:
        db.close()

    db = testing_session()
    try:
        with caplog.at_level(logging.WARNING):
            # Ingest Yahoo rate with > 2% deviation (30.00 * 1.05 = 31.50)
            run, _ = ingest_fx_rate(
                db,
                source="yahoo-usd-try",
                base_currency="USD",
                quote_currency="TRY",
                rate=Decimal("31.50"),
                observed_at=now,
                fetched_at=now,
                payload={"test": "yahoo"},
                raw_payload="test",
                parser_version="v1",
                collector_name="yahoo_usd_try",
            )

        # Check logs
        assert "USD/TRY deviation >= 2% compared to TCMB daily reference" in caplog.text

        # Check details_json
        assert "warning" in run.details_json
        assert run.details_json["deviation_pct"] == 0.05
    finally:
        db.close()


def test_yahoo_usd_try_deviation_not_logged_when_lt_2_percent(caplog):
    import logging

    client_app, testing_session = make_client()
    now = datetime.now(UTC)

    db = testing_session()
    try:
        ingest_fx_rate(
            db,
            source="tcmb-today-xml",
            base_currency="USD",
            quote_currency="TRY",
            rate=Decimal("30.00"),
            observed_at=now - timedelta(minutes=10),
            fetched_at=now - timedelta(minutes=10),
            payload={"test": "tcmb"},
            raw_payload="test",
            parser_version="v1",
            collector_name="tcmb_usd_try",
        )
    finally:
        db.close()

    db = testing_session()
    try:
        with caplog.at_level(logging.WARNING):
            # Ingest Yahoo rate with < 2% deviation (30.00 * 1.01 = 30.30)
            run, _ = ingest_fx_rate(
                db,
                source="yahoo-usd-try",
                base_currency="USD",
                quote_currency="TRY",
                rate=Decimal("30.30"),
                observed_at=now,
                fetched_at=now,
                payload={"test": "yahoo"},
                raw_payload="test",
                parser_version="v1",
                collector_name="yahoo_usd_try",
            )

        assert "USD/TRY deviation >= 2% compared to TCMB daily reference" not in caplog.text
        assert "warning" not in run.details_json
    finally:
        db.close()


def test_kuveyt_finance_portal_parser_usd_try():
    raw_payload = """
[
  {"Title":"USD","CurrencyCode":"USD","BuyRate":32.5,"SellRate":33.5},
  {"Title":"GMS (gr)","CurrencyCode":"GMS (gr)","CurrencyDescription":"Gümüş","BuyRate":125.87879,"SellRate":129.63761,"ChangeRate":3.46,"ChangeRateNegative":false}
]
"""
    parsed = parse_kuveyt_finance_portal_json_usd_try(
        raw_payload, fetched_at=datetime(2026, 5, 13, 12, 0, tzinfo=UTC), finance_portal_url="https://test"
    )
    assert parsed.base_currency == "USD"
    assert parsed.quote_currency == "TRY"
    assert parsed.rate == Decimal("33.00")
    assert parsed.payload["source_type"] == "official_public_browser_loaded_json"


def test_kuveyt_usd_try_collector_writes_fx_rate():
    _, testing_session = make_client()
    db = testing_session()

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/canli-gumus-fiyatlari-ve-gram-gumus-hesaplama"):
            return httpx.Response(200, text='<script src="/magiclick.core.min.js?v=abc"></script>')
        if request.url.path == "/magiclick.core.min.js":
            return httpx.Response(200, text='const ApiEndpoints={financePortal:"/ck0d84?financePortal"};')
        if request.url.path == "/ck0d84":
            return httpx.Response(
                200,
                json=[
                    {"Title": "USD", "CurrencyCode": "USD", "BuyRate": 32.5, "SellRate": 33.5},
                ],
            )
        return httpx.Response(404)

    client = httpx.Client(transport=httpx.MockTransport(handler))
    try:
        run, raw_inserted = collect_kuveyt_usd_try(db, settings=Settings(), client=client)

        assert run.status == "success"
        assert raw_inserted is True
        raw = db.query(RawFxRate).where(RawFxRate.source == "kuveyt-public-silver-page").one()
        assert raw.base_currency == "USD"
        assert raw.quote_currency == "TRY"
        assert str(raw.rate) == "33.000000"
    finally:
        client.close()
        db.close()


def test_collector_health_reports_fresh_with_kuveyt_usd_try_fallback():
    client, testing_session = make_client()
    now = datetime.now(UTC)
    db = testing_session()
    try:
        # Seed fresh global XAG
        asset = db.execute(select(Asset).where(Asset.symbol == "XAG")).scalar_one()
        global_run = CollectorRun(
            collector_name="global_xag_usd",
            source="yahoo-si-f",
            status="success",
            records_seen=1,
            records_inserted=1,
            started_at=now - timedelta(minutes=10),
            finished_at=now - timedelta(minutes=10),
            details_json={},
        )
        # Seed fresh Kuveyt USD TRY (this acts as fallback for usd_try)
        fx_run = CollectorRun(
            collector_name="kuveyt_usd_try",
            source="kuveyt-public-silver-page",
            status="success",
            records_seen=1,
            records_inserted=1,
            started_at=now - timedelta(minutes=10),
            finished_at=now - timedelta(minutes=10),
            details_json={},
        )
        # Seed fresh Kuveyt bank price
        bank_run = CollectorRun(
            collector_name="kuveyt_public_silver",
            source="kuveyt-public-silver-page",
            status="success",
            records_seen=1,
            records_inserted=1,
            started_at=now - timedelta(minutes=10),
            finished_at=now - timedelta(minutes=10),
            details_json={},
        )
        db.add_all([global_run, fx_run, bank_run])
        db.flush()
        db.add(
            RawGlobalPrice(
                collector_run_id=global_run.id,
                asset_id=asset.id,
                source="yahoo-si-f",
                buy_price=Decimal("28.00"),
                sell_price=Decimal("28.00"),
                currency="USD",
                observed_at=now - timedelta(minutes=10),
                fetched_at=now - timedelta(minutes=10),
                raw_payload_hash="test",
                parser_version="v1",
                payload_json={},
            )
        )
        db.add(
            RawFxRate(
                collector_run_id=fx_run.id,
                source="kuveyt-public-silver-page",
                base_currency="USD",
                quote_currency="TRY",
                rate=Decimal("33.00"),
                observed_at=now - timedelta(minutes=10),
                fetched_at=now - timedelta(minutes=10),
                raw_payload_hash="test",
                parser_version="v1",
                payload_json={},
            )
        )
        db.add(
            RawBankPrice(
                collector_run_id=bank_run.id,
                asset_id=asset.id,
                source="kuveyt-public-silver-page",
                buy_price=Decimal("130.00"),
                sell_price=Decimal("126.00"),
                currency="TRY",
                observed_at=now - timedelta(minutes=10),
                fetched_at=now - timedelta(minutes=10),
                raw_payload_hash="test",
                parser_version="v1",
                payload_json={},
            )
        )
        db.commit()
    finally:
        db.close()

    response = client.get("/collectors/health?stale_after_minutes=60")

    assert response.status_code == 200
    body = response.json()
    assert body["execution_critical"]["usd_try"] == "fresh"
    assert body["execution_critical"]["usd_try_source"] == "kuveyt-public-silver-page"


def test_kuveyt_hardening_successful_run():
    _, testing_session = make_client()
    db = testing_session()

    # Seed USDTRY FX rate
    fx_run = CollectorRun(
        collector_name="yahoo_usd_try",
        source="yahoo-usd-try",
        status="success",
        records_seen=1,
        records_inserted=1,
        started_at=datetime.now(UTC) - timedelta(minutes=5),
        finished_at=datetime.now(UTC) - timedelta(minutes=5),
    )
    db.add(fx_run)
    db.flush()
    db.add(
        RawFxRate(
            collector_run_id=fx_run.id,
            source="yahoo-usd-try",
            base_currency="USD",
            quote_currency="TRY",
            rate=Decimal("32.50"),
            observed_at=datetime.now(UTC) - timedelta(minutes=5),
            fetched_at=datetime.now(UTC) - timedelta(minutes=5),
            raw_payload_hash="test-fx-rate",
            parser_version="yahoo-finance-chart-v1",
        )
    )
    db.commit()

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/canli-gumus-fiyatlari-ve-gram-gumus-hesaplama"):
            return httpx.Response(200, text='<script src="/magiclick.core.min.js?v=abc"></script>')
        if request.url.path == "/magiclick.core.min.js":
            return httpx.Response(200, text='const ApiEndpoints={financePortal:"/ck0d84?financePortal"};')
        if request.url.path == "/ck0d84":
            return httpx.Response(
                200,
                json=[
                    {"Title": "USD", "CurrencyCode": "USD", "BuyRate": 44.1, "SellRate": 45.2},
                    {
                        "Title": "GMS (gr)",
                        "CurrencyCode": "GMS (gr)",
                        "CurrencyDescription": "Gümüş",
                        "BuyRate": 125.87879,
                        "SellRate": 129.63761,
                    },
                ],
            )
        if "SI=F" in str(request.url):
            return httpx.Response(
                200,
                json={
                    "chart": {
                        "result": [
                            {
                                "meta": {"symbol": "SI=F", "currency": "USD"},
                                "timestamp": [int(time.time())],
                                "indicators": {
                                    "quote": [
                                        {
                                            "close": [124.0],
                                            "open": [124.0],
                                            "high": [124.0],
                                            "low": [124.0],
                                            "volume": [0],
                                        }
                                    ]
                                },
                            }
                        ]
                    }
                },
            )
        return httpx.Response(404)

    client = httpx.Client(transport=httpx.MockTransport(handler))
    try:
        run, raw_inserted, snapshot = collect_kuveyt_public_silver(db, settings=Settings(), client=client)

        assert run.status == "success"
        assert raw_inserted is True
        assert snapshot is not None
        assert snapshot.resolved_source == "kuveyt_public_portal"
        assert snapshot.is_degraded is False

        raw = db.query(RawBankPrice).one()
        assert raw.resolved_source == "kuveyt_public_portal"
        assert raw.is_degraded is False
    finally:
        client.close()
        db.close()


def test_kuveyt_hardening_degraded_fallback():
    _, testing_session = make_client()
    db = testing_session()

    # Seed USDTRY FX rate
    fx_run = CollectorRun(
        collector_name="yahoo_usd_try",
        source="yahoo-usd-try",
        status="success",
        records_seen=1,
        records_inserted=1,
        started_at=datetime.now(UTC) - timedelta(minutes=5),
        finished_at=datetime.now(UTC) - timedelta(minutes=5),
    )
    db.add(fx_run)
    db.flush()
    db.add(
        RawFxRate(
            collector_run_id=fx_run.id,
            source="yahoo-usd-try",
            base_currency="USD",
            quote_currency="TRY",
            rate=Decimal("32.50"),
            observed_at=datetime.now(UTC) - timedelta(minutes=5),
            fetched_at=datetime.now(UTC) - timedelta(minutes=5),
            raw_payload_hash="test-fx-rate",
            parser_version="yahoo-finance-chart-v1",
        )
    )
    db.commit()

    def handler(request: httpx.Request) -> httpx.Response:
        if "/canli-gumus-fiyatlari-ve-gram-gumus-hesaplama" in str(request.url):
            raise httpx.ConnectTimeout("connection timed out", request=request)
        if "SI=F" in str(request.url):
            return httpx.Response(
                200,
                json={
                    "chart": {
                        "result": [
                            {
                                "meta": {"symbol": "SI=F", "currency": "USD"},
                                "timestamp": [int(time.time())],
                                "indicators": {
                                    "quote": [
                                        {
                                            "close": [28.45],
                                            "open": [28.45],
                                            "high": [28.45],
                                            "low": [28.45],
                                            "volume": [0],
                                        }
                                    ]
                                },
                            }
                        ]
                    }
                },
            )
        return httpx.Response(404)

    client = httpx.Client(transport=httpx.MockTransport(handler))
    try:
        run, raw_inserted, snapshot = collect_kuveyt_public_silver(db, settings=Settings(), client=client)

        assert run.status == "success"
        assert raw_inserted is True
        assert snapshot is not None
        assert snapshot.resolved_source == "yahoo_si_f"
        assert snapshot.is_degraded is True

        raw = db.query(RawBankPrice).one()
        assert raw.resolved_source == "yahoo_si_f"
        assert raw.is_degraded is True
    finally:
        client.close()
        db.close()


def test_kuveyt_retry_mechanism():
    _, testing_session = make_client()
    db = testing_session()

    # Seed USDTRY FX rate
    fx_run = CollectorRun(
        collector_name="yahoo_usd_try",
        source="yahoo-usd-try",
        status="success",
        records_seen=1,
        records_inserted=1,
        started_at=datetime.now(UTC) - timedelta(minutes=5),
        finished_at=datetime.now(UTC) - timedelta(minutes=5),
    )
    db.add(fx_run)
    db.flush()
    db.add(
        RawFxRate(
            collector_run_id=fx_run.id,
            source="yahoo-usd-try",
            base_currency="USD",
            quote_currency="TRY",
            rate=Decimal("32.50"),
            observed_at=datetime.now(UTC) - timedelta(minutes=5),
            fetched_at=datetime.now(UTC) - timedelta(minutes=5),
            raw_payload_hash="test-fx-rate",
            parser_version="yahoo-finance-chart-v1",
        )
    )
    db.commit()

    kuveyt_page_calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal kuveyt_page_calls
        if request.url.path.endswith("/canli-gumus-fiyatlari-ve-gram-gumus-hesaplama"):
            kuveyt_page_calls += 1
            if kuveyt_page_calls < 3:
                raise httpx.ConnectTimeout("connection timed out", request=request)
            return httpx.Response(200, text='<script src="/magiclick.core.min.js?v=abc"></script>')
        if request.url.path == "/magiclick.core.min.js":
            return httpx.Response(200, text='const ApiEndpoints={financePortal:"/ck0d84?financePortal"};')
        if request.url.path == "/ck0d84":
            return httpx.Response(
                200,
                json=[
                    {"Title": "USD", "CurrencyCode": "USD", "BuyRate": 44.1, "SellRate": 45.2},
                    {
                        "Title": "GMS (gr)",
                        "CurrencyCode": "GMS (gr)",
                        "CurrencyDescription": "Gümüş",
                        "BuyRate": 125.87879,
                        "SellRate": 129.63761,
                    },
                ],
            )
        return httpx.Response(404)

    client = httpx.Client(transport=httpx.MockTransport(handler))
    try:
        from unittest.mock import patch

        with patch("time.sleep", return_value=None) as mock_sleep:
            run, raw_inserted, snapshot = collect_kuveyt_public_silver(db, settings=Settings(), client=client)

            assert run.status == "success"
            assert raw_inserted is True
            assert snapshot is not None
            assert snapshot.resolved_source == "kuveyt_public_portal"
            assert snapshot.is_degraded is False
            assert kuveyt_page_calls == 3
            assert mock_sleep.call_count == 2
    finally:
        client.close()
        db.close()


def test_kuveyt_hardening_structural_error():
    _, testing_session = make_client()
    db = testing_session()

    # Seed USDTRY FX rate
    fx_run = CollectorRun(
        collector_name="yahoo_usd_try",
        source="yahoo-usd-try",
        status="success",
        records_seen=1,
        records_inserted=1,
        started_at=datetime.now(UTC) - timedelta(minutes=5),
        finished_at=datetime.now(UTC) - timedelta(minutes=5),
    )
    db.add(fx_run)
    db.flush()
    db.add(
        RawFxRate(
            collector_run_id=fx_run.id,
            source="yahoo-usd-try",
            base_currency="USD",
            quote_currency="TRY",
            rate=Decimal("32.50"),
            observed_at=datetime.now(UTC) - timedelta(minutes=5),
            fetched_at=datetime.now(UTC) - timedelta(minutes=5),
            raw_payload_hash="test-fx-rate",
            parser_version="yahoo-finance-chart-v1",
        )
    )
    db.commit()

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/canli-gumus-fiyatlari-ve-gram-gumus-hesaplama"):
            return httpx.Response(200, text="<html><body>No script here</body></html>")
        if "SI=F" in str(request.url):
            return httpx.Response(
                200,
                json={
                    "chart": {
                        "result": [
                            {
                                "meta": {"symbol": "SI=F", "currency": "USD"},
                                "timestamp": [int(time.time())],
                                "indicators": {
                                    "quote": [
                                        {
                                            "close": [28.45],
                                            "open": [28.45],
                                            "high": [28.45],
                                            "low": [28.45],
                                            "volume": [0],
                                        }
                                    ]
                                },
                            }
                        ]
                    }
                },
            )
        return httpx.Response(404)

    client = httpx.Client(transport=httpx.MockTransport(handler))
    try:
        run, raw_inserted, snapshot = collect_kuveyt_public_silver(db, settings=Settings(), client=client)

        assert run.status == "failed"
        assert raw_inserted is False
        assert snapshot is None
        assert "Kuveyt public page parser could not find public core script" in run.error_message
    finally:
        client.close()
        db.close()


def test_kuveyt_hardening_inverted_spread_hard_block():
    _, testing_session = make_client()
    db = testing_session()

    # Seed USDTRY FX rate
    fx_run = CollectorRun(
        collector_name="yahoo_usd_try",
        source="yahoo-usd-try",
        status="success",
        records_seen=1,
        records_inserted=1,
        started_at=datetime.now(UTC) - timedelta(minutes=5),
        finished_at=datetime.now(UTC) - timedelta(minutes=5),
    )
    db.add(fx_run)
    db.flush()
    db.add(
        RawFxRate(
            collector_run_id=fx_run.id,
            source="yahoo-usd-try",
            base_currency="USD",
            quote_currency="TRY",
            rate=Decimal("32.50"),
            observed_at=datetime.now(UTC) - timedelta(minutes=5),
            fetched_at=datetime.now(UTC) - timedelta(minutes=5),
            raw_payload_hash="test-fx-rate",
            parser_version="yahoo-finance-chart-v1",
        )
    )
    db.commit()

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/canli-gumus-fiyatlari-ve-gram-gumus-hesaplama"):
            return httpx.Response(200, text='<script src="/magiclick.core.min.js?v=abc"></script>')
        if request.url.path == "/magiclick.core.min.js":
            return httpx.Response(200, text='const ApiEndpoints={financePortal:"/ck0d84?financePortal"};')
        if request.url.path == "/ck0d84":
            return httpx.Response(
                200,
                json=[
                    {"Title": "USD", "CurrencyCode": "USD", "BuyRate": 44.1, "SellRate": 45.2},
                    {
                        "Title": "GMS (gr)",
                        "CurrencyCode": "GMS (gr)",
                        "CurrencyDescription": "Gümüş",
                        "BuyRate": 130.0,
                        "SellRate": 125.0,
                    },
                ],
            )
        if "SI=F" in str(request.url):
            return httpx.Response(
                200,
                json={
                    "chart": {
                        "result": [
                            {
                                "meta": {"symbol": "SI=F", "currency": "USD"},
                                "timestamp": [int(time.time())],
                                "indicators": {
                                    "quote": [
                                        {
                                            "close": [28.45],
                                            "open": [28.45],
                                            "high": [28.45],
                                            "low": [28.45],
                                            "volume": [0],
                                        }
                                    ]
                                },
                            }
                        ]
                    }
                },
            )
        return httpx.Response(404)

    client = httpx.Client(transport=httpx.MockTransport(handler))
    try:
        run, raw_inserted, snapshot = collect_kuveyt_public_silver(db, settings=Settings(), client=client)

        assert run.status == "failed"
        assert raw_inserted is False
        assert snapshot is None
        assert "inverted" in run.error_message.lower()
    finally:
        client.close()
        db.close()


def test_kuveyt_hardening_out_of_bounds_spread_hard_block():
    _, testing_session = make_client()
    db = testing_session()

    # Seed USDTRY FX rate
    fx_run = CollectorRun(
        collector_name="yahoo_usd_try",
        source="yahoo-usd-try",
        status="success",
        records_seen=1,
        records_inserted=1,
        started_at=datetime.now(UTC) - timedelta(minutes=5),
        finished_at=datetime.now(UTC) - timedelta(minutes=5),
    )
    db.add(fx_run)
    db.flush()
    db.add(
        RawFxRate(
            collector_run_id=fx_run.id,
            source="yahoo-usd-try",
            base_currency="USD",
            quote_currency="TRY",
            rate=Decimal("32.50"),
            observed_at=datetime.now(UTC) - timedelta(minutes=5),
            fetched_at=datetime.now(UTC) - timedelta(minutes=5),
            raw_payload_hash="test-fx-rate",
            parser_version="yahoo-finance-chart-v1",
        )
    )
    db.commit()

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/canli-gumus-fiyatlari-ve-gram-gumus-hesaplama"):
            return httpx.Response(200, text='<script src="/magiclick.core.min.js?v=abc"></script>')
        if request.url.path == "/magiclick.core.min.js":
            return httpx.Response(200, text='const ApiEndpoints={financePortal:"/ck0d84?financePortal"};')
        if request.url.path == "/ck0d84":
            return httpx.Response(
                200,
                json=[
                    {"Title": "USD", "CurrencyCode": "USD", "BuyRate": 44.1, "SellRate": 45.2},
                    {
                        "Title": "GMS (gr)",
                        "CurrencyCode": "GMS (gr)",
                        "CurrencyDescription": "Gümüş",
                        "BuyRate": 100.0,
                        "SellRate": 101.0,
                    },
                ],
            )
        if "SI=F" in str(request.url):
            return httpx.Response(
                200,
                json={
                    "chart": {
                        "result": [
                            {
                                "meta": {"symbol": "SI=F", "currency": "USD"},
                                "timestamp": [int(time.time())],
                                "indicators": {
                                    "quote": [
                                        {
                                            "close": [28.45],
                                            "open": [28.45],
                                            "high": [28.45],
                                            "low": [28.45],
                                            "volume": [0],
                                        }
                                    ]
                                },
                            }
                        ]
                    }
                },
            )
        return httpx.Response(404)

    client = httpx.Client(transport=httpx.MockTransport(handler))
    try:
        run, raw_inserted, snapshot = collect_kuveyt_public_silver(db, settings=Settings(), client=client)

        assert run.status == "failed"
        assert raw_inserted is False
        assert snapshot is None
        assert "spread percent" in run.error_message and "outside of safe range" in run.error_message
    finally:
        client.close()
        db.close()


def test_kuveyt_hardening_cross_control_warning():
    _, testing_session = make_client()
    db = testing_session()

    # Seed USDTRY FX rate
    fx_run = CollectorRun(
        collector_name="yahoo_usd_try",
        source="yahoo-usd-try",
        status="success",
        records_seen=1,
        records_inserted=1,
        started_at=datetime.now(UTC) - timedelta(minutes=5),
        finished_at=datetime.now(UTC) - timedelta(minutes=5),
    )
    db.add(fx_run)
    db.flush()
    db.add(
        RawFxRate(
            collector_run_id=fx_run.id,
            source="yahoo-usd-try",
            base_currency="USD",
            quote_currency="TRY",
            rate=Decimal("32.50"),
            observed_at=datetime.now(UTC) - timedelta(minutes=5),
            fetched_at=datetime.now(UTC) - timedelta(minutes=5),
            raw_payload_hash="test-fx-rate",
            parser_version="yahoo-finance-chart-v1",
        )
    )
    db.commit()

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/canli-gumus-fiyatlari-ve-gram-gumus-hesaplama"):
            return httpx.Response(200, text='<script src="/magiclick.core.min.js?v=abc"></script>')
        if request.url.path == "/magiclick.core.min.js":
            return httpx.Response(200, text='const ApiEndpoints={financePortal:"/ck0d84?financePortal"};')
        if request.url.path == "/ck0d84":
            return httpx.Response(
                200,
                json=[
                    {"Title": "USD", "CurrencyCode": "USD", "BuyRate": 44.1, "SellRate": 45.2},
                    {
                        "Title": "GMS (gr)",
                        "CurrencyCode": "GMS (gr)",
                        "CurrencyDescription": "Gümüş",
                        "BuyRate": 125.87879,
                        "SellRate": 129.63761,
                    },
                ],
            )
        if "SI=F" in str(request.url):
            return httpx.Response(
                200,
                json={
                    "chart": {
                        "result": [
                            {
                                "meta": {"symbol": "SI=F", "currency": "USD"},
                                "timestamp": [int(time.time())],
                                "indicators": {
                                    "quote": [
                                        {
                                            "close": [100.00],
                                            "open": [100.00],
                                            "high": [100.00],
                                            "low": [100.00],
                                            "volume": [0],
                                        }
                                    ]
                                },
                            }
                        ]
                    }
                },
            )
        return httpx.Response(404)

    client = httpx.Client(transport=httpx.MockTransport(handler))
    try:
        run, raw_inserted, snapshot = collect_kuveyt_public_silver(db, settings=Settings(), client=client)

        assert run.status == "success"
        assert raw_inserted is True
        assert snapshot is not None
        assert "warning" in run.details_json
        assert "Kuveyt USD mid price deviates by" in run.details_json["warning"]
        assert run.details_json["kuveyt_usd_mid"]
        assert run.details_json["yahoo_usd_mid"] == "100.0"
        assert run.details_json["deviation_pct"] > 0.05
    finally:
        client.close()
        db.close()


def test_runner_comex_sleep_mode_job_filtering_independent_override():
    from app.collectors.runner import parse_collector_jobs

    jobs = parse_collector_jobs("fed-rss,news-agent,hermes-agent", fallback_job="manual")
    assert len(jobs) == 3
    assert jobs == ["fed-rss", "news-agent", "hermes-agent"]
