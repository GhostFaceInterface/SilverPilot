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
    db.add(Asset(symbol="XAG", name="Silver", asset_type="metal", is_active=True))
    db.add(
        Portfolio(
            name="default-paper",
            base_currency="USD",
            initial_cash=Decimal("600.000000"),
            cash_balance=Decimal("600.000000"),
            is_real_money=False,
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
        asset = db.query(Asset).filter(Asset.symbol == "XAG").one()
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
    assert buy_response.json()["snapshot"]["cash_balance"] == "499.000000"
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
    assert snapshot["cash_balance"] == "596.000000"
    assert Decimal(snapshot["portfolio_value"]) < Decimal("600.000000")
    assert Decimal(snapshot["realized_pnl"]) < Decimal("0")


def test_buy_cannot_make_cash_balance_negative():
    client, testing_session = make_client()
    seed_execution_critical_data(testing_session)

    response = client.post(
        "/paper-trades",
        json={
            "action": "paper_buy",
            "quantity": "100",
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
        portfolio = db.query(Portfolio).filter(Portfolio.name == "default-paper").one()
        trade = db.query(PaperTrade).one()
        assert portfolio.cash_balance == Decimal("600.000000")
        assert trade.action == "blocked"
        assert trade.risk_decision_id is not None
    finally:
        db.close()


def test_real_money_portfolio_is_rejected():
    client, testing_session = make_client()
    db = testing_session()
    try:
        portfolio = db.query(Portfolio).filter(Portfolio.name == "default-paper").one()
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
        portfolio = db.query(Portfolio).filter(Portfolio.name == "default-paper").one()
        assert portfolio.cash_balance == Decimal("600.000000")
    finally:
        db.close()
