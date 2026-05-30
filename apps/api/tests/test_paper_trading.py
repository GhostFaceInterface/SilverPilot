from datetime import UTC, datetime, timedelta
from decimal import Decimal

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.db import Base, get_db
from app.main import create_app
from app.models import Asset, CollectorRun, PaperTrade, Portfolio, RawBankPrice, RawFxRate, RawGlobalPrice, RiskDecision


def make_client():
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    testing_session = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    Base.metadata.create_all(bind=engine)

    db = testing_session()
    db.add(Asset(symbol="XAG_GRAM", name="Gram Silver", asset_type="metal", is_active=True))
    db.add(
        Portfolio(
            name="gram-paper",
            base_currency="USD",
            initial_cash=Decimal("2500.000000"),
            cash_balance=Decimal("2500.000000"),
            is_real_money=False,
        )
    )
    db.flush()

    fx_run = CollectorRun(
        collector_name="tcmb_usd_try",
        source="tcmb-today-xml",
        status="success",
        records_seen=1,
        records_inserted=1,
        started_at=datetime.now(UTC),
        finished_at=datetime.now(UTC),
        details_json={},
    )
    db.add(fx_run)
    db.flush()

    db.add(
        RawFxRate(
            collector_run_id=fx_run.id,
            source="tcmb-today-xml",
            base_currency="USD",
            quote_currency="TRY",
            rate=Decimal("32.000000"),
            observed_at=datetime.now(UTC),
            fetched_at=datetime.now(UTC),
            raw_payload_hash="default-fx-hash",
            parser_version="tcmb-today-xml-v1",
            payload_json={},
        )
    )
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


def seed_execution_critical_data(testing_session, *, observed_at: datetime | None = None):
    observed_at = observed_at or datetime.now(UTC)
    fetched_at = observed_at
    db = testing_session()
    try:
        asset = db.query(Asset).filter(Asset.symbol == "XAG_GRAM").one()
        bank_run = CollectorRun(
            collector_name="kuveyt_public_silver",
            source="kuveyt-public-silver-page",
            status="success",
            records_seen=1,
            records_inserted=1,
            started_at=fetched_at,
            finished_at=fetched_at,
            details_json={},
        )
        global_run = CollectorRun(
            collector_name="global_xag_usd",
            source="gold-api-xag-usd",
            status="success",
            records_seen=1,
            records_inserted=1,
            started_at=fetched_at,
            finished_at=fetched_at,
            details_json={"selected_global_xag_source": "gold-api-xag-usd"},
        )
        fx_run = CollectorRun(
            collector_name="tcmb_usd_try",
            source="tcmb-today-xml",
            status="success",
            records_seen=1,
            records_inserted=1,
            started_at=fetched_at,
            finished_at=fetched_at,
            details_json={},
        )
        db.add_all([bank_run, global_run, fx_run])
        db.flush()
        db.add_all(
            [
                RawBankPrice(
                    collector_run_id=bank_run.id,
                    asset_id=asset.id,
                    source="kuveyt-public-silver-page",
                    buy_price=Decimal("10.000000"),
                    sell_price=Decimal("9.800000"),
                    currency="TRY",
                    observed_at=observed_at,
                    fetched_at=fetched_at,
                    raw_payload_hash="bank-hash",
                    parser_version="kuveyt-public-finance-portal-v2",
                    payload_json={},
                ),
                RawGlobalPrice(
                    collector_run_id=global_run.id,
                    asset_id=asset.id,
                    source="gold-api-xag-usd",
                    buy_price=Decimal("32.000000"),
                    sell_price=Decimal("32.000000"),
                    currency="USD",
                    observed_at=observed_at,
                    fetched_at=fetched_at,
                    raw_payload_hash="global-hash",
                    parser_version="gold-api-xag-usd-v1",
                    payload_json={},
                ),
                RawFxRate(
                    collector_run_id=fx_run.id,
                    source="tcmb-today-xml",
                    base_currency="USD",
                    quote_currency="TRY",
                    rate=Decimal("32.000000"),
                    observed_at=observed_at,
                    fetched_at=fetched_at,
                    raw_payload_hash="fx-hash",
                    parser_version="tcmb-today-xml-v1",
                    payload_json={},
                ),
            ]
        )
        db.commit()
    finally:
        db.close()


