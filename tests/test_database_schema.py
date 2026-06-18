from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from uuid import UUID, uuid4

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import Engine, create_engine, inspect
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from silverpilot.app.db.base import Base
from silverpilot.app.db.models import (
    BacktestDatasetSnapshotModel,
    BacktestRunModel,
    BankInstrumentModel,
    BankModel,
    CurrencyModel,
    EventRiskSnapshotModel,
    ExecutionInstrumentModel,
    ExecutionVenueModel,
    IndicatorSnapshotModel,
    MarketBarModel,
    MarketRegimeSnapshotModel,
    MetalModel,
    NewsEventModel,
    NewsSourceModel,
    PaperOrderModel,
    RiskDecisionModel,
    StrategyModel,
    StrategyRunModel,
    TradeIntentModel,
    UnitModel,
    UserModel,
    VirtualAccountInstrumentModel,
    VirtualAccountModel,
)

CORE_TABLES = {
    "backtest_dataset_snapshots",
    "backtest_runs",
    "banks",
    "bank_instruments",
    "currencies",
    "execution_instruments",
    "execution_venues",
    "instrument_mappings",
    "indicator_snapshots",
    "market_bars",
    "market_regime_snapshots",
    "metals",
    "event_risk_snapshots",
    "ledger_entries",
    "news_events",
    "news_sources",
    "paper_orders",
    "paper_trades",
    "price_quotes",
    "positions",
    "reference_market_instruments",
    "risk_decisions",
    "strategies",
    "strategy_runs",
    "trade_intents",
    "unit_conversion_rules",
    "units",
    "users",
    "virtual_account_instruments",
    "virtual_accounts",
    "wallets",
}


@pytest.fixture()
def engine() -> Engine:
    db_engine = create_engine("sqlite+pysqlite:///:memory:", future=True)
    Base.metadata.create_all(db_engine)
    return db_engine


def now() -> datetime:
    return datetime(2026, 6, 17, 12, 0, tzinfo=UTC)


def test_metadata_contains_phase_1_core_tables() -> None:
    assert CORE_TABLES.issubset(set(Base.metadata.tables))


def test_alembic_upgrade_and_downgrade_on_local_sqlite(tmp_path: Path) -> None:
    db_path = tmp_path / "schema.db"
    config = Config("alembic.ini")
    config.set_main_option("sqlalchemy.url", f"sqlite+pysqlite:///{db_path}")

    command.upgrade(config, "head")

    migrated_engine = create_engine(f"sqlite+pysqlite:///{db_path}", future=True)
    tables_after_upgrade = set(inspect(migrated_engine).get_table_names())
    assert CORE_TABLES.issubset(tables_after_upgrade)

    command.downgrade(config, "base")

    tables_after_downgrade = set(inspect(migrated_engine).get_table_names())
    assert "users" not in tables_after_downgrade
    assert "alembic_version" in tables_after_downgrade


def test_user_identity_constraint(engine: Engine) -> None:
    with Session(engine) as session:
        session.add(
            UserModel(
                id=uuid4(),
                email=None,
                external_id=None,
                status="active",
                created_at=now(),
            )
        )

        with pytest.raises(IntegrityError):
            session.commit()


def test_account_bound_execution_relationships(engine: Engine) -> None:
    created_at = now()
    currency = CurrencyModel(
        id=uuid4(),
        code="TRY",
        name="Turkish Lira",
        decimal_places=2,
        created_at=created_at,
    )
    unit = UnitModel(id=uuid4(), code="GRAM", name="Gram", precision=6, created_at=created_at)
    metal = MetalModel(
        id=uuid4(),
        code="XAG",
        name="Silver",
        default_unit=unit,
        created_at=created_at,
    )
    bank = BankModel(
        id=uuid4(),
        code="kuveyt_turk",
        name="Kuveyt Turk",
        country_code="TR",
        status="active",
        created_at=created_at,
    )
    venue = ExecutionVenueModel(
        id=uuid4(),
        venue_type="bank",
        bank=bank,
        code="kuveyt_turk",
        name="Kuveyt Turk",
        status="active",
        created_at=created_at,
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
        created_at=created_at,
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
        created_at=created_at,
    )
    user = UserModel(id=uuid4(), email="owner@example.com", status="active", created_at=created_at)
    account = VirtualAccountModel(
        id=uuid4(),
        user=user,
        name="Kuveyt paper account",
        base_currency=currency,
        execution_venue=venue,
        starting_balance=Decimal("10000"),
        status="active",
        created_at=created_at,
    )
    allowed = VirtualAccountInstrumentModel(
        id=uuid4(),
        virtual_account=account,
        execution_instrument=execution_instrument,
        status="active",
        created_at=created_at,
    )

    with Session(engine) as session:
        session.add(allowed)
        session.commit()
        session.refresh(account)

        assert account.execution_venue.code == "kuveyt_turk"
        assert account.allowed_instruments[0].execution_instrument.symbol == "KT-XAG-GRAM-TRY"


