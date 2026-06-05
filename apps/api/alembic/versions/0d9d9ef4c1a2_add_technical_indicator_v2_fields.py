"""add technical indicator v2 fields

Revision ID: 0d9d9ef4c1a2
Revises: c81f0a9d2e6b
Create Date: 2026-06-06 00:00:00.000000
"""

from alembic import op
import sqlalchemy as sa


revision = "0d9d9ef4c1a2"
down_revision = "c81f0a9d2e6b"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("technical_indicators", sa.Column("ema_20", sa.Numeric(precision=10, scale=4), nullable=True))
    op.add_column("technical_indicators", sa.Column("ema_50", sa.Numeric(precision=10, scale=4), nullable=True))
    op.add_column("technical_indicators", sa.Column("ema_200", sa.Numeric(precision=10, scale=4), nullable=True))
    op.add_column("technical_indicators", sa.Column("adx_14", sa.Numeric(precision=10, scale=4), nullable=True))
    op.add_column("technical_indicators", sa.Column("plus_di_14", sa.Numeric(precision=10, scale=4), nullable=True))
    op.add_column("technical_indicators", sa.Column("minus_di_14", sa.Numeric(precision=10, scale=4), nullable=True))
    op.add_column(
        "technical_indicators", sa.Column("bb_bandwidth_20_2", sa.Numeric(precision=10, scale=4), nullable=True)
    )
    op.add_column(
        "technical_indicators", sa.Column("bb_percent_b_20_2", sa.Numeric(precision=10, scale=4), nullable=True)
    )
    op.add_column("technical_indicators", sa.Column("atr_percent_14", sa.Numeric(precision=10, scale=4), nullable=True))
    op.add_column("technical_indicators", sa.Column("rsi_slope_1", sa.Numeric(precision=10, scale=4), nullable=True))
    op.add_column(
        "technical_indicators",
        sa.Column("macd_histogram_slope_1", sa.Numeric(precision=10, scale=4), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("technical_indicators", "macd_histogram_slope_1")
    op.drop_column("technical_indicators", "rsi_slope_1")
    op.drop_column("technical_indicators", "atr_percent_14")
    op.drop_column("technical_indicators", "bb_percent_b_20_2")
    op.drop_column("technical_indicators", "bb_bandwidth_20_2")
    op.drop_column("technical_indicators", "minus_di_14")
    op.drop_column("technical_indicators", "plus_di_14")
    op.drop_column("technical_indicators", "adx_14")
    op.drop_column("technical_indicators", "ema_200")
    op.drop_column("technical_indicators", "ema_50")
    op.drop_column("technical_indicators", "ema_20")
