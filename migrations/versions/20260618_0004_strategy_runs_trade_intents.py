"""add strategies, strategy runs, and trade intents

Revision ID: 20260618_0004
Revises: 20260618_0003
Create Date: 2026-06-18 13:00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260618_0004"
down_revision: str | None = "20260618_0003"
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
        "strategies",
        sa.Column("id", _uuid_type(), nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("version", sa.String(length=40), nullable=False),
        sa.Column("parameters", sa.JSON(), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False),
        *_audit_columns(),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_strategies")),
        sa.UniqueConstraint("name", "version", name=op.f("uq_strategies_name")),
    )
    op.create_index("ix_strategies_enabled", "strategies", ["enabled"])

    op.create_table(
        "strategy_runs",
        sa.Column("id", _uuid_type(), nullable=False),
        sa.Column("strategy_id", _uuid_type(), nullable=False),
        sa.Column("account_id", _uuid_type(), nullable=False),
        sa.Column("instrument_type", sa.String(length=16), nullable=False),
        sa.Column("instrument_id", _uuid_type(), nullable=False),
        sa.Column("source", sa.String(length=120), nullable=False),
        sa.Column("timeframe", sa.String(length=20), nullable=False),
        _timestamp_column("source_bar_end_at"),
        _timestamp_column("run_at"),
        sa.Column("regime_snapshot_id", _uuid_type(), nullable=True),
        sa.Column("input_hash", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("evidence", sa.JSON(), nullable=False),
        *_audit_columns(),
        sa.CheckConstraint(
            "instrument_type IN ('reference', 'execution')",
            name=op.f("ck_strategy_runs_strategy_run_instrument_type_valid"),
        ),
        sa.CheckConstraint(
            "status IN ('intent_created', 'no_intent')",
            name=op.f("ck_strategy_runs_strategy_run_status_valid"),
        ),
        sa.CheckConstraint(
            "run_at >= source_bar_end_at",
            name=op.f("ck_strategy_runs_strategy_run_at_gte_source_bar_end"),
        ),
        sa.ForeignKeyConstraint(
            ["account_id"],
            ["virtual_accounts.id"],
            name=op.f("fk_strategy_runs_account_id_virtual_accounts"),
        ),
        sa.ForeignKeyConstraint(
            ["regime_snapshot_id"],
            ["market_regime_snapshots.id"],
            name=op.f("fk_strategy_runs_regime_snapshot_id_market_regime_snapshots"),
        ),
        sa.ForeignKeyConstraint(
            ["strategy_id"],
            ["strategies.id"],
            name=op.f("fk_strategy_runs_strategy_id_strategies"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_strategy_runs")),
    )
    op.create_index("ix_strategy_runs_strategy_time", "strategy_runs", ["strategy_id", "run_at"])
    op.create_index("ix_strategy_runs_account_time", "strategy_runs", ["account_id", "run_at"])

    op.create_table(
        "trade_intents",
        sa.Column("id", _uuid_type(), nullable=False),
        sa.Column("account_id", _uuid_type(), nullable=False),
        sa.Column("strategy_run_id", _uuid_type(), nullable=False),
        sa.Column("side", sa.String(length=16), nullable=False),
        sa.Column("cash_amount", sa.Numeric(precision=24, scale=8), nullable=False),
        sa.Column("quantity", sa.Numeric(precision=24, scale=8), nullable=True),
        _timestamp_column("signal_time"),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("rationale", sa.String(length=500), nullable=False),
        sa.Column("evidence", sa.JSON(), nullable=False),
        *_audit_columns(),
        sa.CheckConstraint(
            "side IN ('buy')",
            name=op.f("ck_trade_intents_trade_intent_side_valid"),
        ),
        sa.CheckConstraint(
            "status IN ('pending_risk')",
            name=op.f("ck_trade_intents_trade_intent_status_valid"),
        ),
        sa.CheckConstraint(
            "cash_amount > 0",
            name=op.f("ck_trade_intents_trade_intent_cash_amount_positive"),
        ),
        sa.CheckConstraint(
            "quantity IS NULL OR quantity > 0",
            name=op.f("ck_trade_intents_trade_intent_quantity_positive"),
        ),
        sa.ForeignKeyConstraint(
            ["account_id"],
            ["virtual_accounts.id"],
            name=op.f("fk_trade_intents_account_id_virtual_accounts"),
        ),
        sa.ForeignKeyConstraint(
            ["strategy_run_id"],
            ["strategy_runs.id"],
            name=op.f("fk_trade_intents_strategy_run_id_strategy_runs"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_trade_intents")),
    )
    op.create_index(
        "ix_trade_intents_account_status",
        "trade_intents",
        ["account_id", "status"],
    )
    op.create_index("ix_trade_intents_strategy_run", "trade_intents", ["strategy_run_id"])


def downgrade() -> None:
    op.drop_index("ix_trade_intents_strategy_run", table_name="trade_intents")
    op.drop_index("ix_trade_intents_account_status", table_name="trade_intents")
    op.drop_table("trade_intents")
    op.drop_index("ix_strategy_runs_account_time", table_name="strategy_runs")
    op.drop_index("ix_strategy_runs_strategy_time", table_name="strategy_runs")
    op.drop_table("strategy_runs")
    op.drop_index("ix_strategies_enabled", table_name="strategies")
    op.drop_table("strategies")