def test_market_bar_constraints_reject_invalid_price_shape(engine: Engine) -> None:
    with Session(engine) as session:
        session.add(
            MarketBarModel(
                id=uuid4(),
                instrument_type="reference",
                instrument_id=uuid4(),
                source="fixture",
                timeframe="1h",
                open=Decimal("42"),
                high=Decimal("41"),
                low=Decimal("40"),
                close=Decimal("42"),
                quote_count=1,
                bar_start_at=now(),
                bar_end_at=datetime(2026, 6, 17, 13, 0, tzinfo=UTC),
                created_at=now(),
            )
        )

        with pytest.raises(IntegrityError):
            session.commit()


def test_news_event_risk_schema_constraints(engine: Engine) -> None:
    created_at = now()
    source = NewsSourceModel(
        id=uuid4(),
        code="tcmb",
        name="TCMB",
        category="central_bank",
        reliability_score=Decimal("0.9000"),
        source_policy="official public source",
        status="active",
        created_at=created_at,
    )
    event = NewsEventModel(
        id=uuid4(),
        source=source,
        source_event_time=created_at,
        provider_reported_at=created_at,
        published_at=created_at,
        fetched_at=created_at,
        title="Policy shock",
        summary="Hawkish policy shock",
        affected_assets=["XAG"],
        event_type="central_bank",
        content_hash="hash",
        created_at=created_at,
    )
    snapshot = EventRiskSnapshotModel(
        id=uuid4(),
        news_event=event,
        source="tcmb",
        schema_version="hermes-risk-v1",
        event_type="central_bank",
        affected_assets=["XAG"],
        direction_bias="bearish",
        confidence=Decimal("0.7500"),
        time_horizon="1d",
        risk_level="high",
        reasoning="fixture",
        action_recommendation="no_trade",
        interpreted_at=created_at,
        expires_at=datetime(2026, 6, 18, 13, 0, tzinfo=UTC),
        payload={"action_recommendation": "no_trade"},
        created_at=created_at,
    )

    with Session(engine) as session:
        session.add(snapshot)
        session.commit()

        assert session.get(EventRiskSnapshotModel, snapshot.id) is not None


def test_indicator_snapshot_unique_cache_key(engine: Engine) -> None:
    source_bar_end_at = datetime(2026, 6, 17, 13, 0, tzinfo=UTC)
    instrument_id = uuid4()
    first = IndicatorSnapshotModel(
        id=uuid4(),
        instrument_type="reference",
        instrument_id=instrument_id,
        source="fixture",
        timeframe="1h",
        indicator_name="ema",
        parameters_hash="abc",
        parameters={"period": 14},
        value=Decimal("42.1"),
        calculated_at=source_bar_end_at,
        source_bar_end_at=source_bar_end_at,
        created_at=source_bar_end_at,
    )
    duplicate = IndicatorSnapshotModel(
        id=uuid4(),
        instrument_type="reference",
        instrument_id=instrument_id,
        source="fixture",
        timeframe="1h",
        indicator_name="ema",
        parameters_hash="abc",
        parameters={"period": 14},
        value=Decimal("42.2"),
        calculated_at=source_bar_end_at,
        source_bar_end_at=source_bar_end_at,
        created_at=source_bar_end_at,
    )

    with Session(engine) as session:
        session.add_all([first, duplicate])

        with pytest.raises(IntegrityError):
            session.commit()