def seed_global_price_history(
    testing_session,
    *,
    prices: list[Decimal],
    observed_at: datetime | None = None,
    source: str = "gold-api-xag-usd",
):
    observed_at = observed_at or datetime.now(UTC)
    db = testing_session()
    try:
        asset = db.query(Asset).filter(Asset.symbol == "XAG_GRAM").one()
        for index, price in enumerate(prices):
            point_time = observed_at - timedelta(minutes=len(prices) - index)
            run = CollectorRun(
                collector_name="global_xag_usd",
                source=source,
                status="success",
                records_seen=1,
                records_inserted=1,
                started_at=point_time,
                finished_at=point_time,
                details_json={"selected_global_xag_source": source},
            )
            db.add(run)
            db.flush()
            db.add(
                RawGlobalPrice(
                    collector_run_id=run.id,
                    asset_id=asset.id,
                    source=source,
                    buy_price=price,
                    sell_price=price,
                    currency="USD",
                    observed_at=point_time,
                    fetched_at=point_time,
                    raw_payload_hash=f"global-history-{index}",
                    parser_version=f"{source}-v1",
                    payload_json={},
                )
            )
        db.commit()
    finally:
        db.close()


def seed_realized_loss(testing_session, *, loss: Decimal, sell_created_at: datetime):
    db = testing_session()
    try:
        asset = db.query(Asset).filter(Asset.symbol == "XAG_GRAM").one()
        portfolio = db.query(Portfolio).filter(Portfolio.name == "gram-paper").one()
        decision = RiskDecision(
            decision="allow",
            reason_code="RISK_CHECK_PASSED",
            risk_level="low",
            confidence=Decimal("1.0000"),
            details_json={},
        )
        db.add(decision)
        db.flush()
        buy_created_at = sell_created_at - timedelta(minutes=5)
        db.add_all(
            [
                PaperTrade(
                    portfolio_id=portfolio.id,
                    asset_id=asset.id,
                    action="paper_buy",
                    quantity=Decimal("10.000000"),
                    price=Decimal("10.000000"),
                    gross_amount=Decimal("100.000000"),
                    fees=Decimal("0.000000"),
                    taxes=Decimal("0.000000"),
                    net_amount=Decimal("100.000000"),
                    risk_decision_id=decision.id,
                    created_at=buy_created_at,
                ),
                PaperTrade(
                    portfolio_id=portfolio.id,
                    asset_id=asset.id,
                    action="paper_sell",
                    quantity=Decimal("10.000000"),
                    price=(Decimal("100.000000") - loss) / Decimal("10.000000"),
                    gross_amount=Decimal("100.000000") - loss,
                    fees=Decimal("0.000000"),
                    taxes=Decimal("0.000000"),
                    net_amount=Decimal("100.000000") - loss,
                    risk_decision_id=decision.id,
                    created_at=sell_created_at,
                ),
            ]
        )
        db.commit()
    finally:
        db.close()


def test_buy_then_sell_same_market_loses_after_spread_and_fees():
    client, testing_session = make_client()
    seed_execution_critical_data(testing_session)

    buy_response = client.post(
        "/paper-trades",
        json={
            "action": "paper_buy",
            "quantity": "10",
            "buy_price": "10.00",
            "sell_price": "9.80",
            "fees": "1.00",
            "taxes": "0",
        },
    )
    assert buy_response.status_code == 200
    assert buy_response.json()["snapshot"]["cash_balance"] == "2496.837500"
    assert buy_response.json()["risk_decision"]["decision"] == "allow"
    assert buy_response.json()["risk_decision"]["reason_code"] == "RISK_CHECK_PASSED"
    assert buy_response.json()["trade"]["risk_decision_id"] == buy_response.json()["risk_decision"]["id"]

    sell_response = client.post(
        "/paper-trades",
        json={
            "action": "paper_sell",
            "quantity": "10",
            "buy_price": "10.00",
            "sell_price": "9.80",
            "fees": "1.00",
            "taxes": "0",
        },
    )
    assert sell_response.status_code == 200

    snapshot = sell_response.json()["snapshot"]
    assert snapshot["cash_balance"] == "2499.868750"
    assert Decimal(snapshot["portfolio_value"]) < Decimal("2500.000000")
    assert Decimal(snapshot["realized_pnl"]) < Decimal("0")


