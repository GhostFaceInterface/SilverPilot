"""add backtest dataset snapshots and runs

Revision ID: 20260618_0008
Revises: 20260618_0007
Create Date: 2026-06-18 19:00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260618_0008"
down_revision: str | None = "20260618_0007"
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
    op.create_table(
        "backtest_dataset_snapshots",
        sa.Column("id", _uuid_type(), nullable=False),
        sa.Column("instrument_type", sa.String(length=16), nullable=False),
        sa.Column("instrument_id", _uuid_type(), nullable=False),
        sa.Column("execution_instrument_id", _uuid_type(), nullable=False),
        sa.Column("source", sa.String(length=120), nullable=False),
        sa.Column("timeframe", sa.String(length=20), nullable=False),
        sa.Column("quote_source", sa.String(length=200), nullable=False),
        sa.Column("start_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("end_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("input_ranges", sa.JSON(), nullable=False),
        sa.Column("data_hash", sa.String(length=64), nullable=False),
        *_audit_columns(),
        sa.CheckConstraint(
            "instrument_type IN ('reference', 'execution')",
            name=op.f("ck_backtest_dataset_snapshots_backtest_dataset_instrument_type_valid"),
        ),
        sa.CheckConstraint(
            "end_at > start_at",
            name=op.f("ck_backtest_dataset_snapshots_backtest_dataset_window_valid"),
        ),
        sa.ForeignKeyConstraint(
            ["execution_instrument_id"],
            ["execution_instruments.id"],
            name=op.f(
                "fk_backtest_dataset_snapshots_execution_instrument_id_execution_instruments"
            ),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_backtest_dataset_snapshots")),
        sa.UniqueConstraint("data_hash", name=op.f("uq_backtest_dataset_snapshots_data_hash")),
    )
    op.create_index(
        "ix_backtest_dataset_lookup",
        "backtest_dataset_snapshots",
        ["instrument_type", "instrument_id", "timeframe", "start_at", "end_at"],
    )

    op.create_table(
        "backtest_runs",
        sa.Column("id", _uuid_type(), nullable=False),
        sa.Column("dataset_snapshot_id", _uuid_type(), nullable=False),
        sa.Column("account_id", _uuid_type(), nullable=False),
        sa.Column("strategy_id", _uuid_type(), nullable=False),
        sa.Column("config_hash", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("report_json", sa.JSON(), nullable=False),
        *_audit_columns(),
        sa.CheckConstraint(
            "status IN ('completed', 'failed')",
            name=op.f("ck_backtest_runs_backtest_run_status_valid"),
        ),
        sa.CheckConstraint(
            "completed_at IS NULL OR completed_at >= started_at",
            name=op.f("ck_backtest_runs_backtest_completed_gte_started"),
        ),
        sa.ForeignKeyConstraint(
            ["account_id"],
            ["virtual_accounts.id"],
            name=op.f("fk_backtest_runs_account_id_virtual_accounts"),
        ),
        sa.ForeignKeyConstraint(
            ["dataset_snapshot_id"],
            ["backtest_dataset_snapshots.id"],
            name=op.f("fk_backtest_runs_dataset_snapshot_id_backtest_dataset_snapshots"),
        ),
        sa.ForeignKeyConstraint(
            ["strategy_id"],
            ["strategies.id"],
            name=op.f("fk_backtest_runs_strategy_id_strategies"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_backtest_runs")),
    )
    op.create_index("ix_backtest_runs_dataset", "backtest_runs", ["dataset_snapshot_id"])
    op.create_index("ix_backtest_runs_account", "backtest_runs", ["account_id"])
    op.create_index("ix_backtest_runs_strategy", "backtest_runs", ["strategy_id"])


def downgrade() -> None:
    op.drop_index("ix_backtest_runs_strategy", table_name="backtest_runs")
    op.drop_index("ix_backtest_runs_account", table_name="backtest_runs")
    op.drop_index("ix_backtest_runs_dataset", table_name="backtest_runs")
    op.drop_table("backtest_runs")
    op.drop_index("ix_backtest_dataset_lookup", table_name="backtest_dataset_snapshots")
    op.drop_table("backtest_dataset_snapshots")