def test_market_regime_snapshot_unique_cache_key(engine: Engine) -> None:
    source_bar_end_at = datetime(2026, 6, 17, 13, 0, tzinfo=UTC)
    instrument_id = uuid4()
    first = MarketRegimeSnapshotModel(
        id=uuid4(),
        instrument_type="reference",
        instrument_id=instrument_id,
        source="fixture",
        timeframe="1h",
        regime="trend_up",
        confidence=Decimal("0.8500"),
        evidence={"candidate_regime": "trend_up"},
        config_version="rule-v1",
        starts_at=source_bar_end_at,
        confirmed_at=source_bar_end_at,
        source_bar_end_at=source_bar_end_at,
        created_at=source_bar_end_at,
    )
    duplicate = MarketRegimeSnapshotModel(
        id=uuid4(),
        instrument_type="reference",
        instrument_id=instrument_id,
        source="fixture",
        timeframe="1h",
        regime="trend_up",
        confidence=Decimal("0.8500"),
        evidence={"candidate_regime": "trend_up"},
        config_version="rule-v1",
        starts_at=source_bar_end_at,
        confirmed_at=source_bar_end_at,
        source_bar_end_at=source_bar_end_at,
        created_at=source_bar_end_at,
    )

    with Session(engine) as session:
        session.add_all([first, duplicate])

        with pytest.raises(IntegrityError):
            session.commit()


def test_strategy_definition_unique_version(engine: Engine) -> None:
    created_at = now()
    first = StrategyModel(
        id=uuid4(),
        name="trend_up_pullback",
        version="1",
        parameters={"cash_amount": "1000"},
        enabled=True,
        created_at=created_at,
    )
    duplicate = StrategyModel(
        id=uuid4(),
        name="trend_up_pullback",
        version="1",
        parameters={"cash_amount": "2000"},
        enabled=True,
        created_at=created_at,
    )

    with Session(engine) as session:
        session.add_all([first, duplicate])

        with pytest.raises(IntegrityError):
            session.commit()


def test_risk_decision_unique_policy_version_per_intent(engine: Engine) -> None:
    created_at = now()
    with Session(engine) as session:
        account, strategy_run = _seed_account_and_strategy_run(session, created_at=created_at)
        intent = strategy_run.trade_intents[0]
        first = RiskDecisionModel(
            id=uuid4(),
            trade_intent_id=intent.id,
            decision="approve",
            requested_cash_amount=Decimal("500"),
            approved_cash_amount=Decimal("500"),
            approved_quantity=Decimal("10"),
            policy_version="risk-v1",
            reasons=["risk_approved"],
            constraints_applied={},
            evaluated_at=created_at,
            created_at=created_at,
        )
        duplicate = RiskDecisionModel(
            id=uuid4(),
            trade_intent_id=intent.id,
            decision="reject",
            requested_cash_amount=Decimal("500"),
            approved_cash_amount=Decimal("0"),
            approved_quantity=Decimal("0"),
            policy_version="risk-v1",
            reasons=["stale_quote"],
            constraints_applied={},
            evaluated_at=created_at,
            created_at=created_at,
        )
        session.add_all([account, first, duplicate])

        with pytest.raises(IntegrityError):
            session.commit()


def test_risk_decision_stores_execution_instrument_reference(engine: Engine) -> None:
    inspector = inspect(engine)
    columns = {column["name"] for column in inspector.get_columns("risk_decisions")}
    indexes = {index["name"] for index in inspector.get_indexes("risk_decisions")}
    foreign_key_columns = {
        constrained_column
        for foreign_key in inspector.get_foreign_keys("risk_decisions")
        for constrained_column in foreign_key["constrained_columns"]
    }

    assert "execution_instrument_id" in columns
    assert "ix_risk_decisions_execution_instrument" in indexes
    assert "execution_instrument_id" in foreign_key_columns


def test_paper_trading_schema_contains_execution_and_ledger_tables(engine: Engine) -> None:
    inspector = inspect(engine)
    assert {
        "paper_orders",
        "paper_trades",
        "positions",
        "ledger_entries",
    }.issubset(set(inspector.get_table_names()))
    paper_order_columns = {column["name"] for column in inspector.get_columns("paper_orders")}
    paper_order_indexes = {index["name"] for index in inspector.get_indexes("paper_orders")}
    ledger_indexes = {index["name"] for index in inspector.get_indexes("ledger_entries")}

    assert "risk_decision_id" in paper_order_columns
    assert "approved_quantity" in paper_order_columns
    assert "ix_paper_orders_risk_decision" in paper_order_indexes
    assert "ix_ledger_entries_reference" in ledger_indexes