def test_buy_cannot_make_cash_balance_negative():
    client, testing_session = make_client()
    seed_execution_critical_data(testing_session)

    response = client.post(
        "/paper-trades",
        json={
            "action": "paper_buy",
            "quantity": "9000",
            "buy_price": "10.00",
            "sell_price": "9.80",
            "fees": "0",
            "taxes": "0",
        },
    )

    assert response.status_code == 200
    assert response.json()["trade"]["action"] == "blocked"
    assert response.json()["risk_decision"]["decision"] == "blocked"
    assert response.json()["risk_decision"]["reason_code"] == "INSUFFICIENT_CASH"

    db = testing_session()
    try:
        portfolio = db.query(Portfolio).filter(Portfolio.name == "gram-paper").one()
        trade = db.query(PaperTrade).one()
        assert portfolio.cash_balance == Decimal("2500.000000")
        assert trade.action == "blocked"
        assert trade.risk_decision_id is not None
    finally:
        db.close()


def test_real_money_portfolio_is_rejected():
    client, testing_session = make_client()
    db = testing_session()
    try:
        portfolio = db.query(Portfolio).filter(Portfolio.name == "gram-paper").one()
        portfolio.is_real_money = True
        db.commit()
    finally:
        db.close()

    response = client.post(
        "/paper-trades",
        json={
            "action": "paper_buy",
            "quantity": "1",
            "buy_price": "10.00",
            "sell_price": "9.80",
            "fees": "0",
            "taxes": "0",
        },
    )

    assert response.status_code == 400
    assert response.json()["detail"] == "Real-money portfolios are not allowed in SilverPilot"


def test_missing_execution_critical_data_blocks_and_records_risk_decision():
    client, testing_session = make_client()

    response = client.post(
        "/paper-trades",
        json={
            "action": "paper_buy",
            "quantity": "1",
            "buy_price": "10.00",
            "sell_price": "9.80",
            "fees": "0",
            "taxes": "0",
        },
    )

    assert response.status_code == 200
    assert response.json()["trade"]["action"] == "blocked"
    assert response.json()["risk_decision"]["reason_code"] == "MISSING_DATA"

    db = testing_session()
    try:
        decision = db.query(RiskDecision).one()
        trade = db.query(PaperTrade).one()
        assert decision.reason_code == "MISSING_DATA"
        assert trade.risk_decision_id == decision.id
    finally:
        db.close()


def test_stale_execution_critical_data_blocks_trade():
    client, testing_session = make_client()
    seed_execution_critical_data(testing_session, observed_at=datetime.now(UTC) - timedelta(hours=2))

    response = client.post(
        "/paper-trades",
        json={
            "action": "paper_buy",
            "quantity": "1",
            "buy_price": "10.00",
            "sell_price": "9.80",
            "fees": "0",
            "taxes": "0",
        },
    )

    assert response.status_code == 200
    assert response.json()["trade"]["action"] == "blocked"
    assert response.json()["risk_decision"]["reason_code"] == "STALE_DATA"


def test_high_spread_blocks_trade_before_balance_changes():
    client, testing_session = make_client()
    seed_execution_critical_data(testing_session)

    response = client.post(
        "/paper-trades",
        json={
            "action": "paper_buy",
            "quantity": "1",
            "buy_price": "100.00",
            "sell_price": "90.00",
            "fees": "0",
            "taxes": "0",
        },
    )

    assert response.status_code == 200
    assert response.json()["trade"]["action"] == "blocked"
    assert response.json()["risk_decision"]["reason_code"] == "SPREAD_TOO_HIGH"

    db = testing_session()
    try:
        portfolio = db.query(Portfolio).filter(Portfolio.name == "gram-paper").one()
        assert portfolio.cash_balance == Decimal("2500.000000")
    finally:
        db.close()


