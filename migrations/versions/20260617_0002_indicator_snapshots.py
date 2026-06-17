"""add indicator snapshot cache

Revision ID: 20260617_0002
Revises: 20260617_0001
Create Date: 2026-06-17 18:30:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260617_0002"
down_revision: str | None = "20260617_0001"
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
        "indicator_snapshots",
        sa.Column("id", _uuid_type(), nullable=False),
        sa.Column("instrument_type", sa.String(length=16), nullable=False),
        sa.Column("instrument_id", _uuid_type(), nullable=False),
        sa.Column("source", sa.String(length=120), nullable=False),
        sa.Column("timeframe", sa.String(length=20), nullable=False),
        sa.Column("indicator_name", sa.String(length=80), nullable=False),
        sa.Column("parameters_hash", sa.String(length=64), nullable=False),
        sa.Column("parameters", sa.JSON(), nullable=False),
        sa.Column("value", sa.Numeric(precision=36, scale=18), nullable=False),
        _timestamp_column("calculated_at"),
        _timestamp_column("source_bar_end_at"),
        *_audit_columns(),
        sa.CheckConstraint(
            "instrument_type IN ('reference', 'execution')",
            name=op.f("ck_indicator_snapshots_indicator_instrument_type_valid"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_indicator_snapshots")),
        sa.UniqueConstraint(
            "instrument_type",
            "instrument_id",
            "source",
            "timeframe",
            "indicator_name",
            "parameters_hash",
            "source_bar_end_at",
            name=op.f("uq_indicator_snapshots_instrument_type"),
        ),
    )
    op.create_index(
        "ix_indicator_snapshots_lookup",
        "indicator_snapshots",
        [
            "instrument_type",
            "instrument_id",
            "timeframe",
            "indicator_name",
            "source_bar_end_at",
        ],
    )


def downgrade() -> None:
    op.drop_index("ix_indicator_snapshots_lookup", table_name="indicator_snapshots")
    op.drop_table("indicator_snapshots")
