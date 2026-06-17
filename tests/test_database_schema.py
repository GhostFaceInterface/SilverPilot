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
    MarketBarModel,
    MetalModel,
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
    "market_bars",
    "metals",
    "price_quotes",
    "reference_market_instruments",
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