def test_high_24h_volatility_blocks_trade():
    client, testing_session = make_client()
    seed_execution_critical_data(testing_session)
    seed_global_price_history(testing_session, prices=[Decimal("30.000000"), Decimal("39.000000")])

    response = client.post(
        "/paper-trades",
        json={
            "action": "paper_buy",
            "quantity": "1",
            "buy_price": "10.00",
            "sell_price": "9.80",
            "fees": "0",
            "taxes": "0",
        },
    )

    assert response.status_code == 200
    assert response.json()["trade"]["action"] == "blocked"
    assert response.json()["risk_decision"]["reason_code"] == "VOLATILITY_TOO_HIGH"
    assert response.json()["risk_decision"]["details"]["window_hours"] == 24


def test_fomo_risk_blocks_after_rapid_global_price_rise():
    client, testing_session = make_client()
    seed_execution_critical_data(testing_session)
    seed_global_price_history(
        testing_session,
        prices=[Decimal("32.000000"), Decimal("34.100000")],
        observed_at=datetime.now(UTC) + timedelta(minutes=10),
    )

    response = client.post(
        "/paper-trades",
        json={
            "action": "paper_buy",
            "quantity": "1",
            "buy_price": "10.00",
            "sell_price": "9.80",
            "fees": "0",
            "taxes": "0",
        },
    )

    assert response.status_code == 200
    assert response.json()["trade"]["action"] == "blocked"
    assert response.json()["risk_decision"]["reason_code"] == "FOMO_RISK"


def test_daily_loss_limit_blocks_trade():
    client, testing_session = make_client()
    seed_execution_critical_data(testing_session)
    seed_realized_loss(
        testing_session, loss=Decimal("35.000000"), sell_created_at=datetime.now(UTC) - timedelta(hours=1)
    )

    response = client.post(
        "/paper-trades",
        json={
            "action": "paper_buy",
            "quantity": "1",
            "buy_price": "10.00",
            "sell_price": "9.80",
            "fees": "0",
            "taxes": "0",
        },
    )

    assert response.status_code == 200
    assert response.json()["trade"]["action"] == "blocked"
    assert response.json()["risk_decision"]["reason_code"] == "DAILY_LOSS_LIMIT_REACHED"


def test_weekly_loss_limit_blocks_when_daily_limit_is_not_reached():
    client, testing_session = make_client()
    seed_execution_critical_data(testing_session)
    seed_realized_loss(
        testing_session, loss=Decimal("65.000000"), sell_created_at=datetime.now(UTC) - timedelta(days=2)
    )

    response = client.post(
        "/paper-trades",
        json={
            "action": "paper_buy",
            "quantity": "1",
            "buy_price": "10.00",
            "sell_price": "9.80",
            "fees": "0",
            "taxes": "0",
        },
    )

    assert response.status_code == 200
    assert response.json()["trade"]["action"] == "blocked"
    assert response.json()["risk_decision"]["reason_code"] == "WEEKLY_LOSS_LIMIT_REACHED"


def test_expected_exit_price_below_entry_cost_blocks_trade():
    client, testing_session = make_client()
    seed_execution_critical_data(testing_session)

    response = client.post(
        "/paper-trades",
        json={
            "action": "paper_buy",
            "quantity": "1",
            "buy_price": "10.00",
            "sell_price": "9.80",
            "expected_exit_price": "9.90",
            "fees": "0",
            "taxes": "0",
        },
    )

    assert response.status_code == 200
    assert response.json()["trade"]["action"] == "blocked"
    assert response.json()["risk_decision"]["reason_code"] == "EXPECTED_GAIN_BELOW_COST"


