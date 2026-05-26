"""make_technical_indicator_modular

Revision ID: b2813bc6e7b0
Revises: 3e7a45f0cd22
Create Date: 2026-05-26 15:50:25.983230
"""

from alembic import op

revision = "b2813bc6e7b0"
down_revision = "3e7a45f0cd22"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_constraint("uq_technical_indicators_timestamp_timeframe", "technical_indicators", type_="unique")
    op.create_unique_constraint(
        "uq_technical_indicators_snapshot_timeframe", "technical_indicators", ["price_snapshot_id", "timeframe"]
    )


def downgrade() -> None:
    op.drop_constraint("uq_technical_indicators_snapshot_timeframe", "technical_indicators", type_="unique")
    op.create_unique_constraint(
        "uq_technical_indicators_timestamp_timeframe", "technical_indicators", ["bar_timestamp", "timeframe"]
    )
