from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from uuid import uuid4

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import Engine, create_engine, inspect
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from silverpilot.app.db.base import Base
from silverpilot.app.db.models import (
    BankInstrumentModel,
    BankModel,
    CurrencyModel,
    ExecutionInstrumentModel,
    ExecutionVenueModel,
    IndicatorSnapshotModel,
    MarketBarModel,
    MarketRegimeSnapshotModel,
    MetalModel,
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
    "price_quotes",
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
    session.add_all([metal, intent])
    session.flush()
    return account, run