def test_paper_order_unique_per_risk_decision(engine: Engine) -> None:
    created_at = now()
    with Session(engine) as session:
        account, strategy_run = _seed_account_and_strategy_run(session, created_at=created_at)
        intent = strategy_run.trade_intents[0]
        decision = RiskDecisionModel(
            id=uuid4(),
            trade_intent_id=intent.id,
            execution_instrument_id=account.allowed_instruments[0].execution_instrument_id,
            decision="approve",
            requested_cash_amount=Decimal("500"),
            approved_cash_amount=Decimal("500"),
            approved_quantity=Decimal("10"),
            policy_version="risk-v1",
            reasons=["risk_approved"],
            constraints_applied={},
            evaluated_at=created_at,
            created_at=created_at,
        )
        first = _paper_order(
            account_id=account.id,
            intent_id=intent.id,
            risk_decision_id=decision.id,
            execution_instrument_id=account.allowed_instruments[0].execution_instrument_id,
            bank_instrument_id=account.allowed_instruments[
                0
            ].execution_instrument.bank_instrument_id,
            created_at=created_at,
        )
        duplicate = _paper_order(
            account_id=account.id,
            intent_id=intent.id,
            risk_decision_id=decision.id,
            execution_instrument_id=account.allowed_instruments[0].execution_instrument_id,
            bank_instrument_id=account.allowed_instruments[
                0
            ].execution_instrument.bank_instrument_id,
            created_at=created_at,
        )
        session.add_all([account, decision, first, duplicate])

        with pytest.raises(IntegrityError):
            session.commit()


def test_backtest_schema_contains_dataset_and_report_tables(engine: Engine) -> None:
    inspector = inspect(engine)
    assert {"backtest_dataset_snapshots", "backtest_runs"}.issubset(
        set(inspector.get_table_names())
    )
    dataset_columns = {
        column["name"] for column in inspector.get_columns("backtest_dataset_snapshots")
    }
    run_columns = {column["name"] for column in inspector.get_columns("backtest_runs")}
    dataset_indexes = {
        index["name"] for index in inspector.get_indexes("backtest_dataset_snapshots")
    }

    assert "data_hash" in dataset_columns
    assert "input_ranges" in dataset_columns
    assert "report_json" in run_columns
    assert "ix_backtest_dataset_lookup" in dataset_indexes


def test_backtest_dataset_hash_is_unique(engine: Engine) -> None:
    created_at = now()
    with Session(engine) as session:
        account, strategy_run = _seed_account_and_strategy_run(session, created_at=created_at)
        execution_instrument_id = account.allowed_instruments[0].execution_instrument_id
        first = _backtest_dataset_snapshot(
            execution_instrument_id=execution_instrument_id,
            instrument_id=strategy_run.instrument_id,
            created_at=created_at,
        )
        duplicate = _backtest_dataset_snapshot(
            execution_instrument_id=execution_instrument_id,
            instrument_id=strategy_run.instrument_id,
            created_at=created_at,
        )
        run = BacktestRunModel(
            id=uuid4(),
            dataset_snapshot=first,
            account_id=account.id,
            strategy_id=strategy_run.strategy_id,
            config_hash="abc",
            status="completed",
            started_at=created_at,
            completed_at=created_at,
            report_json={"status": "completed"},
            created_at=created_at,
        )
        session.add_all([account, first, duplicate, run])

        with pytest.raises(IntegrityError):
            session.commit()


def _paper_order(
    *,
    account_id: UUID,
    intent_id: UUID,
    risk_decision_id: UUID,
    execution_instrument_id: UUID,
    bank_instrument_id: UUID | None,
    created_at: datetime,
) -> PaperOrderModel:
    assert bank_instrument_id is not None
    return PaperOrderModel(
        id=uuid4(),
        account_id=account_id,
        trade_intent_id=intent_id,
        risk_decision_id=risk_decision_id,
        execution_instrument_id=execution_instrument_id,
        bank_instrument_id=bank_instrument_id,
        side="buy",
        requested_quantity=Decimal("10"),
        approved_quantity=Decimal("10"),
        status="executed",
        created_at=created_at,
    )


