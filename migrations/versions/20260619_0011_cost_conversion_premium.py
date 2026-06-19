"""add cost breakdown and execution premium snapshots

Revision ID: 20260619_0011
Revises: 20260618_0010
Create Date: 2026-06-19 12:00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260619_0011"
down_revision: str | None = "20260618_0010"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _uuid_type() -> sa.Uuid:
    return sa.Uuid(as_uuid=True)


def _audit_columns() -> list[sa.Column[sa.DateTime]]:
    return [
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
    ]


def upgrade() -> None:
    op.add_column("paper_trades", sa.Column("cost_breakdown", sa.JSON(), nullable=True))

    op.create_table(
        "execution_premium_snapshots",
        sa.Column("id", _uuid_type(), nullable=False),
        sa.Column("execution_instrument_id", _uuid_type(), nullable=False),
        sa.Column("bank_instrument_id", _uuid_type(), nullable=False),
        sa.Column("price_quote_id", _uuid_type(), nullable=True),
        sa.Column("reference_price", sa.Numeric(precision=24, scale=8), nullable=False),
        sa.Column("reference_currency_code", sa.String(length=3), nullable=False),
        sa.Column("reference_unit_code", sa.String(length=16), nullable=False),
        sa.Column("execution_currency_code", sa.String(length=3), nullable=False),
        sa.Column("execution_unit_code", sa.String(length=16), nullable=False),
        sa.Column("fx_rate", sa.Numeric(precision=36, scale=18), nullable=True),
        sa.Column("fx_source", sa.String(length=120), nullable=True),
        sa.Column("unit_conversion", sa.JSON(), nullable=True),
        sa.Column("converted_reference_price", sa.Numeric(precision=24, scale=8), nullable=True),
        sa.Column("bank_buy_price", sa.Numeric(precision=24, scale=8), nullable=False),
        sa.Column("bank_sell_price", sa.Numeric(precision=24, scale=8), nullable=False),
        sa.Column("bank_spread", sa.Numeric(precision=24, scale=8), nullable=False),
        sa.Column("buy_discount", sa.Numeric(precision=24, scale=8), nullable=True),
        sa.Column("sell_premium", sa.Numeric(precision=24, scale=8), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("provenance", sa.JSON(), nullable=False),
        sa.Column("captured_at", sa.DateTime(timezone=True), nullable=False),
        *_audit_columns(),
        sa.CheckConstraint(
            "reference_price > 0",
            name=op.f("ck_execution_premium_snapshots_premium_reference_price_positive"),
        ),
        sa.CheckConstraint(
            "bank_buy_price >= 0",
            name=op.f("ck_execution_premium_snapshots_premium_bank_buy_non_negative"),
        ),
        sa.CheckConstraint(
            "bank_sell_price >= bank_buy_price",
            name=op.f("ck_execution_premium_snapshots_premium_sell_gte_buy"),
        ),
        sa.CheckConstraint(
            "bank_spread >= 0",
            name=op.f("ck_execution_premium_snapshots_premium_spread_non_negative"),
        ),
        sa.CheckConstraint(
            "fx_rate IS NULL OR fx_rate > 0",
            name=op.f("ck_execution_premium_snapshots_premium_fx_rate_positive"),
        ),
        sa.CheckConstraint(
            "status IN ('ok', 'missing_fx_rate')",
            name=op.f("ck_execution_premium_snapshots_premium_status_valid"),
        ),
        sa.ForeignKeyConstraint(
            ["bank_instrument_id"],
            ["bank_instruments.id"],
            name=op.f("fk_execution_premium_snapshots_bank_instrument_id_bank_instruments"),
        ),
        sa.ForeignKeyConstraint(
            ["execution_instrument_id"],
            ["execution_instruments.id"],
            name=op.f(
                "fk_execution_premium_snapshots_execution_instrument_id_execution_instruments"
            ),
        ),
        sa.ForeignKeyConstraint(
            ["price_quote_id"],
            ["price_quotes.id"],
            name=op.f("fk_execution_premium_snapshots_price_quote_id_price_quotes"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_execution_premium_snapshots")),
    )
    op.create_index(
        "ix_execution_premium_instrument_captured",
        "execution_premium_snapshots",
        ["execution_instrument_id", "captured_at"],
    )
    op.create_index(
        "ix_execution_premium_status",
        "execution_premium_snapshots",
        ["status"],
    )


def downgrade() -> None:
    op.drop_index("ix_execution_premium_status", table_name="execution_premium_snapshots")
    op.drop_index(
        "ix_execution_premium_instrument_captured",
        table_name="execution_premium_snapshots",
    )
    op.drop_table("execution_premium_snapshots")
    op.drop_column("paper_trades", "cost_breakdown")
