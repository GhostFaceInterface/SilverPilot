"""Add technical_indicators table.

Revision ID: 0004_add_technical_indicators_table
Revises: 0003_add_collector_audit_fields
Create Date: 2026-05-21
"""
from alembic import op
import sqlalchemy as sa


revision = "0004_add_technical_indicators_table"
down_revision = "0003_add_collector_audit_fields"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "technical_indicators",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("price_snapshot_id", sa.Integer(), nullable=True),
        sa.Column("bar_timestamp", sa.DateTime(timezone=True), nullable=False),
        sa.Column("timeframe", sa.String(length=8), nullable=False),
        sa.Column("close_usd_oz", sa.Numeric(precision=18, scale=6), nullable=True),
        sa.Column("rsi_14", sa.Numeric(precision=10, scale=4), nullable=True),
        sa.Column("macd_line", sa.Numeric(precision=10, scale=4), nullable=True),
        sa.Column("macd_signal", sa.Numeric(precision=10, scale=4), nullable=True),
        sa.Column("macd_histogram", sa.Numeric(precision=10, scale=4), nullable=True),
        sa.Column("bb_upper_20_2", sa.Numeric(precision=10, scale=4), nullable=True),
        sa.Column("bb_middle_20_2", sa.Numeric(precision=10, scale=4), nullable=True),
        sa.Column("bb_lower_20_2", sa.Numeric(precision=10, scale=4), nullable=True),
        sa.Column("sma_20", sa.Numeric(precision=10, scale=4), nullable=True),
        sa.Column("sma_50", sa.Numeric(precision=10, scale=4), nullable=True),
        sa.Column("sma_200", sa.Numeric(precision=10, scale=4), nullable=True),
        sa.Column("atr_14", sa.Numeric(precision=10, scale=4), nullable=True),
        sa.Column("xau_xag_ratio", sa.Numeric(precision=10, scale=4), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["price_snapshot_id"], ["price_snapshots.id"], name="fk_technical_indicators_price_snapshot_id"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("bar_timestamp", "timeframe", name="uq_technical_indicators_timestamp_timeframe"),
    )
    op.create_index("ix_technical_indicators_bar_timestamp", "technical_indicators", ["bar_timestamp"], unique=False)
    op.create_index("ix_technical_indicators_timeframe", "technical_indicators", ["timeframe"], unique=False)
    op.create_index("ix_technical_indicators_price_snapshot_id", "technical_indicators", ["price_snapshot_id"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_technical_indicators_price_snapshot_id", table_name="technical_indicators")
    op.drop_index("ix_technical_indicators_timeframe", table_name="technical_indicators")
    op.drop_index("ix_technical_indicators_bar_timestamp", table_name="technical_indicators")
    op.drop_table("technical_indicators")
