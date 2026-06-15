"""add instrument account ledger

Revision ID: 8c2f6b7a9d10
Revises: 5b9d6c2e4f10
Create Date: 2026-06-15 00:00:00.000000
"""

from decimal import Decimal

from alembic import op
import sqlalchemy as sa


revision = "8c2f6b7a9d10"
down_revision = "5b9d6c2e4f10"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    json_default = sa.text("'{}'::json") if bind.dialect.name == "postgresql" else sa.text("'{}'")

    op.create_table(
        "currencies",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("code", sa.String(length=8), nullable=False),
        sa.Column("name", sa.String(length=64), nullable=False),
        sa.Column("numeric_code", sa.String(length=3), nullable=True),
        sa.Column("minor_unit", sa.Integer(), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_currencies_code"), "currencies", ["code"], unique=True)
    op.create_index(op.f("ix_currencies_created_at"), "currencies", ["created_at"], unique=False)

    op.create_table(
        "measurement_units",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("code", sa.String(length=32), nullable=False),
        sa.Column("name", sa.String(length=64), nullable=False),
        sa.Column("unit_type", sa.String(length=32), nullable=False),
        sa.Column("to_base_factor", sa.Numeric(precision=18, scale=8), nullable=False),
        sa.Column("base_unit_code", sa.String(length=32), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_measurement_units_code"), "measurement_units", ["code"], unique=True)
    op.create_index(op.f("ix_measurement_units_created_at"), "measurement_units", ["created_at"], unique=False)
    op.create_index(op.f("ix_measurement_units_unit_type"), "measurement_units", ["unit_type"], unique=False)

    op.create_table(
        "instruments",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("symbol", sa.String(length=32), nullable=False),
        sa.Column("name", sa.String(length=128), nullable=False),
        sa.Column("instrument_type", sa.String(length=32), nullable=False),
        sa.Column("native_currency_id", sa.Integer(), nullable=True),
        sa.Column("native_unit_id", sa.Integer(), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("metadata_json", sa.JSON(), server_default=json_default, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["native_currency_id"], ["currencies.id"]),
        sa.ForeignKeyConstraint(["native_unit_id"], ["measurement_units.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_instruments_symbol"), "instruments", ["symbol"], unique=True)
    op.create_index(op.f("ix_instruments_instrument_type"), "instruments", ["instrument_type"], unique=False)
    op.create_index(op.f("ix_instruments_native_currency_id"), "instruments", ["native_currency_id"], unique=False)
    op.create_index(op.f("ix_instruments_native_unit_id"), "instruments", ["native_unit_id"], unique=False)
    op.create_index(op.f("ix_instruments_created_at"), "instruments", ["created_at"], unique=False)

    with op.batch_alter_table("assets") as batch_op:
        batch_op.add_column(sa.Column("instrument_id", sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column("unit_id", sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column("quote_currency_id", sa.Integer(), nullable=True))
        batch_op.create_foreign_key("fk_assets_instrument_id", "instruments", ["instrument_id"], ["id"])
        batch_op.create_foreign_key("fk_assets_unit_id", "measurement_units", ["unit_id"], ["id"])
        batch_op.create_foreign_key("fk_assets_quote_currency_id", "currencies", ["quote_currency_id"], ["id"])
        batch_op.create_index(op.f("ix_assets_instrument_id"), ["instrument_id"])
        batch_op.create_index(op.f("ix_assets_unit_id"), ["unit_id"])
        batch_op.create_index(op.f("ix_assets_quote_currency_id"), ["quote_currency_id"])

    op.create_table(
        "provider_accounts",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("tenant_id", sa.String(length=64), nullable=False),
        sa.Column("provider_id", sa.Integer(), nullable=False),
        sa.Column("portfolio_id", sa.Integer(), nullable=True),
        sa.Column("account_key", sa.String(length=128), nullable=False),
        sa.Column("display_name", sa.String(length=128), nullable=False),
        sa.Column("account_type", sa.String(length=32), nullable=False),
        sa.Column("base_currency_id", sa.Integer(), nullable=True),
        sa.Column("is_paper", sa.Boolean(), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("metadata_json", sa.JSON(), server_default=json_default, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["base_currency_id"], ["currencies.id"]),
        sa.ForeignKeyConstraint(["portfolio_id"], ["portfolios.id"]),
        sa.ForeignKeyConstraint(["provider_id"], ["providers.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("tenant_id", "provider_id", "account_key", name="uq_provider_accounts_tenant_provider_key"),
    )
    op.create_index(op.f("ix_provider_accounts_tenant_id"), "provider_accounts", ["tenant_id"], unique=False)
    op.create_index(op.f("ix_provider_accounts_provider_id"), "provider_accounts", ["provider_id"], unique=False)
    op.create_index(op.f("ix_provider_accounts_portfolio_id"), "provider_accounts", ["portfolio_id"], unique=False)
    op.create_index(op.f("ix_provider_accounts_account_key"), "provider_accounts", ["account_key"], unique=False)
    op.create_index(op.f("ix_provider_accounts_account_type"), "provider_accounts", ["account_type"], unique=False)
    op.create_index(
        op.f("ix_provider_accounts_base_currency_id"), "provider_accounts", ["base_currency_id"], unique=False
    )
    op.create_index(op.f("ix_provider_accounts_is_paper"), "provider_accounts", ["is_paper"], unique=False)
    op.create_index(op.f("ix_provider_accounts_is_active"), "provider_accounts", ["is_active"], unique=False)
    op.create_index(op.f("ix_provider_accounts_created_at"), "provider_accounts", ["created_at"], unique=False)

    op.create_table(
        "trade_intents",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("signal_id", sa.Integer(), nullable=True),
        sa.Column("portfolio_id", sa.Integer(), nullable=True),
        sa.Column("asset_id", sa.Integer(), nullable=True),
        sa.Column("action", sa.String(length=32), nullable=False),
        sa.Column("confidence", sa.Numeric(precision=5, scale=4), nullable=False),
        sa.Column("reason_code", sa.String(length=64), nullable=False),
        sa.Column("stop_loss_price", sa.Numeric(precision=18, scale=6), nullable=True),
        sa.Column("take_profit_price", sa.Numeric(precision=18, scale=6), nullable=True),
        sa.Column("expected_exit_price", sa.Numeric(precision=18, scale=6), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("risk_decision_id", sa.Integer(), nullable=True),
        sa.Column("metadata_json", sa.JSON(), server_default=json_default, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["asset_id"], ["assets.id"]),
        sa.ForeignKeyConstraint(["portfolio_id"], ["portfolios.id"]),
        sa.ForeignKeyConstraint(["risk_decision_id"], ["risk_decisions.id"]),
        sa.ForeignKeyConstraint(["signal_id"], ["signals.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    for column in ("signal_id", "portfolio_id", "asset_id", "action", "reason_code", "status", "risk_decision_id"):
        op.create_index(op.f(f"ix_trade_intents_{column}"), "trade_intents", [column], unique=False)
    op.create_index(op.f("ix_trade_intents_created_at"), "trade_intents", ["created_at"], unique=False)
    op.create_index(op.f("ix_trade_intents_updated_at"), "trade_intents", ["updated_at"], unique=False)

    with op.batch_alter_table("paper_trades") as batch_op:
        batch_op.add_column(sa.Column("trade_intent_id", sa.Integer(), nullable=True))
        batch_op.create_foreign_key("fk_paper_trades_trade_intent_id", "trade_intents", ["trade_intent_id"], ["id"])
        batch_op.create_index(op.f("ix_paper_trades_trade_intent_id"), ["trade_intent_id"])

    op.create_table(
        "account_ledger_entries",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("account_id", sa.Integer(), nullable=False),
        sa.Column("asset_id", sa.Integer(), nullable=True),
        sa.Column("instrument_id", sa.Integer(), nullable=True),
        sa.Column("unit_id", sa.Integer(), nullable=True),
        sa.Column("currency_id", sa.Integer(), nullable=True),
        sa.Column("quote_currency_id", sa.Integer(), nullable=True),
        sa.Column("entry_type", sa.String(length=32), nullable=False),
        sa.Column("quantity_delta", sa.Numeric(precision=18, scale=6), nullable=False),
        sa.Column("cash_delta", sa.Numeric(precision=18, scale=6), nullable=False),
        sa.Column("price", sa.Numeric(precision=18, scale=6), nullable=True),
        sa.Column("gross_amount", sa.Numeric(precision=18, scale=6), nullable=False),
        sa.Column("fees", sa.Numeric(precision=18, scale=6), nullable=False),
        sa.Column("taxes", sa.Numeric(precision=18, scale=6), nullable=False),
        sa.Column("paper_trade_id", sa.Integer(), nullable=True),
        sa.Column("trade_intent_id", sa.Integer(), nullable=True),
        sa.Column("risk_decision_id", sa.Integer(), nullable=True),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("details_json", sa.JSON(), server_default=json_default, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["account_id"], ["provider_accounts.id"]),
        sa.ForeignKeyConstraint(["asset_id"], ["assets.id"]),
        sa.ForeignKeyConstraint(["currency_id"], ["currencies.id"]),
        sa.ForeignKeyConstraint(["instrument_id"], ["instruments.id"]),
        sa.ForeignKeyConstraint(["paper_trade_id"], ["paper_trades.id"]),
        sa.ForeignKeyConstraint(["quote_currency_id"], ["currencies.id"]),
        sa.ForeignKeyConstraint(["risk_decision_id"], ["risk_decisions.id"]),
        sa.ForeignKeyConstraint(["trade_intent_id"], ["trade_intents.id"]),
        sa.ForeignKeyConstraint(["unit_id"], ["measurement_units.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    for column in (
        "account_id",
        "asset_id",
        "instrument_id",
        "unit_id",
        "currency_id",
        "quote_currency_id",
        "entry_type",
        "paper_trade_id",
        "trade_intent_id",
        "risk_decision_id",
        "occurred_at",
        "created_at",
    ):
        op.create_index(op.f(f"ix_account_ledger_entries_{column}"), "account_ledger_entries", [column], unique=False)
    op.create_index(
        "ix_account_ledger_entries_account_occurred",
        "account_ledger_entries",
        ["account_id", "occurred_at", "id"],
        unique=False,
    )
    op.create_index(
        "ix_account_ledger_entries_asset_dimension",
        "account_ledger_entries",
        ["account_id", "asset_id", "instrument_id", "unit_id"],
        unique=False,
    )

    op.create_table(
        "account_holding_snapshots",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("account_id", sa.Integer(), nullable=False),
        sa.Column("asset_id", sa.Integer(), nullable=True),
        sa.Column("instrument_id", sa.Integer(), nullable=True),
        sa.Column("unit_id", sa.Integer(), nullable=True),
        sa.Column("currency_id", sa.Integer(), nullable=True),
        sa.Column("quantity", sa.Numeric(precision=18, scale=6), nullable=False),
        sa.Column("cash_balance", sa.Numeric(precision=18, scale=6), nullable=False),
        sa.Column("source_ledger_entry_id", sa.Integer(), nullable=True),
        sa.Column("observed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("details_json", sa.JSON(), server_default=json_default, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["account_id"], ["provider_accounts.id"]),
        sa.ForeignKeyConstraint(["asset_id"], ["assets.id"]),
        sa.ForeignKeyConstraint(["currency_id"], ["currencies.id"]),
        sa.ForeignKeyConstraint(["instrument_id"], ["instruments.id"]),
        sa.ForeignKeyConstraint(["source_ledger_entry_id"], ["account_ledger_entries.id"]),
        sa.ForeignKeyConstraint(["unit_id"], ["measurement_units.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "account_id",
            "asset_id",
            "instrument_id",
            "unit_id",
            "currency_id",
            name="uq_account_holding_snapshot_dimension",
        ),
    )
    for column in (
        "account_id",
        "asset_id",
        "instrument_id",
        "unit_id",
        "currency_id",
        "source_ledger_entry_id",
        "observed_at",
        "created_at",
    ):
        op.create_index(op.f(f"ix_account_holding_snapshots_{column}"), "account_holding_snapshots", [column])
    op.create_index(
        "ix_account_holding_snapshots_account_dimension",
        "account_holding_snapshots",
        ["account_id", "asset_id", "instrument_id", "unit_id", "currency_id"],
        unique=False,
    )

    op.create_table(
        "indicator_definitions",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("code", sa.String(length=64), nullable=False),
        sa.Column("display_name", sa.String(length=128), nullable=False),
        sa.Column("value_type", sa.String(length=32), nullable=False),
        sa.Column("calculation_version", sa.String(length=64), nullable=False),
        sa.Column("params_json", sa.JSON(), server_default=json_default, nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("code", "calculation_version", name="uq_indicator_definitions_code_version"),
    )
    for column in ("code", "calculation_version", "is_active", "created_at"):
        op.create_index(op.f(f"ix_indicator_definitions_{column}"), "indicator_definitions", [column])

    op.create_table(
        "technical_indicator_values",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("technical_indicator_id", sa.Integer(), nullable=False),
        sa.Column("indicator_definition_id", sa.Integer(), nullable=False),
        sa.Column("numeric_value", sa.Numeric(precision=18, scale=8), nullable=True),
        sa.Column("text_value", sa.Text(), nullable=True),
        sa.Column("value_json", sa.JSON(), server_default=json_default, nullable=False),
        sa.Column("quality_status", sa.String(length=32), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["indicator_definition_id"], ["indicator_definitions.id"]),
        sa.ForeignKeyConstraint(["technical_indicator_id"], ["technical_indicators.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "technical_indicator_id",
            "indicator_definition_id",
            name="uq_technical_indicator_values_indicator_definition",
        ),
    )
    for column in ("technical_indicator_id", "indicator_definition_id", "quality_status", "created_at"):
        op.create_index(op.f(f"ix_technical_indicator_values_{column}"), "technical_indicator_values", [column])

    _seed_reference_data()


def downgrade() -> None:
    for column in ("technical_indicator_id", "indicator_definition_id", "quality_status", "created_at"):
        op.drop_index(op.f(f"ix_technical_indicator_values_{column}"), table_name="technical_indicator_values")
    op.drop_table("technical_indicator_values")

    for column in ("code", "calculation_version", "is_active", "created_at"):
        op.drop_index(op.f(f"ix_indicator_definitions_{column}"), table_name="indicator_definitions")
    op.drop_table("indicator_definitions")

    op.drop_index("ix_account_holding_snapshots_account_dimension", table_name="account_holding_snapshots")
    for column in (
        "account_id",
        "asset_id",
        "instrument_id",
        "unit_id",
        "currency_id",
        "source_ledger_entry_id",
        "observed_at",
        "created_at",
    ):
        op.drop_index(op.f(f"ix_account_holding_snapshots_{column}"), table_name="account_holding_snapshots")
    op.drop_table("account_holding_snapshots")

    op.drop_index("ix_account_ledger_entries_asset_dimension", table_name="account_ledger_entries")
    op.drop_index("ix_account_ledger_entries_account_occurred", table_name="account_ledger_entries")
    for column in (
        "account_id",
        "asset_id",
        "instrument_id",
        "unit_id",
        "currency_id",
        "quote_currency_id",
        "entry_type",
        "paper_trade_id",
        "trade_intent_id",
        "risk_decision_id",
        "occurred_at",
        "created_at",
    ):
        op.drop_index(op.f(f"ix_account_ledger_entries_{column}"), table_name="account_ledger_entries")
    op.drop_table("account_ledger_entries")

    with op.batch_alter_table("paper_trades") as batch_op:
        batch_op.drop_index(op.f("ix_paper_trades_trade_intent_id"))
        batch_op.drop_constraint("fk_paper_trades_trade_intent_id", type_="foreignkey")
        batch_op.drop_column("trade_intent_id")

    for column in ("signal_id", "portfolio_id", "asset_id", "action", "reason_code", "status", "risk_decision_id"):
        op.drop_index(op.f(f"ix_trade_intents_{column}"), table_name="trade_intents")
    op.drop_index(op.f("ix_trade_intents_created_at"), table_name="trade_intents")
    op.drop_index(op.f("ix_trade_intents_updated_at"), table_name="trade_intents")
    op.drop_table("trade_intents")

    for column in (
        "tenant_id",
        "provider_id",
        "portfolio_id",
        "account_key",
        "account_type",
        "base_currency_id",
        "is_paper",
        "is_active",
        "created_at",
    ):
        op.drop_index(op.f(f"ix_provider_accounts_{column}"), table_name="provider_accounts")
    op.drop_table("provider_accounts")

    with op.batch_alter_table("assets") as batch_op:
        batch_op.drop_index(op.f("ix_assets_quote_currency_id"))
        batch_op.drop_index(op.f("ix_assets_unit_id"))
        batch_op.drop_index(op.f("ix_assets_instrument_id"))
        batch_op.drop_constraint("fk_assets_quote_currency_id", type_="foreignkey")
        batch_op.drop_constraint("fk_assets_unit_id", type_="foreignkey")
        batch_op.drop_constraint("fk_assets_instrument_id", type_="foreignkey")
        batch_op.drop_column("quote_currency_id")
        batch_op.drop_column("unit_id")
        batch_op.drop_column("instrument_id")

    op.drop_index(op.f("ix_instruments_created_at"), table_name="instruments")
    op.drop_index(op.f("ix_instruments_native_unit_id"), table_name="instruments")
    op.drop_index(op.f("ix_instruments_native_currency_id"), table_name="instruments")
    op.drop_index(op.f("ix_instruments_instrument_type"), table_name="instruments")
    op.drop_index(op.f("ix_instruments_symbol"), table_name="instruments")
    op.drop_table("instruments")

    op.drop_index(op.f("ix_measurement_units_unit_type"), table_name="measurement_units")
    op.drop_index(op.f("ix_measurement_units_created_at"), table_name="measurement_units")
    op.drop_index(op.f("ix_measurement_units_code"), table_name="measurement_units")
    op.drop_table("measurement_units")

    op.drop_index(op.f("ix_currencies_created_at"), table_name="currencies")
    op.drop_index(op.f("ix_currencies_code"), table_name="currencies")
    op.drop_table("currencies")


def _seed_reference_data() -> None:
    bind = op.get_bind()
    _insert_currency(bind, "USD", "US Dollar", "840", 2)
    _insert_currency(bind, "TRY", "Turkish Lira", "949", 2)
    _insert_currency(bind, "EUR", "Euro", "978", 2)
    _insert_unit(bind, "gram", "Gram", "mass", Decimal("1.00000000"), "gram")
    _insert_unit(bind, "troy_ounce", "Troy Ounce", "mass", Decimal("31.10350000"), "gram")
    _insert_unit(bind, "currency_unit", "Currency Unit", "currency", Decimal("1.00000000"), "currency_unit")
    _insert_instrument(bind, "XAG", "Silver", "metal", native_unit="troy_ounce")
    _insert_instrument(bind, "XAU", "Gold", "metal", native_unit="troy_ounce")
    _insert_instrument(bind, "USD", "US Dollar", "currency", native_currency="USD")
    _insert_instrument(bind, "TRY", "Turkish Lira", "currency", native_currency="TRY")
    _insert_instrument(bind, "EUR", "Euro", "currency", native_currency="EUR")
    _map_asset(bind, "XAG", "XAG", "troy_ounce", "USD")
    _map_asset(bind, "XAG_GRAM", "XAG", "gram", "USD")
    _map_asset(bind, "XAG_TRY", "XAG", "gram", "TRY")


def _insert_currency(bind, code: str, name: str, numeric_code: str, minor_unit: int) -> None:
    if bind.execute(sa.text("SELECT id FROM currencies WHERE code = :code"), {"code": code}).first():
        return
    bind.execute(
        sa.text(
            "INSERT INTO currencies (code, name, numeric_code, minor_unit, is_active) "
            "VALUES (:code, :name, :numeric_code, :minor_unit, :is_active)"
        ),
        {"code": code, "name": name, "numeric_code": numeric_code, "minor_unit": minor_unit, "is_active": True},
    )


def _insert_unit(bind, code: str, name: str, unit_type: str, factor: Decimal, base_unit_code: str) -> None:
    if bind.execute(sa.text("SELECT id FROM measurement_units WHERE code = :code"), {"code": code}).first():
        return
    bind.execute(
        sa.text(
            "INSERT INTO measurement_units (code, name, unit_type, to_base_factor, base_unit_code, is_active) "
            "VALUES (:code, :name, :unit_type, :factor, :base_unit_code, :is_active)"
        ),
        {
            "code": code,
            "name": name,
            "unit_type": unit_type,
            "factor": factor,
            "base_unit_code": base_unit_code,
            "is_active": True,
        },
    )


def _insert_instrument(
    bind,
    symbol: str,
    name: str,
    instrument_type: str,
    *,
    native_currency: str | None = None,
    native_unit: str | None = None,
) -> None:
    if bind.execute(sa.text("SELECT id FROM instruments WHERE symbol = :symbol"), {"symbol": symbol}).first():
        return
    currency_id = _lookup_id(bind, "currencies", "code", native_currency) if native_currency else None
    unit_id = _lookup_id(bind, "measurement_units", "code", native_unit) if native_unit else None
    bind.execute(
        sa.text(
            "INSERT INTO instruments "
            "(symbol, name, instrument_type, native_currency_id, native_unit_id, is_active, metadata_json) "
            "VALUES (:symbol, :name, :instrument_type, :currency_id, :unit_id, :is_active, :metadata_json)"
        ),
        {
            "symbol": symbol,
            "name": name,
            "instrument_type": instrument_type,
            "currency_id": currency_id,
            "unit_id": unit_id,
            "is_active": True,
            "metadata_json": "{}",
        },
    )


def _map_asset(bind, asset_symbol: str, instrument_symbol: str, unit_code: str, quote_currency_code: str) -> None:
    instrument_id = _lookup_id(bind, "instruments", "symbol", instrument_symbol)
    unit_id = _lookup_id(bind, "measurement_units", "code", unit_code)
    currency_id = _lookup_id(bind, "currencies", "code", quote_currency_code)
    if instrument_id is None or unit_id is None or currency_id is None:
        return
    bind.execute(
        sa.text(
            "UPDATE assets SET instrument_id = :instrument_id, unit_id = :unit_id, "
            "quote_currency_id = :currency_id WHERE symbol = :asset_symbol"
        ),
        {
            "instrument_id": instrument_id,
            "unit_id": unit_id,
            "currency_id": currency_id,
            "asset_symbol": asset_symbol,
        },
    )


def _lookup_id(bind, table: str, column: str, value: str | None) -> int | None:
    if value is None:
        return None
    row = bind.execute(sa.text(f"SELECT id FROM {table} WHERE {column} = :value"), {"value": value}).first()
    return row[0] if row else None
