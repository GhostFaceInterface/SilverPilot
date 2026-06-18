"""add paper trading orders trades positions and ledger

Revision ID: 20260618_0007
Revises: 20260618_0006
Create Date: 2026-06-18 18:00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260618_0007"
down_revision: str | None = "20260618_0006"
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
        "paper_orders",
        sa.Column("id", _uuid_type(), nullable=False),
        sa.Column("account_id", _uuid_type(), nullable=False),
        sa.Column("trade_intent_id", _uuid_type(), nullable=False),
        sa.Column("risk_decision_id", _uuid_type(), nullable=False),
        sa.Column("execution_instrument_id", _uuid_type(), nullable=False),
        sa.Column("bank_instrument_id", _uuid_type(), nullable=False),
        sa.Column("side", sa.String(length=16), nullable=False),
        sa.Column("requested_quantity", sa.Numeric(precision=24, scale=8), nullable=False),
        sa.Column("approved_quantity", sa.Numeric(precision=24, scale=8), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        *_audit_columns(),
        sa.CheckConstraint(
            "side IN ('buy', 'sell')", name=op.f("ck_paper_orders_paper_order_side_valid")
        ),
        sa.CheckConstraint(
            "status IN ('pending', 'executed', 'rejected')",
            name=op.f("ck_paper_orders_paper_order_status_valid"),
        ),
        sa.CheckConstraint(
            "requested_quantity > 0",
            name=op.f("ck_paper_orders_paper_order_requested_quantity_positive"),
        ),
        sa.CheckConstraint(
            "approved_quantity > 0",
            name=op.f("ck_paper_orders_paper_order_approved_quantity_positive"),
        ),
        sa.ForeignKeyConstraint(
            ["account_id"],
            ["virtual_accounts.id"],
            name=op.f("fk_paper_orders_account_id_virtual_accounts"),
        ),
        sa.ForeignKeyConstraint(
            ["bank_instrument_id"],
            ["bank_instruments.id"],
            name=op.f("fk_paper_orders_bank_instrument_id_bank_instruments"),
        ),
        sa.ForeignKeyConstraint(
            ["execution_instrument_id"],
            ["execution_instruments.id"],
            name=op.f("fk_paper_orders_execution_instrument_id_execution_instruments"),
        ),
        sa.ForeignKeyConstraint(
            ["risk_decision_id"],
            ["risk_decisions.id"],
            name=op.f("fk_paper_orders_risk_decision_id_risk_decisions"),
        ),
        sa.ForeignKeyConstraint(
            ["trade_intent_id"],
            ["trade_intents.id"],
            name=op.f("fk_paper_orders_trade_intent_id_trade_intents"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_paper_orders")),
        sa.UniqueConstraint(
            "risk_decision_id",
            name=op.f("uq_paper_orders_risk_decision_id"),
        ),
    )
    op.create_index("ix_paper_orders_account_status", "paper_orders", ["account_id", "status"])
    op.create_index("ix_paper_orders_risk_decision", "paper_orders", ["risk_decision_id"])

    op.create_table(
        "paper_trades",
        sa.Column("id", _uuid_type(), nullable=False),
        sa.Column("order_id", _uuid_type(), nullable=False),
        sa.Column("account_id", _uuid_type(), nullable=False),
        sa.Column("execution_instrument_id", _uuid_type(), nullable=False),
        sa.Column("bank_instrument_id", _uuid_type(), nullable=False),
        sa.Column("quote_id", _uuid_type(), nullable=False),
        sa.Column("side", sa.String(length=16), nullable=False),
        sa.Column("quantity", sa.Numeric(precision=24, scale=8), nullable=False),
        sa.Column("execution_price", sa.Numeric(precision=24, scale=8), nullable=False),
        sa.Column("gross_cash_amount", sa.Numeric(precision=24, scale=8), nullable=False),
        sa.Column("fees", sa.Numeric(precision=24, scale=8), nullable=False),
        sa.Column("taxes", sa.Numeric(precision=24, scale=8), nullable=False),
        sa.Column("spread_cost", sa.Numeric(precision=24, scale=8), nullable=False),
        sa.Column("net_cash_amount", sa.Numeric(precision=24, scale=8), nullable=False),
        sa.Column("realized_pnl", sa.Numeric(precision=24, scale=8), nullable=False),
        _timestamp_column("executed_at"),
        *_audit_columns(),
        sa.CheckConstraint(
            "side IN ('buy', 'sell')", name=op.f("ck_paper_trades_paper_trade_side_valid")
        ),
        sa.CheckConstraint(
            "quantity > 0", name=op.f("ck_paper_trades_paper_trade_quantity_positive")
        ),
        sa.CheckConstraint(
            "execution_price > 0",
            name=op.f("ck_paper_trades_paper_trade_execution_price_positive"),
        ),
        sa.CheckConstraint(
            "gross_cash_amount >= 0",
            name=op.f("ck_paper_trades_paper_trade_gross_non_negative"),
        ),
        sa.CheckConstraint("fees >= 0", name=op.f("ck_paper_trades_paper_trade_fees_non_negative")),
        sa.CheckConstraint(
            "taxes >= 0", name=op.f("ck_paper_trades_paper_trade_taxes_non_negative")
        ),
        sa.CheckConstraint(
            "spread_cost >= 0",
            name=op.f("ck_paper_trades_paper_trade_spread_cost_non_negative"),
        ),
        sa.ForeignKeyConstraint(
            ["account_id"],
            ["virtual_accounts.id"],
            name=op.f("fk_paper_trades_account_id_virtual_accounts"),
        ),
        sa.ForeignKeyConstraint(
            ["bank_instrument_id"],
            ["bank_instruments.id"],
            name=op.f("fk_paper_trades_bank_instrument_id_bank_instruments"),
        ),
        sa.ForeignKeyConstraint(
            ["execution_instrument_id"],
            ["execution_instruments.id"],
            name=op.f("fk_paper_trades_execution_instrument_id_execution_instruments"),
        ),
        sa.ForeignKeyConstraint(
            ["order_id"],
            ["paper_orders.id"],
            name=op.f("fk_paper_trades_order_id_paper_orders"),
        ),
        sa.ForeignKeyConstraint(
            ["quote_id"],
            ["price_quotes.id"],
            name=op.f("fk_paper_trades_quote_id_price_quotes"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_paper_trades")),
        sa.UniqueConstraint("order_id", name=op.f("uq_paper_trades_order_id")),
    )
    op.create_index(
        "ix_paper_trades_account_executed", "paper_trades", ["account_id", "executed_at"]
    )
    op.create_index("ix_paper_trades_order", "paper_trades", ["order_id"])

    op.create_table(
        "positions",
        sa.Column("id", _uuid_type(), nullable=False),
        sa.Column("account_id", _uuid_type(), nullable=False),
        sa.Column("bank_instrument_id", _uuid_type(), nullable=False),
        sa.Column("quantity", sa.Numeric(precision=24, scale=8), nullable=False),
        sa.Column("average_cost", sa.Numeric(precision=24, scale=8), nullable=False),
        sa.Column("realized_pnl", sa.Numeric(precision=24, scale=8), nullable=False),
        *_audit_columns(),
        sa.CheckConstraint(
            "quantity >= 0",
            name=op.f("ck_positions_position_quantity_non_negative"),
        ),
        sa.CheckConstraint(
            "average_cost >= 0",
            name=op.f("ck_positions_position_average_cost_non_negative"),
        ),
        sa.ForeignKeyConstraint(
            ["account_id"],
            ["virtual_accounts.id"],
            name=op.f("fk_positions_account_id_virtual_accounts"),
        ),
        sa.ForeignKeyConstraint(
            ["bank_instrument_id"],
            ["bank_instruments.id"],
            name=op.f("fk_positions_bank_instrument_id_bank_instruments"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_positions")),
        sa.UniqueConstraint(
            "account_id", "bank_instrument_id", name=op.f("uq_positions_account_bank")
        ),
    )
    op.create_index("ix_positions_account", "positions", ["account_id"])

    op.create_table(
        "ledger_entries",
        sa.Column("id", _uuid_type(), nullable=False),
        sa.Column("account_id", _uuid_type(), nullable=False),
        sa.Column("currency_id", _uuid_type(), nullable=False),
        sa.Column("amount", sa.Numeric(precision=24, scale=8), nullable=False),
        sa.Column("entry_type", sa.String(length=64), nullable=False),
        sa.Column("reference_type", sa.String(length=64), nullable=False),
        sa.Column("reference_id", _uuid_type(), nullable=False),
        sa.Column("metadata_json", sa.JSON(), nullable=False),
        *_audit_columns(),
        sa.ForeignKeyConstraint(
            ["account_id"],
            ["virtual_accounts.id"],
            name=op.f("fk_ledger_entries_account_id_virtual_accounts"),
        ),
        sa.ForeignKeyConstraint(
            ["currency_id"],
            ["currencies.id"],
            name=op.f("fk_ledger_entries_currency_id_currencies"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_ledger_entries")),
    )
    op.create_index(
        "ix_ledger_entries_account_created",
        "ledger_entries",
        ["account_id", "created_at"],
    )
    op.create_index(
        "ix_ledger_entries_reference",
        "ledger_entries",
        ["reference_type", "reference_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_ledger_entries_reference", table_name="ledger_entries")
    op.drop_index("ix_ledger_entries_account_created", table_name="ledger_entries")
    op.drop_table("ledger_entries")

    op.drop_index("ix_positions_account", table_name="positions")
    op.drop_table("positions")

    op.drop_index("ix_paper_trades_order", table_name="paper_trades")
    op.drop_index("ix_paper_trades_account_executed", table_name="paper_trades")
    op.drop_table("paper_trades")

    op.drop_index("ix_paper_orders_risk_decision", table_name="paper_orders")
    op.drop_index("ix_paper_orders_account_status", table_name="paper_orders")
    op.drop_table("paper_orders")
