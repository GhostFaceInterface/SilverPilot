"""add market bars and audit provenance

Revision ID: 7f3c2a1d9b40
Revises: 9c7d4a6f2b10
Create Date: 2026-06-04 00:00:00.000000
"""

from alembic import op
import sqlalchemy as sa


revision = "7f3c2a1d9b40"
down_revision = "9c7d4a6f2b10"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("price_snapshots", sa.Column("collector_run_id", sa.Integer(), nullable=True))
    op.create_foreign_key(
        "fk_price_snapshots_collector_run_id",
        "price_snapshots",
        "collector_runs",
        ["collector_run_id"],
        ["id"],
    )
    op.create_index(op.f("ix_price_snapshots_collector_run_id"), "price_snapshots", ["collector_run_id"], unique=False)

    op.create_table(
        "market_bars",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("asset_id", sa.Integer(), nullable=False),
        sa.Column("source", sa.String(length=128), nullable=False),
        sa.Column("timeframe", sa.String(length=8), nullable=False),
        sa.Column("bar_start_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("bar_end_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("open", sa.Numeric(precision=18, scale=6), nullable=False),
        sa.Column("high", sa.Numeric(precision=18, scale=6), nullable=False),
        sa.Column("low", sa.Numeric(precision=18, scale=6), nullable=False),
        sa.Column("close", sa.Numeric(precision=18, scale=6), nullable=False),
        sa.Column("currency", sa.String(length=8), nullable=False),
        sa.Column("sample_count", sa.Integer(), nullable=False),
        sa.Column("first_price_snapshot_id", sa.Integer(), nullable=True),
        sa.Column("last_price_snapshot_id", sa.Integer(), nullable=True),
        sa.Column("quality_status", sa.String(length=32), nullable=False),
        sa.Column("bar_builder_version", sa.String(length=64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["asset_id"], ["assets.id"], name="fk_market_bars_asset_id"),
        sa.ForeignKeyConstraint(
            ["first_price_snapshot_id"], ["price_snapshots.id"], name="fk_market_bars_first_price_snapshot_id"
        ),
        sa.ForeignKeyConstraint(
            ["last_price_snapshot_id"], ["price_snapshots.id"], name="fk_market_bars_last_price_snapshot_id"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "asset_id", "source", "timeframe", "bar_start_at", name="uq_market_bars_asset_source_tf_start"
        ),
    )
    op.create_index(op.f("ix_market_bars_asset_id"), "market_bars", ["asset_id"], unique=False)
    op.create_index(op.f("ix_market_bars_source"), "market_bars", ["source"], unique=False)
    op.create_index(op.f("ix_market_bars_timeframe"), "market_bars", ["timeframe"], unique=False)
    op.create_index(op.f("ix_market_bars_bar_start_at"), "market_bars", ["bar_start_at"], unique=False)
    op.create_index(op.f("ix_market_bars_bar_end_at"), "market_bars", ["bar_end_at"], unique=False)
    op.create_index(op.f("ix_market_bars_quality_status"), "market_bars", ["quality_status"], unique=False)
    op.create_index(
        "ix_market_bars_asset_source_tf_start",
        "market_bars",
        ["asset_id", "source", "timeframe", "bar_start_at"],
        unique=False,
    )

    op.add_column("technical_indicators", sa.Column("market_bar_id", sa.Integer(), nullable=True))
    op.add_column(
        "technical_indicators",
        sa.Column(
            "calculation_version", sa.String(length=64), server_default="technical-indicators-v1", nullable=False
        ),
    )
    op.add_column(
        "technical_indicators", sa.Column("input_bar_count", sa.Integer(), server_default="0", nullable=False)
    )
    op.add_column(
        "technical_indicators", sa.Column("quality_status", sa.String(length=32), server_default="ok", nullable=False)
    )
    op.create_foreign_key(
        "fk_technical_indicators_market_bar_id",
        "technical_indicators",
        "market_bars",
        ["market_bar_id"],
        ["id"],
    )
    op.create_index(
        op.f("ix_technical_indicators_market_bar_id"), "technical_indicators", ["market_bar_id"], unique=False
    )
    op.create_index(
        op.f("ix_technical_indicators_calculation_version"),
        "technical_indicators",
        ["calculation_version"],
        unique=False,
    )
    op.create_index(
        op.f("ix_technical_indicators_quality_status"), "technical_indicators", ["quality_status"], unique=False
    )
    op.create_unique_constraint(
        "uq_technical_indicators_bar_calc_version",
        "technical_indicators",
        ["market_bar_id", "calculation_version"],
    )

    op.add_column("portfolio_snapshots", sa.Column("price_snapshot_id", sa.Integer(), nullable=True))
    op.create_foreign_key(
        "fk_portfolio_snapshots_price_snapshot_id",
        "portfolio_snapshots",
        "price_snapshots",
        ["price_snapshot_id"],
        ["id"],
    )
    op.create_index(
        op.f("ix_portfolio_snapshots_price_snapshot_id"),
        "portfolio_snapshots",
        ["price_snapshot_id"],
        unique=False,
    )

    op.alter_column("technical_indicators", "calculation_version", server_default=None)
    op.alter_column("technical_indicators", "input_bar_count", server_default=None)
    op.alter_column("technical_indicators", "quality_status", server_default=None)


def downgrade() -> None:
    op.drop_index(op.f("ix_portfolio_snapshots_price_snapshot_id"), table_name="portfolio_snapshots")
    op.drop_constraint("fk_portfolio_snapshots_price_snapshot_id", "portfolio_snapshots", type_="foreignkey")
    op.drop_column("portfolio_snapshots", "price_snapshot_id")

    op.drop_constraint("uq_technical_indicators_bar_calc_version", "technical_indicators", type_="unique")
    op.drop_index(op.f("ix_technical_indicators_quality_status"), table_name="technical_indicators")
    op.drop_index(op.f("ix_technical_indicators_calculation_version"), table_name="technical_indicators")
    op.drop_index(op.f("ix_technical_indicators_market_bar_id"), table_name="technical_indicators")
    op.drop_constraint("fk_technical_indicators_market_bar_id", "technical_indicators", type_="foreignkey")
    op.drop_column("technical_indicators", "quality_status")
    op.drop_column("technical_indicators", "input_bar_count")
    op.drop_column("technical_indicators", "calculation_version")
    op.drop_column("technical_indicators", "market_bar_id")

    op.drop_index("ix_market_bars_asset_source_tf_start", table_name="market_bars")
    op.drop_index(op.f("ix_market_bars_quality_status"), table_name="market_bars")
    op.drop_index(op.f("ix_market_bars_bar_end_at"), table_name="market_bars")
    op.drop_index(op.f("ix_market_bars_bar_start_at"), table_name="market_bars")
    op.drop_index(op.f("ix_market_bars_timeframe"), table_name="market_bars")
    op.drop_index(op.f("ix_market_bars_source"), table_name="market_bars")
    op.drop_index(op.f("ix_market_bars_asset_id"), table_name="market_bars")
    op.drop_table("market_bars")

    op.drop_index(op.f("ix_price_snapshots_collector_run_id"), table_name="price_snapshots")
    op.drop_constraint("fk_price_snapshots_collector_run_id", "price_snapshots", type_="foreignkey")
    op.drop_column("price_snapshots", "collector_run_id")
