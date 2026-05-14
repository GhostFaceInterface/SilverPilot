from datetime import UTC, datetime
from decimal import Decimal

from fastapi.testclient import TestClient
import httpx
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.collectors.public_sources import (
    collect_fed_rss,
    collect_fred_macro,
    collect_kuveyt_public_silver,
    collect_stooq_xag_usd,
    collect_tcmb_usd_try,
    discover_kuveyt_core_script_url,
    parse_fed_rss,
    parse_fred_observations,
    parse_kuveyt_finance_portal_endpoint,
    parse_kuveyt_finance_portal_json,
    parse_kuveyt_public_silver_html,
)
from app.collectors.runner import parse_collector_jobs
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
        "execution_critical": {
            "bank_price": "missing",
            "source": None,
            "age_seconds": None,
            "stale": True,
            "manual_fallback": False,
        },
        "stale_after_minutes": 60,
        "collectors": [],
    }


def test_collector_health_reports_manual_bank_price_as_degraded_fallback():
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
    assert body["status"] == "degraded"
    assert body["execution_critical"]["bank_price"] == "manual_fallback"
    assert body["execution_critical"]["manual_fallback"] is True
    assert body["collectors"][0]["collector_name"] == "manual_bank_price"
    assert body["collectors"][0]["source"] == "manual-test-bank"
    assert body["collectors"][0]["stale"] is False


def test_collector_health_ignores_stale_manual_when_official_bank_price_is_fresh():
    client, testing_session = make_client()
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


def test_runner_parse_collector_jobs_uses_comma_list_or_fallback():
    assert parse_collector_jobs("", fallback_job="manual") == ["manual"]
    assert parse_collector_jobs("kuveyt-silver, stooq-xag-usd", fallback_job="manual") == [
        "kuveyt-silver",
        "stooq-xag-usd",
    ]


def test_runner_parse_collector_jobs_rejects_unknown_job():
    try:
        parse_collector_jobs("kuveyt-silver,unknown", fallback_job="manual")
    except ValueError as exc:
        assert "unknown" in str(exc)
    else:
        raise AssertionError("unknown collector job should be rejected")


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
    db = testing_session()
    try:
        run, raw_inserted, snapshot = collect_kuveyt_public_silver(db, settings=Settings(), client=client)

        assert run.status == "success"
        assert raw_inserted is True
        assert snapshot is not None
        assert str(snapshot.buy_price) == "129.637610"
        assert str(snapshot.sell_price) == "125.878790"
        raw = db.query(RawBankPrice).one()
        assert raw.raw_payload_hash
        assert raw.parser_version == "kuveyt-public-finance-portal-v2"
        assert raw.payload_json["source_type"] == "official_public_browser_loaded_json"
    finally:
        client.close()
        db.close()
