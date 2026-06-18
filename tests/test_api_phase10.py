from collections.abc import Generator
from datetime import UTC, datetime
from decimal import Decimal
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from silverpilot.app.db.base import Base
from silverpilot.app.db.models import (
    BacktestDatasetSnapshotModel,
    BacktestRunModel,
    BankInstrumentModel,
    BankModel,
    CurrencyModel,
    ExecutionInstrumentModel,
    ExecutionVenueModel,
    IndicatorSnapshotModel,
    MarketRegimeSnapshotModel,
    MetalModel,
    PaperOrderModel,
    PaperTradeModel,
    PositionModel,
    PriceQuoteModel,
    ReferenceMarketInstrumentModel,
    RiskDecisionModel,
    StrategyModel,
    StrategyRunModel,
    TradeIntentModel,
    UnitModel,
    UserModel,
    VirtualAccountInstrumentModel,
    VirtualAccountModel,
    WalletModel,
)
from silverpilot.app.db.session import get_db_session
from silverpilot.app.domain.enums import InstrumentType, MarketRegime
from silverpilot.app.indicators.service import hash_parameters
from silverpilot.app.main import create_app

NOW = datetime(2026, 6, 18, 12, 0, tzinfo=UTC)


@pytest.fixture()
def engine() -> Engine:
    db_engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
        future=True,
    )
    Base.metadata.create_all(db_engine)
    return db_engine


@pytest.fixture()
def client(engine: Engine) -> TestClient:
    app = create_app()

    def override_session() -> Generator[Session, None, None]:
        with Session(engine) as session:
            yield session

    app.dependency_overrides[get_db_session] = override_session
    return TestClient(app)


def test_read_api_exposes_accounts_wallets_static_resources_and_latest_market_state(
    engine: Engine,
    client: TestClient,
) -> None:
    fixture = _seed_api_fixture(engine)

    accounts = client.get("/api/v1/accounts?page=1&page_size=10")
    assert accounts.status_code == 200
    assert accounts.json()["meta"] == {"page": 1, "page_size": 10, "total": 1, "pages": 1}
    assert accounts.json()["items"][0]["id"] == str(fixture.account_id)
    assert accounts.json()["items"][0]["base_currency_code"] == "TRY"

    wallets = client.get(f"/api/v1/accounts/{fixture.account_id}/wallets")
    assert wallets.status_code == 200
    assert wallets.json()[0]["available_amount"] == "1000.00000000"

    banks = client.get("/api/v1/banks")
    assert banks.status_code == 200
    assert banks.json()["items"][0]["code"] == "kuveyt_turk"

    instruments = client.get("/api/v1/instruments/execution")
    assert instruments.status_code == 200
    assert instruments.json()["items"][0]["symbol"] == "KT-XAG-GRAM-TRY"

    prices = client.get(f"/api/v1/prices/latest?bank_instrument_id={fixture.bank_instrument_id}")
    assert prices.status_code == 200
    assert prices.json()["items"][0]["bank_sell_price"] == "51.00000000"

    indicators = client.get(
        "/api/v1/indicators/latest",
        params={
            "instrument_type": "reference",
            "instrument_id": str(fixture.reference_instrument_id),
            "indicator_name": "ema",
        },
    )
    assert indicators.status_code == 200
    assert indicators.json()["items"][0]["value"] == "100.000000000000000000"

    regimes = client.get(
        "/api/v1/regimes/latest",
        params={"instrument_id": str(fixture.reference_instrument_id)},
    )
    assert regimes.status_code == 200
    assert regimes.json()["items"][0]["regime"] == MarketRegime.TREND_UP.value


def test_read_api_exposes_trades_positions_backtests_reports_and_health(
    engine: Engine,
    client: TestClient,
) -> None:
    fixture = _seed_api_fixture(engine)

    trades = client.get(f"/api/v1/trades?account_id={fixture.account_id}")
    assert trades.status_code == 200
    assert trades.json()["items"][0]["net_cash_amount"] == "501.00000000"

    positions = client.get(f"/api/v1/positions?account_id={fixture.account_id}")
    assert positions.status_code == 200
    assert positions.json()["items"][0]["quantity"] == "10.00000000"

    backtests = client.get("/api/v1/backtests")
    assert backtests.status_code == 200
    assert backtests.json()["items"][0]["id"] == str(fixture.backtest_run_id)
    assert backtests.json()["items"][0]["pnl_after_costs"] == "42.00000000"

    backtest = client.get(f"/api/v1/backtests/{fixture.backtest_run_id}")
    assert backtest.status_code == 200
    assert backtest.json()["report"]["data_hash"] == "a" * 64

    report = client.get(f"/api/v1/reports/backtests/{fixture.backtest_run_id}")
    assert report.status_code == 200
    assert report.json()["report_type"] == "backtest"

    health = client.get("/api/v1/system/health")
    assert health.status_code == 200
    assert health.json() == {"status": "ok", "app": "SilverPilot"}