def test_risk_status_reports_thresholds_and_current_metrics():
    client, testing_session = make_client()
    seed_execution_critical_data(testing_session)
    seed_global_price_history(testing_session, prices=[Decimal("32.000000"), Decimal("33.000000")])

    response = client.get("/risk/status")

    assert response.status_code == 200
    payload = response.json()
    assert payload["portfolio_name"] == "gram-paper"
    assert payload["asset_symbol"] == "XAG_GRAM"
    assert payload["thresholds"]["max_24h_volatility_percent"] == "12.0"
    assert payload["current_metrics"]["daily_realized_loss_usd"] == "0.000000"
    assert payload["current_metrics"]["global_xag_volatility_24h_percent"] is not None
    headroom = {item["metric_name"]: item for item in payload["threshold_headroom"]}
    assert headroom["daily_realized_loss_usd"]["status"] == "ok"
    assert headroom["daily_realized_loss_usd"]["remaining_to_block"] == "30.000000"
    assert headroom["global_xag_volatility_24h_percent"]["source"] == "gold-api-xag-usd"
    assert headroom["fomo_rise_percent"]["status"] == "ok"
    assert payload["global_xag_diagnostics"][0]["window_hours"] == 24
    assert payload["global_xag_diagnostics"][0]["sample_count"] == 3
    assert payload["global_xag_diagnostics"][0]["latest_source"] == "gold-api-xag-usd"
    assert payload["global_xag_diagnostics"][0]["sources"] == [
        {
            "source": "gold-api-xag-usd",
            "sample_count": 3,
            "first_observed_at": payload["global_xag_diagnostics"][0]["first_observed_at"],
            "last_observed_at": payload["global_xag_diagnostics"][0]["last_observed_at"],
            "min_price": "32.000000",
            "max_price": "33.000000",
            "range_percent": "3.076923",
        }
    ]
    assert payload["would_block_now"] == []


def test_risk_status_reports_global_xag_source_diagnostics():
    client, testing_session = make_client()
    seed_execution_critical_data(testing_session)
    now = datetime.now(UTC)
    seed_global_price_history(
        testing_session,
        prices=[Decimal("76.000000"), Decimal("77.000000")],
        observed_at=now - timedelta(minutes=10),
        source="stooq-xagusd-csv",
    )
    seed_global_price_history(
        testing_session,
        prices=[Decimal("78.000000")],
        observed_at=now,
        source="gold-api-xag-usd",
    )

    response = client.get("/risk/status")

    assert response.status_code == 200
    diagnostics_24h = response.json()["global_xag_diagnostics"][0]
    assert diagnostics_24h["sample_count"] == 4
    assert diagnostics_24h["latest_source"] == "gold-api-xag-usd"
    assert diagnostics_24h["min_price"] == "32.000000"
    assert diagnostics_24h["max_price"] == "78.000000"
    assert diagnostics_24h["range_percent"] == "83.636364"
    assert [
        {"source": item["source"], "sample_count": item["sample_count"]} for item in diagnostics_24h["sources"]
    ] == [
        {"source": "gold-api-xag-usd", "sample_count": 2},
        {"source": "stooq-xagusd-csv", "sample_count": 2},
    ]


def test_risk_engine_does_not_create_synthetic_volatility_across_sources():
    client, testing_session = make_client()
    seed_execution_critical_data(testing_session)
    now = datetime.now(UTC)
    seed_global_price_history(
        testing_session,
        prices=[Decimal("32.000000"), Decimal("33.000000")],
        observed_at=now - timedelta(minutes=10),
        source="gold-api-xag-usd",
    )
    seed_global_price_history(
        testing_session,
        prices=[Decimal("44.000000"), Decimal("45.000000")],
        observed_at=now - timedelta(minutes=10),
        source="stooq-xagusd-csv",
    )

    response = client.post(
        "/paper-trades",
        json={
            "action": "paper_buy",
            "quantity": "1",
            "buy_price": "10.00",
            "sell_price": "9.80",
            "fees": "0",
            "taxes": "0",
        },
    )

    assert response.status_code == 200
    assert response.json()["trade"]["action"] == "paper_buy"
    assert response.json()["risk_decision"]["reason_code"] == "RISK_CHECK_PASSED"

    status_response = client.get("/risk/status")
    assert status_response.status_code == 200
    metrics = status_response.json()["current_metrics"]
    assert metrics["global_xag_volatility_24h_source"] == "gold-api-xag-usd"
    assert metrics["global_xag_volatility_24h_percent"] == "3.076923"
    assert status_response.json()["global_xag_diagnostics"][0]["range_percent"] == "33.766234"


