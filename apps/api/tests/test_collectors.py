from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.db import Base, get_db
from app.main import create_app
from app.models import Asset, CollectorRun, PriceSnapshot, RawBankPrice


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
        assert db.query(RawBankPrice).count() == 1
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
    assert response.json() == {
        "status": "empty",
        "stale_after_minutes": 60,
        "collectors": [],
    }


def test_collector_health_reports_latest_run_status():
    client, _ = make_client()
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
    assert body["status"] == "ok"
    assert body["collectors"][0]["collector_name"] == "manual_bank_price"
    assert body["collectors"][0]["source"] == "manual-test-bank"
    assert body["collectors"][0]["stale"] is False


def test_collector_health_rejects_invalid_stale_threshold():
    client, _ = make_client()

    response = client.get("/collectors/health?stale_after_minutes=0")

    assert response.status_code == 400
