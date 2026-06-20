"""add delayed reference metadata

Revision ID: 20260621_0014
Revises: 20260620_0013
Create Date: 2026-06-21 10:00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260621_0014"
down_revision: str | None = "20260620_0013"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _uuid_type() -> sa.Uuid:
    return sa.Uuid(as_uuid=True)


def upgrade() -> None:
    with op.batch_alter_table("reference_market_instruments") as batch_op:
        batch_op.add_column(sa.Column("provider", sa.String(length=120), nullable=True))
        batch_op.add_column(sa.Column("exchange", sa.String(length=120), nullable=True))
        batch_op.add_column(sa.Column("timezone", sa.String(length=80), nullable=True))
        batch_op.add_column(sa.Column("data_delay_seconds", sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column("delay_policy", sa.String(length=32), nullable=True))
        batch_op.add_column(
            sa.Column("session_calendar_code", sa.String(length=80), nullable=True)
        )
        batch_op.add_column(
            sa.Column("source_terms_status", sa.String(length=32), nullable=True)
        )
        batch_op.create_check_constraint(
            "ck_reference_market_instruments_reference_market_data_delay_non_negative",
            "data_delay_seconds IS NULL OR data_delay_seconds >= 0",
        )
        batch_op.create_check_constraint(
            "ck_reference_market_instruments_reference_market_delay_policy_valid",
            "delay_policy IS NULL OR delay_policy IN "
            "('none', 'provider_delayed', 'end_of_day', 'manual_review')",
        )
        batch_op.create_check_constraint(
            "ck_reference_market_instruments_reference_market_terms_status_valid",
            "source_terms_status IS NULL OR source_terms_status IN "
            "('unknown', 'research_only', 'not_approved', 'approved')",
        )

    op.create_table(
        "reference_data_backfill_runs",
        sa.Column("id", _uuid_type(), nullable=False),
        sa.Column("source", sa.String(length=120), nullable=False),
        sa.Column("instrument_id", _uuid_type(), nullable=False),
        sa.Column("symbol", sa.String(length=120), nullable=False),
        sa.Column("timeframe", sa.String(length=20), nullable=False),
        sa.Column("period", sa.String(length=40), nullable=True),
        sa.Column("requested_start_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("requested_end_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("actual_start_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("actual_end_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("rows_inserted", sa.Integer(), nullable=False),
        sa.Column("rows_updated", sa.Integer(), nullable=False),
        sa.Column("data_hash", sa.String(length=64), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("error_summary", sa.String(length=1000), nullable=True),
        sa.Column("dry_run", sa.Boolean(), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "requested_start_at IS NULL OR requested_end_at IS NULL OR "
            "requested_end_at > requested_start_at",
            name=op.f("ck_reference_data_backfill_runs_reference_backfill_requested_window_valid"),
        ),
        sa.CheckConstraint(
            "actual_start_at IS NULL OR actual_end_at IS NULL OR actual_end_at > actual_start_at",
            name=op.f("ck_reference_data_backfill_runs_reference_backfill_actual_window_valid"),
        ),
        sa.CheckConstraint(
            "finished_at IS NULL OR finished_at >= started_at",
            name=op.f("ck_reference_data_backfill_runs_reference_backfill_finished_gte_started"),
        ),
        sa.CheckConstraint(
            "rows_inserted >= 0",
            name=op.f("ck_reference_data_backfill_runs_reference_backfill_rows_inserted_non_negative"),
        ),
        sa.CheckConstraint(
            "rows_updated >= 0",
            name=op.f("ck_reference_data_backfill_runs_reference_backfill_rows_updated_non_negative"),
        ),
        sa.CheckConstraint(
            "status IN ('blocked', 'dry_run', 'running', 'completed', 'failed')",
            name=op.f("ck_reference_data_backfill_runs_reference_backfill_status_valid"),
        ),
        sa.ForeignKeyConstraint(
            ["instrument_id"],
            ["reference_market_instruments.id"],
            name=op.f("fk_reference_data_backfill_runs_instrument_id_reference_market_instruments"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_reference_data_backfill_runs")),
    )
    op.create_index(
        "ix_reference_backfill_runs_lookup",
        "reference_data_backfill_runs",
        ["source", "instrument_id", "timeframe", "started_at"],
    )
    op.create_index(
        "ix_reference_backfill_runs_status",
        "reference_data_backfill_runs",
        ["status"],
    )

    with op.batch_alter_table("market_bars") as batch_op:
        batch_op.drop_constraint("uq_market_bars_instrument_type", type_="unique")
        batch_op.add_column(
            sa.Column("provider_reported_at", sa.DateTime(timezone=True), nullable=True)
        )
        batch_op.add_column(sa.Column("fetched_at", sa.DateTime(timezone=True), nullable=True))
        batch_op.add_column(sa.Column("stored_at", sa.DateTime(timezone=True), nullable=True))
        batch_op.add_column(sa.Column("data_delay_seconds", sa.Integer(), nullable=True))
        batch_op.add_column(
            sa.Column("signal_available_at", sa.DateTime(timezone=True), nullable=True)
        )
        batch_op.add_column(sa.Column("adjusted_close", sa.Numeric(24, 8), nullable=True))
        batch_op.add_column(sa.Column("volume", sa.Numeric(36, 8), nullable=True))
        batch_op.add_column(sa.Column("data_quality_status", sa.String(32), nullable=True))
        batch_op.add_column(sa.Column("session_status", sa.String(32), nullable=True))
        batch_op.add_column(
            sa.Column("is_backfilled", sa.Boolean(), server_default=sa.false(), nullable=False)
        )
        batch_op.add_column(sa.Column("backfill_batch_id", _uuid_type(), nullable=True))
        batch_op.create_unique_constraint(
            "uq_market_bars_instrument_type",
            ["instrument_type", "instrument_id", "source", "timeframe", "bar_start_at"],
        )
        batch_op.create_foreign_key(
            "fk_market_bars_backfill_batch_id_reference_data_backfill_runs",
            "reference_data_backfill_runs",
            ["backfill_batch_id"],
            ["id"],
        )
        batch_op.create_check_constraint(
            "ck_market_bars_market_bar_fetched_gte_provider_reported",
            "provider_reported_at IS NULL OR fetched_at IS NULL OR "
            "fetched_at >= provider_reported_at",
        )
        batch_op.create_check_constraint(
            "ck_market_bars_market_bar_stored_gte_fetched",
            "fetched_at IS NULL OR stored_at IS NULL OR stored_at >= fetched_at",
        )
        batch_op.create_check_constraint(
            "ck_market_bars_market_bar_data_delay_non_negative",
            "data_delay_seconds IS NULL OR data_delay_seconds >= 0",
        )
        batch_op.create_check_constraint(
            "ck_market_bars_market_bar_signal_available_gte_bar_end",
            "signal_available_at IS NULL OR signal_available_at >= bar_end_at",
        )
        batch_op.create_check_constraint(
            "ck_market_bars_market_bar_adjusted_close_non_negative",
            "adjusted_close IS NULL OR adjusted_close >= 0",
        )
        batch_op.create_check_constraint(
            "ck_market_bars_market_bar_volume_non_negative",
            "volume IS NULL OR volume >= 0",
        )
        batch_op.create_check_constraint(
            "ck_market_bars_market_bar_data_quality_status_valid",
            "data_quality_status IS NULL OR data_quality_status IN "
            "('unknown', 'ok', 'degraded', 'rejected')",
        )
        batch_op.create_check_constraint(
            "ck_market_bars_market_bar_session_status_valid",
            "session_status IS NULL OR session_status IN "
            "('unknown', 'open', 'closed', 'indicative_only')",
        )
        batch_op.create_index("ix_market_bars_signal_available", ["signal_available_at"])

    if op.get_bind().dialect.name != "sqlite":
        op.alter_column("market_bars", "is_backfilled", server_default=None)


def downgrade() -> None:
    with op.batch_alter_table("market_bars") as batch_op:
        batch_op.drop_index("ix_market_bars_signal_available")
        batch_op.drop_constraint(
            "ck_market_bars_market_bar_session_status_valid",
            type_="check",
        )
        batch_op.drop_constraint(
            "ck_market_bars_market_bar_data_quality_status_valid",
            type_="check",
        )
        batch_op.drop_constraint(
            "ck_market_bars_market_bar_volume_non_negative",
            type_="check",
        )
        batch_op.drop_constraint(
            "ck_market_bars_market_bar_adjusted_close_non_negative",
            type_="check",
        )
        batch_op.drop_constraint(
            "ck_market_bars_market_bar_signal_available_gte_bar_end",
            type_="check",
        )
        batch_op.drop_constraint(
            "ck_market_bars_market_bar_data_delay_non_negative",
            type_="check",
        )
        batch_op.drop_constraint(
            "ck_market_bars_market_bar_stored_gte_fetched",
            type_="check",
        )
        batch_op.drop_constraint(
            "ck_market_bars_market_bar_fetched_gte_provider_reported",
            type_="check",
        )
        batch_op.drop_constraint(
            "fk_market_bars_backfill_batch_id_reference_data_backfill_runs",
            type_="foreignkey",
        )
        batch_op.drop_constraint("uq_market_bars_instrument_type", type_="unique")
        batch_op.create_unique_constraint(
            "uq_market_bars_instrument_type",
            ["instrument_type", "instrument_id", "timeframe", "bar_start_at"],
        )
        batch_op.drop_column("backfill_batch_id")
        batch_op.drop_column("is_backfilled")
        batch_op.drop_column("session_status")
        batch_op.drop_column("data_quality_status")
        batch_op.drop_column("volume")
        batch_op.drop_column("adjusted_close")
        batch_op.drop_column("signal_available_at")
        batch_op.drop_column("data_delay_seconds")
        batch_op.drop_column("stored_at")
        batch_op.drop_column("fetched_at")
        batch_op.drop_column("provider_reported_at")

    op.drop_index("ix_reference_backfill_runs_status", table_name="reference_data_backfill_runs")
    op.drop_index("ix_reference_backfill_runs_lookup", table_name="reference_data_backfill_runs")
    op.drop_table("reference_data_backfill_runs")

    with op.batch_alter_table("reference_market_instruments") as batch_op:
        batch_op.drop_constraint(
            "ck_reference_market_instruments_reference_market_terms_status_valid",
            type_="check",
        )
        batch_op.drop_constraint(
            "ck_reference_market_instruments_reference_market_delay_policy_valid",
            type_="check",
        )
        batch_op.drop_constraint(
            "ck_reference_market_instruments_reference_market_data_delay_non_negative",
            type_="check",
        )
        batch_op.drop_column("source_terms_status")
        batch_op.drop_column("session_calendar_code")
        batch_op.drop_column("delay_policy")
        batch_op.drop_column("data_delay_seconds")
        batch_op.drop_column("timezone")
        batch_op.drop_column("exchange")
        batch_op.drop_column("provider")
