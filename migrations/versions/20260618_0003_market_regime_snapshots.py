"""add market regime snapshots

Revision ID: 20260618_0003
Revises: 20260617_0002
Create Date: 2026-06-18 12:00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260618_0003"
down_revision: str | None = "20260617_0002"
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
        "market_regime_snapshots",
        sa.Column("id", _uuid_type(), nullable=False),
        sa.Column("instrument_type", sa.String(length=16), nullable=False),
        sa.Column("instrument_id", _uuid_type(), nullable=False),
        sa.Column("source", sa.String(length=120), nullable=False),
        sa.Column("timeframe", sa.String(length=20), nullable=False),
        sa.Column("regime", sa.String(length=32), nullable=False),
        sa.Column("confidence", sa.Numeric(precision=5, scale=4), nullable=False),
        sa.Column("evidence", sa.JSON(), nullable=False),
        sa.Column("config_version", sa.String(length=80), nullable=False),
        _timestamp_column("starts_at"),
        _timestamp_column("confirmed_at"),
        _timestamp_column("source_bar_end_at"),
        *_audit_columns(),
        sa.CheckConstraint(
            "instrument_type IN ('reference', 'execution')",
            name=op.f("ck_market_regime_snapshots_market_regime_instrument_type_valid"),
        ),
        sa.CheckConstraint(
            "regime IN ('trend_up', 'trend_down', 'range', 'high_volatility', "
            "'low_volatility', 'no_trade')",
            name=op.f("ck_market_regime_snapshots_market_regime_value_valid"),
        ),
        sa.CheckConstraint(
            "confidence >= 0 AND confidence <= 1",
            name=op.f("ck_market_regime_snapshots_regime_confidence_range"),
        ),
        sa.CheckConstraint(
            "confirmed_at >= starts_at",
            name=op.f("ck_market_regime_snapshots_regime_confirmed_gte_starts"),
        ),
        sa.CheckConstraint(
            "confirmed_at >= source_bar_end_at",
            name=op.f("ck_market_regime_snapshots_regime_confirmed_gte_source_bar_end"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_market_regime_snapshots")),
        sa.UniqueConstraint(
            "instrument_type",
            "instrument_id",
            "source",
            "timeframe",
            "source_bar_end_at",
            "config_version",
            name=op.f("uq_market_regime_snapshots_instrument_type"),
        ),
    )
    op.create_index(
        "ix_market_regime_snapshots_lookup",
        "market_regime_snapshots",
        ["instrument_type", "instrument_id", "timeframe", "source_bar_end_at"],
    )
    op.create_index(
        "ix_market_regime_snapshots_confirmed",
        "market_regime_snapshots",
        ["confirmed_at"],
    )
    op.create_index(
        "ix_market_regime_snapshots_regime",
        "market_regime_snapshots",
        ["regime"],
    )


def downgrade() -> None:
    op.drop_index("ix_market_regime_snapshots_regime", table_name="market_regime_snapshots")
    op.drop_index("ix_market_regime_snapshots_confirmed", table_name="market_regime_snapshots")
    op.drop_index("ix_market_regime_snapshots_lookup", table_name="market_regime_snapshots")
    op.drop_table("market_regime_snapshots")