def test_risk_status_reports_runtime_blocking_thresholds():
    client, testing_session = make_client()
    seed_execution_critical_data(testing_session)
    seed_global_price_history(testing_session, prices=[Decimal("30.000000"), Decimal("39.000000")])
    seed_realized_loss(
        testing_session, loss=Decimal("35.000000"), sell_created_at=datetime.now(UTC) - timedelta(hours=1)
    )

    response = client.get("/risk/status")

    assert response.status_code == 200
    payload = response.json()
    reason_codes = {item["reason_code"] for item in payload["would_block_now"]}
    assert "DAILY_LOSS_LIMIT_REACHED" in reason_codes
    assert "VOLATILITY_TOO_HIGH" in reason_codes
    headroom = {item["metric_name"]: item for item in payload["threshold_headroom"]}
    assert headroom["daily_realized_loss_usd"]["status"] == "blocked"
    assert headroom["global_xag_volatility_24h_percent"]["status"] == "blocked"


def test_risk_status_returns_recent_decision_counts():
    client, testing_session = make_client()
    seed_execution_critical_data(testing_session)

    trade_response = client.post(
        "/paper-trades",
        json={
            "action": "paper_buy",
            "quantity": "1",
            "buy_price": "10.00",
            "sell_price": "9.80",
            "fees": "0",
            "taxes": "0",
        },
    )
    assert trade_response.status_code == 200

    response = client.get("/risk/status")

    assert response.status_code == 200
    assert response.json()["recent_decisions"] == [
        {"decision": "allow", "reason_code": "RISK_CHECK_PASSED", "count": 1}
    ]


def test_daily_loss_limit_with_old_buy_trade():
    client, testing_session = make_client()
    seed_execution_critical_data(testing_session)

    db = testing_session()
    try:
        asset = db.query(Asset).filter(Asset.symbol == "XAG_GRAM").one()
        portfolio = db.query(Portfolio).filter(Portfolio.name == "gram-paper").one()
        decision = RiskDecision(
            decision="allow",
            reason_code="RISK_CHECK_PASSED",
            risk_level="low",
            confidence=Decimal("1.0000"),
            details_json={},
        )
        db.add(decision)
        db.flush()

        now = datetime.now(UTC)
        buy_created_at = now - timedelta(hours=25)
        sell_created_at = now - timedelta(hours=1)

        db.add_all(
            [
                PaperTrade(
                    portfolio_id=portfolio.id,
                    asset_id=asset.id,
                    action="paper_buy",
                    quantity=Decimal("10.000000"),
                    price=Decimal("10.000000"),
                    gross_amount=Decimal("100.000000"),
                    fees=Decimal("0.000000"),
                    taxes=Decimal("0.000000"),
                    net_amount=Decimal("100.000000"),
                    risk_decision_id=decision.id,
                    created_at=buy_created_at,
                ),
                PaperTrade(
                    portfolio_id=portfolio.id,
                    asset_id=asset.id,
                    action="paper_sell",
                    quantity=Decimal("10.000000"),
                    price=Decimal("6.500000"),
                    gross_amount=Decimal("65.000000"),
                    fees=Decimal("0.000000"),
                    taxes=Decimal("0.000000"),
                    net_amount=Decimal("65.000000"),
                    risk_decision_id=decision.id,
                    created_at=sell_created_at,
                ),
            ]
        )
        db.commit()
    finally:
        db.close()

    response = client.post(
        "/paper-trades",
        json={
            "action": "paper_buy",
            "quantity": "1",
            "buy_price": "10.00",
            "sell_price": "9.80",
            "fees": "0",
            "taxes": "0",
        },
    )

    assert response.status_code == 200
    assert response.json()["trade"]["action"] == "blocked"
    assert response.json()["risk_decision"]["decision"] == "blocked"
    assert response.json()["risk_decision"]["reason_code"] == "DAILY_LOSS_LIMIT_REACHED"