def test_read_api_returns_structured_not_found_for_missing_resources(client: TestClient) -> None:
    missing_id = uuid4()

    response = client.get(f"/api/v1/accounts/{missing_id}")

    assert response.status_code == 404
    assert response.json()["detail"] == {
        "error": "not_found",
        "message": "account not found",
        "details": {"id": str(missing_id)},
    }


class _ApiFixture:
    def __init__(
        self,
        *,
        account_id: UUID,
        bank_instrument_id: UUID,
        reference_instrument_id: UUID,
        backtest_run_id: UUID,
    ) -> None:
        self.account_id = account_id
        self.bank_instrument_id = bank_instrument_id
        self.reference_instrument_id = reference_instrument_id
        self.backtest_run_id = backtest_run_id


def _seed_api_fixture(engine: Engine) -> _ApiFixture:
    with Session(engine) as session:
        currency = CurrencyModel(
            id=uuid4(),
            code="TRY",
            name="Turkish Lira",
            decimal_places=2,
            created_at=NOW,
        )
        unit = UnitModel(id=uuid4(), code="GRAM", name="Gram", precision=6, created_at=NOW)
        metal = MetalModel(
            id=uuid4(),
            code="XAG",
            name="Silver",
            default_unit=unit,
            created_at=NOW,
        )
        bank = BankModel(
            id=uuid4(),
            code="kuveyt_turk",
            name="Kuveyt Turk",
            country_code="TR",
            status="active",
            source_policy="public_indicative",
            created_at=NOW,
        )
        venue = ExecutionVenueModel(
            id=uuid4(),
            venue_type="bank",
            bank=bank,
            code="kuveyt_turk",
            name="Kuveyt Turk",
            status="active",
            created_at=NOW,
        )
        bank_instrument = BankInstrumentModel(
            id=uuid4(),
            bank=bank,
            metal=metal,
            currency=currency,
            unit=unit,
            symbol="KT-XAG-GRAM-TRY",
            min_trade_amount=Decimal("100"),
            quantity_precision=4,
            price_precision=4,
            status="active",
            created_at=NOW,
        )
        execution_instrument = ExecutionInstrumentModel(
            id=uuid4(),
            execution_venue=venue,
            bank_instrument=bank_instrument,
            metal=metal,
            currency=currency,
            unit=unit,
            symbol="KT-XAG-GRAM-TRY",
            status="active",
            created_at=NOW,
        )
        reference = ReferenceMarketInstrumentModel(
            id=uuid4(),
            symbol="REF-XAG-TRY",
            source="fixture",
            metal=metal,
            currency=currency,
            unit=unit,
            status="active",
            created_at=NOW,
        )
        user = UserModel(id=uuid4(), email="owner@example.com", status="active", created_at=NOW)
        account = VirtualAccountModel(
            id=uuid4(),
            user=user,
            name="Kuveyt paper account",
            base_currency=currency,
            execution_venue=venue,
            starting_balance=Decimal("1000"),
            status="active",
            created_at=NOW,
        )
        wallet = WalletModel(
            id=uuid4(),
            virtual_account=account,
            currency=currency,
            available_amount=Decimal("1000"),
            reserved_amount=Decimal("0"),
            created_at=NOW,
        )
        allowed = VirtualAccountInstrumentModel(
            id=uuid4(),
            virtual_account=account,
            execution_instrument=execution_instrument,
            status="active",
            created_at=NOW,
        )
        strategy = StrategyModel(
            id=uuid4(),
            name="trend_up_pullback",
            version="v1",
            parameters={"cash_amount": "500"},
            enabled=True,
            created_at=NOW,
        )
        quote = PriceQuoteModel(
            id=uuid4(),
            bank_instrument=bank_instrument,
            bank_buy_price=Decimal("50"),
            bank_sell_price=Decimal("51"),
            observed_at=NOW,
            fetched_at=NOW,
            source="kuveyt_turk_finance_portal",
            source_hash="quote",
            freshness_status="fresh",
            created_at=NOW,
        )
        indicator = IndicatorSnapshotModel(
            id=uuid4(),
            instrument_type=InstrumentType.REFERENCE.value,
            instrument_id=reference.id,
            source="fixture",
            timeframe="1h",
            indicator_name="ema",
            parameters_hash=hash_parameters({"period": 50}),
            parameters={"period": 50},
            value=Decimal("100"),
            calculated_at=NOW,
            source_bar_end_at=NOW,
            created_at=NOW,
        )
        regime = MarketRegimeSnapshotModel(
            id=uuid4(),
            instrument_type=InstrumentType.REFERENCE.value,
            instrument_id=reference.id,
            source="fixture",
            timeframe="1h",
            regime=MarketRegime.TREND_UP.value,
            confidence=Decimal("0.9000"),
            evidence={"candidate_regime": "trend_up"},
            config_version="rule-v1",
            starts_at=NOW,
            confirmed_at=NOW,
            source_bar_end_at=NOW,
            created_at=NOW,
        )
        strategy_run = StrategyRunModel(
            id=uuid4(),
            strategy=strategy,
            account=account,
            instrument_type=InstrumentType.REFERENCE.value,
            instrument_id=reference.id,
            source="fixture",
            timeframe="1h",
            source_bar_end_at=NOW,
            run_at=NOW,
            regime_snapshot=regime,
            input_hash="a" * 64,
            status="intent_created",
            evidence={},
            created_at=NOW,
        )
        intent = TradeIntentModel(
            id=uuid4(),
            account=account,
            strategy_run=strategy_run,
            side="buy",
            cash_amount=Decimal("500"),
            quantity=Decimal("10"),
            signal_time=NOW,
            status="pending_risk",
            rationale="fixture",
            evidence={},
            created_at=NOW,
        )
        decision = RiskDecisionModel(
            id=uuid4(),
            trade_intent=intent,
            execution_instrument=execution_instrument,
            quote=quote,
            decision="approve",
            requested_cash_amount=Decimal("500"),
            approved_cash_amount=Decimal("500"),
            approved_quantity=Decimal("10"),
            policy_version="risk-v1",
            reasons=["approved"],
            constraints_applied={},
            evaluated_at=NOW,
            created_at=NOW,
        )
        order = PaperOrderModel(
            id=uuid4(),
            account=account,
            trade_intent=intent,
            risk_decision=decision,
            execution_instrument=execution_instrument,
            bank_instrument=bank_instrument,
            side="buy",
            requested_quantity=Decimal("10"),
            approved_quantity=Decimal("10"),
            status="executed",
            created_at=NOW,
        )
        trade = PaperTradeModel(
            id=uuid4(),
            order=order,
            account=account,
            execution_instrument=execution_instrument,
            bank_instrument=bank_instrument,
            quote=quote,
            side="buy",
            quantity=Decimal("10"),
            execution_price=Decimal("50"),
            gross_cash_amount=Decimal("500"),
            fees=Decimal("1"),
            taxes=Decimal("0"),
            spread_cost=Decimal("0"),
            net_cash_amount=Decimal("501"),
            realized_pnl=Decimal("0"),
            executed_at=NOW,
            created_at=NOW,
        )
        position = PositionModel(
            id=uuid4(),
            account=account,
            bank_instrument=bank_instrument,
            quantity=Decimal("10"),
            average_cost=Decimal("50"),
            realized_pnl=Decimal("0"),
            created_at=NOW,
        )
        dataset = BacktestDatasetSnapshotModel(
            id=uuid4(),
            instrument_type=InstrumentType.REFERENCE.value,
            instrument_id=reference.id,
            execution_instrument=execution_instrument,
            source="fixture",
            timeframe="1h",
            quote_source="kuveyt_turk_finance_portal",
            start_at=NOW,
            end_at=datetime(2026, 6, 18, 13, 0, tzinfo=UTC),
            input_ranges={},
            data_hash="a" * 64,
            created_at=NOW,
        )
        backtest = BacktestRunModel(
            id=uuid4(),
            dataset_snapshot=dataset,
            account=account,
            strategy=strategy,
            config_hash="b" * 64,
            status="completed",
            started_at=NOW,
            completed_at=NOW,
            report_json={
                "data_hash": "a" * 64,
                "pnl_after_costs": "42.00000000",
                "trade_count": 1,
                "max_drawdown": "0.01000000",
            },
            created_at=NOW,
        )
        session.add_all(
            [
                allowed,
                wallet,
                indicator,
                trade,
                position,
                backtest,
            ]
        )
        session.commit()
        return _ApiFixture(
            account_id=account.id,
            bank_instrument_id=bank_instrument.id,
            reference_instrument_id=reference.id,
            backtest_run_id=backtest.id,
        )