def _backtest_dataset_snapshot(
    *,
    execution_instrument_id: UUID,
    instrument_id: UUID,
    created_at: datetime,
) -> BacktestDatasetSnapshotModel:
    return BacktestDatasetSnapshotModel(
        id=uuid4(),
        instrument_type="reference",
        instrument_id=instrument_id,
        execution_instrument_id=execution_instrument_id,
        source="reference-fixture",
        timeframe="1h",
        quote_source="kuveyt_turk_finance_portal",
        start_at=created_at,
        end_at=datetime(2026, 6, 17, 13, 0, tzinfo=UTC),
        input_ranges={"quotes": []},
        data_hash="abc",
        created_at=created_at,
    )


def _seed_account_and_strategy_run(
    session: Session,
    *,
    created_at: datetime,
) -> tuple[VirtualAccountModel, StrategyRunModel]:
    currency = CurrencyModel(
        id=uuid4(),
        code=f"T{uuid4().hex[:2]}",
        name="Turkish Lira",
        decimal_places=2,
        created_at=created_at,
    )
    unit = UnitModel(
        id=uuid4(),
        code=f"G{uuid4().hex[:4]}",
        name="Gram",
        precision=6,
        created_at=created_at,
    )
    metal = MetalModel(
        id=uuid4(),
        code=f"X{uuid4().hex[:4]}",
        name="Silver",
        default_unit=unit,
        created_at=created_at,
    )
    bank = BankModel(
        id=uuid4(),
        code=f"bank_{uuid4().hex[:8]}",
        name="Kuveyt Turk",
        country_code="TR",
        status="active",
        created_at=created_at,
    )
    venue = ExecutionVenueModel(
        id=uuid4(),
        venue_type="bank",
        bank=bank,
        code=f"venue_{uuid4().hex[:8]}",
        name="Kuveyt Turk",
        status="active",
        created_at=created_at,
    )
    user = UserModel(
        id=uuid4(),
        email=f"{uuid4().hex[:8]}@example.com",
        status="active",
        created_at=created_at,
    )
    account = VirtualAccountModel(
        id=uuid4(),
        user=user,
        name="Paper account",
        base_currency=currency,
        execution_venue=venue,
        starting_balance=Decimal("10000"),
        status="active",
        created_at=created_at,
    )
    bank_instrument = BankInstrumentModel(
        id=uuid4(),
        bank=bank,
        metal=metal,
        currency=currency,
        unit=unit,
        symbol=f"KT-XAG-{uuid4().hex[:6]}",
        min_trade_amount=Decimal("100"),
        quantity_precision=4,
        price_precision=4,
        status="active",
        created_at=created_at,
    )
    execution_instrument = ExecutionInstrumentModel(
        id=uuid4(),
        execution_venue=venue,
        bank_instrument=bank_instrument,
        metal=metal,
        currency=currency,
        unit=unit,
        symbol=f"KT-XAG-{uuid4().hex[:6]}",
        status="active",
        created_at=created_at,
    )
    allowed = VirtualAccountInstrumentModel(
        id=uuid4(),
        virtual_account=account,
        execution_instrument=execution_instrument,
        status="active",
        created_at=created_at,
    )
    strategy = StrategyModel(
        id=uuid4(),
        name="trend_up_pullback",
        version=uuid4().hex[:8],
        parameters={"cash_amount": "500"},
        enabled=True,
        created_at=created_at,
    )
    run = StrategyRunModel(
        id=uuid4(),
        strategy=strategy,
        account=account,
        instrument_type="reference",
        instrument_id=metal.id,
        source="reference-fixture",
        timeframe="1h",
        source_bar_end_at=created_at,
        run_at=created_at,
        input_hash="abc",
        status="intent_created",
        evidence={},
        created_at=created_at,
    )
    intent = TradeIntentModel(
        id=uuid4(),
        account=account,
        strategy_run=run,
        side="buy",
        cash_amount=Decimal("500"),
        quantity=None,
        signal_time=created_at,
        status="pending_risk",
        rationale="trend_up_pullback_long",
        evidence={},
        created_at=created_at,
    )
    session.add_all([allowed, intent])
    session.flush()
    return account, run