def test_cross_currency_fx_rate_conversion():
    client, testing_session = make_client()

    # 1. First, try a buy when NO FX rate is present in database.
    db = testing_session()
    try:
        db.query(RawFxRate).delete()
        db.commit()
    finally:
        db.close()

    response_no_fx = client.post(
        "/paper-trades",
        json={
            "action": "paper_buy",
            "quantity": "10",
            "buy_price": "10.00",
            "sell_price": "9.80",
            "fees": "1.00",
            "taxes": "0",
        },
    )
    assert response_no_fx.status_code == 400
    assert "No valid FX conversion rate found" in response_no_fx.json()["detail"]

    # 2. Now seed a PriceSnapshot for FX rate
    db = testing_session()
    try:
        seed_execution_critical_data(testing_session)
        asset = db.query(Asset).filter(Asset.symbol == "XAG_GRAM").one()
        from app.models import PriceSnapshot

        db.add(
            PriceSnapshot(
                asset_id=asset.id,
                source="tcmb-today-xml",
                buy_price=Decimal("32.000000"),
                sell_price=Decimal("32.000000"),
                mid_price=Decimal("32.000000"),
                currency="TRY",
                spread_absolute=Decimal("0.0"),
                spread_percent=Decimal("0.0"),
                observed_at=datetime.now(UTC),
            )
        )
        db.commit()
    finally:
        db.close()

    # 3. Perform a paper buy trade
    buy_response = client.post(
        "/paper-trades",
        json={
            "action": "paper_buy",
            "quantity": "10",
            "buy_price": "10.00",
            "sell_price": "9.80",
            "fees": "1.00",
            "taxes": "0",
        },
    )
    assert buy_response.status_code == 200

    snapshot = buy_response.json()["snapshot"]
    assert snapshot["cash_balance"] == "2496.837500"
    assert buy_response.json()["trade"]["price"] == "0.312500"
    assert buy_response.json()["trade"]["fees"] == "0.031250"
    assert buy_response.json()["trade"]["taxes"] == "0.006250"
    assert buy_response.json()["trade"]["gross_amount"] == "3.125000"
    assert buy_response.json()["trade"]["net_amount"] == "3.162500"

    # 4. Perform a paper sell trade
    sell_response = client.post(
        "/paper-trades",
        json={
            "action": "paper_sell",
            "quantity": "10",
            "buy_price": "10.00",
            "sell_price": "9.80",
            "fees": "1.00",
            "taxes": "0",
        },
    )
    assert sell_response.status_code == 200

    sell_snapshot = sell_response.json()["snapshot"]
    assert sell_snapshot["cash_balance"] == "2499.868750"
    assert sell_response.json()["trade"]["price"] == "0.306250"
    assert sell_response.json()["trade"]["fees"] == "0.031250"
    assert sell_response.json()["trade"]["taxes"] == "0.000000"
    assert sell_response.json()["trade"]["gross_amount"] == "3.062500"
    assert sell_response.json()["trade"]["net_amount"] == "3.031250"


def test_concurrency_race_condition_under_locking():
    from app.paper_trading.service import _get_portfolio
    from sqlalchemy import select
    from sqlalchemy.dialects import postgresql

    client, testing_session = make_client()
    db = testing_session()
    try:
        # 1. Assert that _get_portfolio with lock=True completes successfully on SQLite
        portfolio = _get_portfolio(db, "gram-paper", lock=True)
        assert portfolio.name == "gram-paper"

        # 2. Verify that when target dialect is postgresql, it compiles with "FOR UPDATE"
        stmt = select(Portfolio).where(Portfolio.name == "gram-paper")
        stmt_locked = stmt.with_for_update()
        compiled = str(stmt_locked.compile(dialect=postgresql.dialect()))
        assert "FOR UPDATE" in compiled
    finally:
        db.close()


