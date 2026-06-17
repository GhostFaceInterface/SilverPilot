"""initial core schema

Revision ID: 20260617_0001
Revises:
Create Date: 2026-06-17 16:30:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260617_0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _uuid_type() -> sa.Uuid:
    return sa.Uuid(as_uuid=True)


def _timestamp_column(name: str) -> sa.Column[sa.DateTime]:
    return sa.Column(name, sa.DateTime(timezone=True), nullable=False)


def _audit_columns() -> list[sa.Column[sa.DateTime]]:
    return [
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
    ]


def upgrade() -> None:
    op.create_table(
        "currencies",
        sa.Column("id", _uuid_type(), nullable=False),
        sa.Column("code", sa.String(length=3), nullable=False),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column("decimal_places", sa.Integer(), nullable=False),
        *_audit_columns(),
        sa.CheckConstraint(
            "decimal_places >= 0 AND decimal_places <= 8",
            name=op.f("ck_currencies_decimal_places_range"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_currencies")),
        sa.UniqueConstraint("code", name=op.f("uq_currencies_code")),
    )
    op.create_table(
        "units",
        sa.Column("id", _uuid_type(), nullable=False),
        sa.Column("code", sa.String(length=16), nullable=False),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column("precision", sa.Integer(), nullable=False),
        *_audit_columns(),
        sa.CheckConstraint(
            "precision >= 0 AND precision <= 12",
            name=op.f("ck_units_precision_range"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_units")),
        sa.UniqueConstraint("code", name=op.f("uq_units_code")),
    )
    op.create_table(
        "users",
        sa.Column("id", _uuid_type(), nullable=False),
        sa.Column("email", sa.String(length=320), nullable=True),
        sa.Column("external_id", sa.String(length=200), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False),
        *_audit_columns(),
        sa.CheckConstraint(
            "email IS NOT NULL OR external_id IS NOT NULL",
            name=op.f("ck_users_identity_required"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_users")),
        sa.UniqueConstraint("email", name=op.f("uq_users_email")),
        sa.UniqueConstraint("external_id", name=op.f("uq_users_external_id")),
    )
    op.create_index("ix_users_status", "users", ["status"])
    op.create_table(
        "banks",
        sa.Column("id", _uuid_type(), nullable=False),
        sa.Column("code", sa.String(length=64), nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("country_code", sa.String(length=2), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("source_policy", sa.String(length=500), nullable=True),
        *_audit_columns(),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_banks")),
        sa.UniqueConstraint("code", name=op.f("uq_banks_code")),
    )
    op.create_index("ix_banks_status", "banks", ["status"])
    op.create_table(
        "metals",
        sa.Column("id", _uuid_type(), nullable=False),
        sa.Column("code", sa.String(length=8), nullable=False),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column("default_unit_id", _uuid_type(), nullable=False),
        *_audit_columns(),
        sa.ForeignKeyConstraint(
            ["default_unit_id"],
            ["units.id"],
            name=op.f("fk_metals_default_unit_id_units"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_metals")),
        sa.UniqueConstraint("code", name=op.f("uq_metals_code")),
    )
    op.create_table(
        "unit_conversion_rules",
        sa.Column("id", _uuid_type(), nullable=False),
        sa.Column("from_unit_id", _uuid_type(), nullable=False),
        sa.Column("to_unit_id", _uuid_type(), nullable=False),
        sa.Column("factor", sa.Numeric(precision=36, scale=18), nullable=False),
        _timestamp_column("effective_from"),
        sa.Column("effective_to", sa.DateTime(timezone=True), nullable=True),
        *_audit_columns(),
        sa.CheckConstraint("factor > 0", name=op.f("ck_unit_conversion_rules_factor_positive")),
        sa.CheckConstraint(
            "effective_to IS NULL OR effective_to > effective_from",
            name=op.f("ck_unit_conversion_rules_effective_window_valid"),
        ),
        sa.ForeignKeyConstraint(
            ["from_unit_id"],
            ["units.id"],
            name=op.f("fk_unit_conversion_rules_from_unit_id_units"),
        ),
        sa.ForeignKeyConstraint(
            ["to_unit_id"],
            ["units.id"],
            name=op.f("fk_unit_conversion_rules_to_unit_id_units"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_unit_conversion_rules")),
    )
    op.create_index(
        "ix_unit_conversion_rules_units_effective",
        "unit_conversion_rules",
        ["from_unit_id", "to_unit_id", "effective_from"],
    )
    op.create_table(
        "execution_venues",
        sa.Column("id", _uuid_type(), nullable=False),
        sa.Column("venue_type", sa.String(length=32), nullable=False),
        sa.Column("bank_id", _uuid_type(), nullable=True),
        sa.Column("code", sa.String(length=80), nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        *_audit_columns(),
        sa.ForeignKeyConstraint(
            ["bank_id"],
            ["banks.id"],
            name=op.f("fk_execution_venues_bank_id_banks"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_execution_venues")),
        sa.UniqueConstraint("code", name=op.f("uq_execution_venues_code")),
    )
    op.create_index(
        "ix_execution_venues_type_status",
        "execution_venues",
        ["venue_type", "status"],
    )
    op.create_table(
        "bank_instruments",
        sa.Column("id", _uuid_type(), nullable=False),
        sa.Column("bank_id", _uuid_type(), nullable=False),
        sa.Column("metal_id", _uuid_type(), nullable=False),
        sa.Column("currency_id", _uuid_type(), nullable=False),
        sa.Column("unit_id", _uuid_type(), nullable=False),
        sa.Column("symbol", sa.String(length=120), nullable=False),
        sa.Column("min_trade_amount", sa.Numeric(precision=24, scale=8), nullable=False),
        sa.Column("quantity_precision", sa.Integer(), nullable=False),
        sa.Column("price_precision", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        *_audit_columns(),
        sa.CheckConstraint(
            "min_trade_amount >= 0",
            name=op.f("ck_bank_instruments_min_trade_amount_non_negative"),
        ),
        sa.CheckConstraint(
            "quantity_precision >= 0 AND quantity_precision <= 12",
            name=op.f("ck_bank_instruments_quantity_precision_range"),
        ),
        sa.CheckConstraint(
            "price_precision >= 0 AND price_precision <= 8",
            name=op.f("ck_bank_instruments_price_precision_range"),
        ),
        sa.ForeignKeyConstraint(
            ["bank_id"], ["banks.id"], name=op.f("fk_bank_instruments_bank_id_banks")
        ),
        sa.ForeignKeyConstraint(
            ["currency_id"],
            ["currencies.id"],
            name=op.f("fk_bank_instruments_currency_id_currencies"),
        ),
        sa.ForeignKeyConstraint(
            ["metal_id"], ["metals.id"], name=op.f("fk_bank_instruments_metal_id_metals")
        ),
        sa.ForeignKeyConstraint(
            ["unit_id"], ["units.id"], name=op.f("fk_bank_instruments_unit_id_units")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_bank_instruments")),
        sa.UniqueConstraint(
            "bank_id",
            "metal_id",
            "currency_id",
            "unit_id",
            name=op.f("uq_bank_instruments_bank_id"),
        ),
    )
    op.create_table(
        "execution_instruments",
        sa.Column("id", _uuid_type(), nullable=False),
        sa.Column("execution_venue_id", _uuid_type(), nullable=False),
        sa.Column("bank_instrument_id", _uuid_type(), nullable=True),
        sa.Column("metal_id", _uuid_type(), nullable=False),
        sa.Column("currency_id", _uuid_type(), nullable=False),
        sa.Column("unit_id", _uuid_type(), nullable=False),
        sa.Column("symbol", sa.String(length=120), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        *_audit_columns(),
        sa.ForeignKeyConstraint(
            ["bank_instrument_id"],
            ["bank_instruments.id"],
            name=op.f("fk_execution_instruments_bank_instrument_id_bank_instruments"),
        ),
        sa.ForeignKeyConstraint(
            ["currency_id"],
            ["currencies.id"],
            name=op.f("fk_execution_instruments_currency_id_currencies"),
        ),
        sa.ForeignKeyConstraint(
            ["execution_venue_id"],
            ["execution_venues.id"],
            name=op.f("fk_execution_instruments_execution_venue_id_execution_venues"),
        ),
        sa.ForeignKeyConstraint(
            ["metal_id"],
            ["metals.id"],
            name=op.f("fk_execution_instruments_metal_id_metals"),
        ),
        sa.ForeignKeyConstraint(
            ["unit_id"], ["units.id"], name=op.f("fk_execution_instruments_unit_id_units")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_execution_instruments")),
        sa.UniqueConstraint(
            "execution_venue_id",
            "metal_id",
            "currency_id",
            "unit_id",
            name=op.f("uq_execution_instruments_execution_venue_id"),
        ),
    )
    op.create_index("ix_execution_instruments_status", "execution_instruments", ["status"])
    op.create_table(
        "reference_market_instruments",
        sa.Column("id", _uuid_type(), nullable=False),
        sa.Column("symbol", sa.String(length=120), nullable=False),
        sa.Column("source", sa.String(length=120), nullable=False),
        sa.Column("metal_id", _uuid_type(), nullable=False),
        sa.Column("currency_id", _uuid_type(), nullable=False),
        sa.Column("unit_id", _uuid_type(), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        *_audit_columns(),
        sa.ForeignKeyConstraint(
            ["currency_id"],
            ["currencies.id"],
            name=op.f("fk_reference_market_instruments_currency_id_currencies"),
        ),
        sa.ForeignKeyConstraint(
            ["metal_id"],
            ["metals.id"],
            name=op.f("fk_reference_market_instruments_metal_id_metals"),
        ),
        sa.ForeignKeyConstraint(
            ["unit_id"],
            ["units.id"],
            name=op.f("fk_reference_market_instruments_unit_id_units"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_reference_market_instruments")),
        sa.UniqueConstraint(
            "symbol", "source", name=op.f("uq_reference_market_instruments_symbol")
        ),
    )
    op.create_index(
        "ix_reference_market_instruments_status",
        "reference_market_instruments",
        ["status"],
    )
    op.create_table(
        "virtual_accounts",
        sa.Column("id", _uuid_type(), nullable=False),
        sa.Column("user_id", _uuid_type(), nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("base_currency_id", _uuid_type(), nullable=False),
        sa.Column("execution_venue_id", _uuid_type(), nullable=False),
        sa.Column("starting_balance", sa.Numeric(precision=24, scale=8), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        *_audit_columns(),
        sa.CheckConstraint(
            "starting_balance >= 0",
            name=op.f("ck_virtual_accounts_starting_balance_non_negative"),
        ),
        sa.ForeignKeyConstraint(
            ["base_currency_id"],
            ["currencies.id"],
            name=op.f("fk_virtual_accounts_base_currency_id_currencies"),
        ),
        sa.ForeignKeyConstraint(
            ["execution_venue_id"],
            ["execution_venues.id"],
            name=op.f("fk_virtual_accounts_execution_venue_id_execution_venues"),
        ),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], name=op.f("fk_virtual_accounts_user_id_users")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_virtual_accounts")),
    )
    op.create_index("ix_virtual_accounts_user_status", "virtual_accounts", ["user_id", "status"])
    op.create_table(
        "instrument_mappings",
        sa.Column("id", _uuid_type(), nullable=False),
        sa.Column("reference_market_instrument_id", _uuid_type(), nullable=False),
        sa.Column("execution_instrument_id", _uuid_type(), nullable=False),
        sa.Column("fx_pair", sa.String(length=20), nullable=True),
        sa.Column("unit_conversion_rule_id", _uuid_type(), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False),
        *_audit_columns(),
        sa.ForeignKeyConstraint(
            ["execution_instrument_id"],
            ["execution_instruments.id"],
            name=op.f("fk_instrument_mappings_execution_instrument_id_execution_instruments"),
        ),
        sa.ForeignKeyConstraint(
            ["reference_market_instrument_id"],
            ["reference_market_instruments.id"],
            name=op.f(
                "fk_instrument_mappings_reference_market_instrument_id_reference_market_instruments"
            ),
        ),
        sa.ForeignKeyConstraint(
            ["unit_conversion_rule_id"],
            ["unit_conversion_rules.id"],
            name=op.f("fk_instrument_mappings_unit_conversion_rule_id_unit_conversion_rules"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_instrument_mappings")),
        sa.UniqueConstraint(
            "reference_market_instrument_id",
            "execution_instrument_id",
            name=op.f("uq_instrument_mappings_reference_market_instrument_id"),
        ),
    )
    op.create_index(
        "ix_instrument_mappings_execution",
        "instrument_mappings",
        ["execution_instrument_id"],
    )
    op.create_index(
        "ix_instrument_mappings_reference",
        "instrument_mappings",
        ["reference_market_instrument_id"],
    )
    op.create_table(
        "price_quotes",
        sa.Column("id", _uuid_type(), nullable=False),
        sa.Column("bank_instrument_id", _uuid_type(), nullable=False),
        sa.Column("bank_buy_price", sa.Numeric(precision=24, scale=8), nullable=False),
        sa.Column("bank_sell_price", sa.Numeric(precision=24, scale=8), nullable=False),
        _timestamp_column("observed_at"),
        _timestamp_column("fetched_at"),
        sa.Column("source", sa.String(length=200), nullable=False),
        sa.Column("source_hash", sa.String(length=128), nullable=True),
        sa.Column("freshness_status", sa.String(length=32), nullable=False),
        *_audit_columns(),
        sa.CheckConstraint(
            "bank_buy_price >= 0",
            name=op.f("ck_price_quotes_bank_buy_price_non_negative"),
        ),
        sa.CheckConstraint(
            "bank_sell_price >= bank_buy_price",
            name=op.f("ck_price_quotes_sell_price_gte_buy_price"),
        ),
        sa.CheckConstraint(
            "fetched_at >= observed_at",
            name=op.f("ck_price_quotes_fetched_at_gte_observed_at"),
        ),
        sa.ForeignKeyConstraint(
            ["bank_instrument_id"],
            ["bank_instruments.id"],
            name=op.f("fk_price_quotes_bank_instrument_id_bank_instruments"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_price_quotes")),
    )
    op.create_index(
        "ix_price_quotes_instrument_observed",
        "price_quotes",
        ["bank_instrument_id", "observed_at"],
    )
    op.create_index("ix_price_quotes_fetched_at", "price_quotes", ["fetched_at"])
    op.create_table(
        "virtual_account_instruments",
        sa.Column("id", _uuid_type(), nullable=False),
        sa.Column("virtual_account_id", _uuid_type(), nullable=False),
        sa.Column("execution_instrument_id", _uuid_type(), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        *_audit_columns(),
        sa.ForeignKeyConstraint(
            ["execution_instrument_id"],
            ["execution_instruments.id"],
            name=op.f(
                "fk_virtual_account_instruments_execution_instrument_id_execution_instruments"
            ),
        ),
        sa.ForeignKeyConstraint(
            ["virtual_account_id"],
            ["virtual_accounts.id"],
            name=op.f("fk_virtual_account_instruments_virtual_account_id_virtual_accounts"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_virtual_account_instruments")),
        sa.UniqueConstraint(
            "virtual_account_id",
            "execution_instrument_id",
            name=op.f("uq_virtual_account_instruments_virtual_account_id"),
        ),
    )
    op.create_index(
        "ix_virtual_account_instruments_account",
        "virtual_account_instruments",
        ["virtual_account_id"],
    )
    op.create_table(
        "wallets",
        sa.Column("id", _uuid_type(), nullable=False),
        sa.Column("virtual_account_id", _uuid_type(), nullable=False),
        sa.Column("currency_id", _uuid_type(), nullable=False),
        sa.Column("available_amount", sa.Numeric(precision=24, scale=8), nullable=False),
        sa.Column("reserved_amount", sa.Numeric(precision=24, scale=8), nullable=False),
        *_audit_columns(),
        sa.CheckConstraint(
            "available_amount >= 0",
            name=op.f("ck_wallets_available_amount_non_negative"),
        ),
        sa.CheckConstraint(
            "reserved_amount >= 0",
            name=op.f("ck_wallets_reserved_amount_non_negative"),
        ),
        sa.ForeignKeyConstraint(
            ["currency_id"],
            ["currencies.id"],
            name=op.f("fk_wallets_currency_id_currencies"),
        ),
        sa.ForeignKeyConstraint(
            ["virtual_account_id"],
            ["virtual_accounts.id"],
            name=op.f("fk_wallets_virtual_account_id_virtual_accounts"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_wallets")),
        sa.UniqueConstraint(
            "virtual_account_id",
            "currency_id",
            name=op.f("uq_wallets_virtual_account_id"),
        ),
    )
    op.create_table(
        "market_bars",
        sa.Column("id", _uuid_type(), nullable=False),
        sa.Column("instrument_type", sa.String(length=16), nullable=False),
        sa.Column("instrument_id", _uuid_type(), nullable=False),
        sa.Column("source", sa.String(length=120), nullable=False),
        sa.Column("timeframe", sa.String(length=20), nullable=False),
        sa.Column("open", sa.Numeric(precision=24, scale=8), nullable=False),
        sa.Column("high", sa.Numeric(precision=24, scale=8), nullable=False),
        sa.Column("low", sa.Numeric(precision=24, scale=8), nullable=False),
        sa.Column("close", sa.Numeric(precision=24, scale=8), nullable=False),
        sa.Column("quote_count", sa.Integer(), nullable=False),
        _timestamp_column("bar_start_at"),
        _timestamp_column("bar_end_at"),
        *_audit_columns(),
        sa.CheckConstraint(
            "instrument_type IN ('reference', 'execution')",
            name=op.f("ck_market_bars_instrument_type_valid"),
        ),
        sa.CheckConstraint(
            "open >= 0 AND high >= 0 AND low >= 0 AND close >= 0",
            name=op.f("ck_market_bars_prices_non_negative"),
        ),
        sa.CheckConstraint(
            "high >= open AND high >= close AND high >= low",
            name=op.f("ck_market_bars_high_is_highest"),
        ),
        sa.CheckConstraint(
            "low <= open AND low <= close AND low <= high",
            name=op.f("ck_market_bars_low_is_lowest"),
        ),
        sa.CheckConstraint("quote_count > 0", name=op.f("ck_market_bars_quote_count_positive")),
        sa.CheckConstraint(
            "bar_end_at > bar_start_at", name=op.f("ck_market_bars_bar_window_valid")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_market_bars")),
        sa.UniqueConstraint(
            "instrument_type",
            "instrument_id",
            "timeframe",
            "bar_start_at",
            name=op.f("uq_market_bars_instrument_type"),
        ),
    )
    op.create_index(
        "ix_market_bars_instrument_time",
        "market_bars",
        ["instrument_type", "instrument_id", "bar_start_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_market_bars_instrument_time", table_name="market_bars")
    op.drop_table("market_bars")
    op.drop_table("wallets")
    op.drop_index(
        "ix_virtual_account_instruments_account", table_name="virtual_account_instruments"
    )
    op.drop_table("virtual_account_instruments")
    op.drop_index("ix_price_quotes_fetched_at", table_name="price_quotes")
    op.drop_index("ix_price_quotes_instrument_observed", table_name="price_quotes")
    op.drop_table("price_quotes")
    op.drop_index("ix_instrument_mappings_reference", table_name="instrument_mappings")
    op.drop_index("ix_instrument_mappings_execution", table_name="instrument_mappings")
    op.drop_table("instrument_mappings")
    op.drop_index("ix_virtual_accounts_user_status", table_name="virtual_accounts")
    op.drop_table("virtual_accounts")
    op.drop_index(
        "ix_reference_market_instruments_status",
        table_name="reference_market_instruments",
    )
    op.drop_table("reference_market_instruments")
    op.drop_index("ix_execution_instruments_status", table_name="execution_instruments")
    op.drop_table("execution_instruments")
    op.drop_table("bank_instruments")
    op.drop_index("ix_execution_venues_type_status", table_name="execution_venues")
    op.drop_table("execution_venues")
    op.drop_index(
        "ix_unit_conversion_rules_units_effective",
        table_name="unit_conversion_rules",
    )
    op.drop_table("unit_conversion_rules")
    op.drop_table("metals")
    op.drop_index("ix_banks_status", table_name="banks")
    op.drop_table("banks")
    op.drop_index("ix_users_status", table_name="users")
    op.drop_table("users")
    op.drop_table("units")
    op.drop_table("currencies")
