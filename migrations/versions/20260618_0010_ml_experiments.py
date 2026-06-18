"""add offline ml experiment metadata

Revision ID: 20260618_0010
Revises: 20260618_0009
Create Date: 2026-06-18 22:30:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260618_0010"
down_revision: str | None = "20260618_0009"
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
        "ml_dataset_snapshots",
        sa.Column("id", _uuid_type(), nullable=False),
        sa.Column("source_dataset_snapshot_id", _uuid_type(), nullable=False),
        sa.Column("feature_spec", sa.JSON(), nullable=False),
        sa.Column("label_spec", sa.JSON(), nullable=False),
        sa.Column("split_spec", sa.JSON(), nullable=False),
        sa.Column("start_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("end_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("row_count", sa.Integer(), nullable=False),
        sa.Column("class_balance", sa.JSON(), nullable=False),
        sa.Column("artifact_uri", sa.String(length=500), nullable=False),
        sa.Column("artifact_hash", sa.String(length=64), nullable=False),
        sa.Column("data_hash", sa.String(length=64), nullable=False),
        *_audit_columns(),
        sa.CheckConstraint(
            "end_at > start_at",
            name=op.f("ck_ml_dataset_snapshots_ml_dataset_window_valid"),
        ),
        sa.CheckConstraint(
            "row_count >= 0",
            name=op.f("ck_ml_dataset_snapshots_ml_dataset_row_count_non_negative"),
        ),
        sa.ForeignKeyConstraint(
            ["source_dataset_snapshot_id"],
            ["backtest_dataset_snapshots.id"],
            name=op.f(
                "fk_ml_dataset_snapshots_source_dataset_snapshot_id_backtest_dataset_snapshots"
            ),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_ml_dataset_snapshots")),
        sa.UniqueConstraint("data_hash", name=op.f("uq_ml_dataset_snapshots_data_hash")),
    )
    op.create_index(
        "ix_ml_dataset_source",
        "ml_dataset_snapshots",
        ["source_dataset_snapshot_id"],
    )
    op.create_index(
        "ix_ml_dataset_lookup",
        "ml_dataset_snapshots",
        ["start_at", "end_at", "row_count"],
    )

    op.create_table(
        "ml_experiment_runs",
        sa.Column("id", _uuid_type(), nullable=False),
        sa.Column("dataset_snapshot_id", _uuid_type(), nullable=False),
        sa.Column("model_family", sa.String(length=80), nullable=False),
        sa.Column("hyperparameters", sa.JSON(), nullable=False),
        sa.Column("random_seed", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("report_json", sa.JSON(), nullable=False),
        *_audit_columns(),
        sa.CheckConstraint(
            "status IN ('completed', 'failed', 'insufficient_data')",
            name=op.f("ck_ml_experiment_runs_ml_experiment_status_valid"),
        ),
        sa.CheckConstraint(
            "completed_at IS NULL OR completed_at >= started_at",
            name=op.f("ck_ml_experiment_runs_ml_experiment_completed_gte_started"),
        ),
        sa.ForeignKeyConstraint(
            ["dataset_snapshot_id"],
            ["ml_dataset_snapshots.id"],
            name=op.f("fk_ml_experiment_runs_dataset_snapshot_id_ml_dataset_snapshots"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_ml_experiment_runs")),
    )
    op.create_index(
        "ix_ml_experiment_runs_dataset",
        "ml_experiment_runs",
        ["dataset_snapshot_id"],
    )
    op.create_index(
        "ix_ml_experiment_runs_model_status",
        "ml_experiment_runs",
        ["model_family", "status"],
    )

    op.create_table(
        "ml_experiment_metrics",
        sa.Column("id", _uuid_type(), nullable=False),
        sa.Column("experiment_run_id", _uuid_type(), nullable=False),
        sa.Column("split", sa.String(length=40), nullable=False),
        sa.Column("metric_name", sa.String(length=120), nullable=False),
        sa.Column("metric_value", sa.Numeric(precision=24, scale=12), nullable=False),
        sa.Column("metric_metadata", sa.JSON(), nullable=False),
        *_audit_columns(),
        sa.ForeignKeyConstraint(
            ["experiment_run_id"],
            ["ml_experiment_runs.id"],
            name=op.f("fk_ml_experiment_metrics_experiment_run_id_ml_experiment_runs"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_ml_experiment_metrics")),
        sa.UniqueConstraint(
            "experiment_run_id",
            "split",
            "metric_name",
            name=op.f("uq_ml_experiment_metrics_run_split_metric"),
        ),
    )
    op.create_index(
        "ix_ml_experiment_metrics_run",
        "ml_experiment_metrics",
        ["experiment_run_id"],
    )
    op.create_index(
        "ix_ml_experiment_metrics_name",
        "ml_experiment_metrics",
        ["metric_name"],
    )


def downgrade() -> None:
    op.drop_index("ix_ml_experiment_metrics_name", table_name="ml_experiment_metrics")
    op.drop_index("ix_ml_experiment_metrics_run", table_name="ml_experiment_metrics")
    op.drop_table("ml_experiment_metrics")
    op.drop_index("ix_ml_experiment_runs_model_status", table_name="ml_experiment_runs")
    op.drop_index("ix_ml_experiment_runs_dataset", table_name="ml_experiment_runs")
    op.drop_table("ml_experiment_runs")
    op.drop_index("ix_ml_dataset_lookup", table_name="ml_dataset_snapshots")
    op.drop_index("ix_ml_dataset_source", table_name="ml_dataset_snapshots")
    op.drop_table("ml_dataset_snapshots")
