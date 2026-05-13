from datetime import UTC, datetime
from decimal import Decimal

from fastapi.testclient import TestClient
import httpx
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.collectors.public_sources import (
    collect_stooq_xag_usd,
    collect_tcmb_usd_try,
    parse_kuveyt_public_silver_html,
)
from app.core.config import Settings
from app.core.db import Base, get_db
from app.main import create_app
from app.models import Asset, CollectorRun, PriceSnapshot, RawBankPrice, RawFxRate, RawGlobalPrice


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


def test_stooq_xag_usd_collector_writes_global_price_and_snapshot():
    _, testing_session = make_client()

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.headers["user-agent"].startswith("SilverPilot/")
        return httpx.Response(
            200,
            text=(
                "Symbol,Date,Time,Open,High,Low,Close,Volume\n"
                "XAGUSD,2026-05-13,11:47:16,86.619,87.799,85.697,86.595,\n"
            ),
        )

    client = httpx.Client(transport=httpx.MockTransport(handler))
    db = testing_session()
    try:
        run, raw_inserted, snapshot = collect_stooq_xag_usd(db, settings=Settings(), client=client)

        assert run.status == "success"
        assert raw_inserted is True
        assert snapshot is not None
        assert str(snapshot.mid_price) == "86.595000"
        raw = db.query(RawGlobalPrice).one()
        assert raw.source == "stooq-xagusd-csv"
        assert raw.raw_payload_hash
        assert raw.parser_version == "stooq-xagusd-csv-v1"
    finally:
        client.close()
        db.close()


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
