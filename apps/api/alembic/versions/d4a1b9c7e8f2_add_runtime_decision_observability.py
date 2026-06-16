"""add runtime decision observability

Revision ID: d4a1b9c7e8f2
Revises: 8c2f6b7a9d10
Create Date: 2026-06-16 00:00:00.000000
"""

from alembic import op
import sqlalchemy as sa


revision = "d4a1b9c7e8f2"
down_revision = "8c2f6b7a9d10"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "runtime_heartbeats",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("component", sa.String(length=64), nullable=False),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expected_next_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("details_json", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("component", name="uq_runtime_heartbeats_component"),
    )
    op.create_index(op.f("ix_runtime_heartbeats_component"), "runtime_heartbeats", ["component"], unique=False)
    op.create_index(op.f("ix_runtime_heartbeats_created_at"), "runtime_heartbeats", ["created_at"], unique=False)
    op.create_index(
        op.f("ix_runtime_heartbeats_expected_next_at"), "runtime_heartbeats", ["expected_next_at"], unique=False
    )
    op.create_index(op.f("ix_runtime_heartbeats_last_seen_at"), "runtime_heartbeats", ["last_seen_at"], unique=False)
    op.create_index(op.f("ix_runtime_heartbeats_status"), "runtime_heartbeats", ["status"], unique=False)
    op.create_index(op.f("ix_runtime_heartbeats_updated_at"), "runtime_heartbeats", ["updated_at"], unique=False)

    op.create_table(
        "trading_decision_runs",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("trigger_collector_run_id", sa.Integer(), nullable=True),
        sa.Column("signal_id", sa.Integer(), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("mode", sa.String(length=32), nullable=False),
        sa.Column("strategy_name", sa.String(length=128), nullable=True),
        sa.Column("asset_symbol", sa.String(length=32), nullable=False),
        sa.Column("source_health_json", sa.JSON(), nullable=False),
        sa.Column("indicator_readiness_json", sa.JSON(), nullable=False),
        sa.Column("action", sa.String(length=32), nullable=True),
        sa.Column("reason_code", sa.String(length=64), nullable=True),
        sa.Column("execution_result_json", sa.JSON(), nullable=False),
        sa.Column("notification_result_json", sa.JSON(), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("details_json", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["signal_id"], ["signals.id"]),
        sa.ForeignKeyConstraint(["trigger_collector_run_id"], ["collector_runs.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_trading_decision_runs_action"), "trading_decision_runs", ["action"], unique=False)
    op.create_index(
        op.f("ix_trading_decision_runs_asset_symbol"), "trading_decision_runs", ["asset_symbol"], unique=False
    )
    op.create_index(op.f("ix_trading_decision_runs_created_at"), "trading_decision_runs", ["created_at"], unique=False)
    op.create_index(
        op.f("ix_trading_decision_runs_finished_at"), "trading_decision_runs", ["finished_at"], unique=False
    )
    op.create_index(op.f("ix_trading_decision_runs_mode"), "trading_decision_runs", ["mode"], unique=False)
    op.create_index(
        op.f("ix_trading_decision_runs_reason_code"), "trading_decision_runs", ["reason_code"], unique=False
    )
    op.create_index(op.f("ix_trading_decision_runs_signal_id"), "trading_decision_runs", ["signal_id"], unique=False)
    op.create_index(op.f("ix_trading_decision_runs_started_at"), "trading_decision_runs", ["started_at"], unique=False)
    op.create_index(op.f("ix_trading_decision_runs_status"), "trading_decision_runs", ["status"], unique=False)
    op.create_index(
        op.f("ix_trading_decision_runs_strategy_name"), "trading_decision_runs", ["strategy_name"], unique=False
    )
    op.create_index(
        op.f("ix_trading_decision_runs_trigger_collector_run_id"),
        "trading_decision_runs",
        ["trigger_collector_run_id"],
        unique=False,
    )
    op.create_index(op.f("ix_trading_decision_runs_updated_at"), "trading_decision_runs", ["updated_at"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_trading_decision_runs_updated_at"), table_name="trading_decision_runs")
    op.drop_index(op.f("ix_trading_decision_runs_trigger_collector_run_id"), table_name="trading_decision_runs")
    op.drop_index(op.f("ix_trading_decision_runs_strategy_name"), table_name="trading_decision_runs")
    op.drop_index(op.f("ix_trading_decision_runs_status"), table_name="trading_decision_runs")
    op.drop_index(op.f("ix_trading_decision_runs_started_at"), table_name="trading_decision_runs")
    op.drop_index(op.f("ix_trading_decision_runs_signal_id"), table_name="trading_decision_runs")
    op.drop_index(op.f("ix_trading_decision_runs_reason_code"), table_name="trading_decision_runs")
    op.drop_index(op.f("ix_trading_decision_runs_mode"), table_name="trading_decision_runs")
    op.drop_index(op.f("ix_trading_decision_runs_finished_at"), table_name="trading_decision_runs")
    op.drop_index(op.f("ix_trading_decision_runs_created_at"), table_name="trading_decision_runs")
    op.drop_index(op.f("ix_trading_decision_runs_asset_symbol"), table_name="trading_decision_runs")
    op.drop_index(op.f("ix_trading_decision_runs_action"), table_name="trading_decision_runs")
    op.drop_table("trading_decision_runs")

    op.drop_index(op.f("ix_runtime_heartbeats_updated_at"), table_name="runtime_heartbeats")
    op.drop_index(op.f("ix_runtime_heartbeats_status"), table_name="runtime_heartbeats")
    op.drop_index(op.f("ix_runtime_heartbeats_last_seen_at"), table_name="runtime_heartbeats")
    op.drop_index(op.f("ix_runtime_heartbeats_expected_next_at"), table_name="runtime_heartbeats")
    op.drop_index(op.f("ix_runtime_heartbeats_created_at"), table_name="runtime_heartbeats")
    op.drop_index(op.f("ix_runtime_heartbeats_component"), table_name="runtime_heartbeats")
    op.drop_table("runtime_heartbeats")
