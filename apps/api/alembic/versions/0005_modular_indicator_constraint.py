"""Modular constraint: TechnicalIndicator unique on (price_snapshot_id, timeframe).

This replaces the old (bar_timestamp, timeframe) constraint to support multiple
asset-types (XAG, XAG_GRAM, XAU_GRAM) recording indicators at the same timestamp.

Revision ID: 0005_modular_indicator_constraint
Revises: 3e7a45f0cd22
Create Date: 2026-05-26
"""

from alembic import op


revision = "0005_modular_indicator_constraint"
down_revision = "3e7a45f0cd22"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Drop old constraint that prevented multi-asset indicators at same timestamp
    op.drop_constraint(
        "uq_technical_indicators_timestamp_timeframe",
        "technical_indicators",
        type_="unique",
    )

    # Create new constraint scoped to price_snapshot_id (inherently asset-specific)
    op.create_unique_constraint(
        "uq_technical_indicators_snapshot_timeframe",
        "technical_indicators",
        ["price_snapshot_id", "timeframe"],
    )


def downgrade() -> None:
    op.drop_constraint(
        "uq_technical_indicators_snapshot_timeframe",
        "technical_indicators",
        type_="unique",
    )

    op.create_unique_constraint(
        "uq_technical_indicators_timestamp_timeframe",
        "technical_indicators",
        ["bar_timestamp", "timeframe"],
    )