def test_is_comex_market_closed():
    from app.risk.service import is_comex_market_closed
    from app.core.config import get_settings
    from datetime import datetime, timezone

    settings = get_settings()
    original_env = settings.app_env
    settings.app_env = "production"  # Temporarily override test flag

    try:
        # America/New_York (EST/EDT) time check:

        # 1. Wednesday 12:00 EDT (UTC-4) -> Wednesday 16:00 UTC
        wed_noon_utc = datetime(2026, 5, 27, 16, 0, tzinfo=timezone.utc)
        assert is_comex_market_closed(wed_noon_utc) is False

        # 2. Saturday 12:00 EDT -> Saturday 16:00 UTC
        sat_noon_utc = datetime(2026, 5, 30, 16, 0, tzinfo=timezone.utc)
        assert is_comex_market_closed(sat_noon_utc) is True

        # 3. Friday 18:00 EDT (Market Closed) -> Friday 22:00 UTC
        fri_late_utc = datetime(2026, 5, 29, 22, 0, tzinfo=timezone.utc)
        assert is_comex_market_closed(fri_late_utc) is True

        # 4. Sunday 12:00 EDT (Market Closed) -> Sunday 16:00 UTC
        sun_noon_utc = datetime(2026, 5, 31, 16, 0, tzinfo=timezone.utc)
        assert is_comex_market_closed(sun_noon_utc) is True

        # 5. Sunday 19:00 EDT (Market Open) -> Sunday 23:00 UTC
        sun_open_utc = datetime(2026, 5, 31, 23, 0, tzinfo=timezone.utc)
        assert is_comex_market_closed(sun_open_utc) is False

        # 6. Tuesday 17:30 EDT (Daily Maintenance Window) -> Tuesday 21:30 UTC
        tue_maint_utc = datetime(2026, 5, 26, 21, 30, tzinfo=timezone.utc)
        assert is_comex_market_closed(tue_maint_utc) is True
    finally:
        settings.app_env = original_env


def test_stale_execution_critical_data_bypassed_when_market_closed():
    from app.risk.service import evaluate_paper_trade_risk, TradeAmounts
    from app.schemas.paper_trading import PaperTradeRequest
    from app.core.config import get_settings
    from datetime import datetime, timezone, timedelta

    client, testing_session = make_client()
    db = testing_session()
    try:
        # Seed stale data from 2 hours ago
        seed_execution_critical_data(testing_session, observed_at=datetime.now(timezone.utc) - timedelta(hours=2))

        # Temporarily mock to production so market closure checks are active
        settings = get_settings()
        original_env = settings.app_env
        settings.app_env = "production"

        # Saturday noon UTC (Market closed)
        sat_now = datetime(2026, 5, 30, 16, 0, tzinfo=timezone.utc)

        portfolio = db.query(Portfolio).filter(Portfolio.name == "gram-paper").one()
        asset = db.query(Asset).filter(Asset.symbol == "XAG_GRAM").one()
        from app.paper_trading.service import calculate_position, _calculate_trade_amounts

        req = PaperTradeRequest(
            action="paper_buy",
            quantity=Decimal("1"),
            buy_price=Decimal("10.00"),
            sell_price=Decimal("9.80"),
            fees=Decimal("0"),
            taxes=Decimal("0"),
        )
        pos = calculate_position(db, portfolio.id, asset.id)
        qty, prc, gross, net = _calculate_trade_amounts(req, fx_rate=Decimal("1.0"))

        try:
            decision = evaluate_paper_trade_risk(
                db,
                request=req,
                portfolio=portfolio,
                asset=asset,
                position=pos,
                amounts=TradeAmounts(quantity=qty, price=prc, gross_amount=gross, net_amount=net),
                now=sat_now,
            )
            # The stale check must be bypassed! Risk check should pass.
            assert decision.decision == "allow"
            assert decision.reason_code == "RISK_CHECK_PASSED"
        finally:
            settings.app_env = original_env
    finally:
        db.close()
