"""Add collector foundation tables.

Revision ID: 0002_collector_foundation
Revises: 0001_initial_schema
Create Date: 2026-05-13
"""
from alembic import op
import sqlalchemy as sa


revision = "0002_collector_foundation"
down_revision = "0001_initial_schema"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "collector_runs",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("collector_name", sa.String(length=128), nullable=False),
        sa.Column("source", sa.String(length=128), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("records_seen", sa.Integer(), nullable=False),
        sa.Column("records_inserted", sa.Integer(), nullable=False),
        sa.Column("duplicates", sa.Integer(), nullable=False),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("details_json", sa.JSON(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_collector_runs_collector_name"), "collector_runs", ["collector_name"], unique=False)
    op.create_index(op.f("ix_collector_runs_source"), "collector_runs", ["source"], unique=False)
    op.create_index(op.f("ix_collector_runs_started_at"), "collector_runs", ["started_at"], unique=False)
    op.create_index(op.f("ix_collector_runs_status"), "collector_runs", ["status"], unique=False)

    op.create_table(
        "raw_bank_prices",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("collector_run_id", sa.Integer(), nullable=False),
        sa.Column("asset_id", sa.Integer(), nullable=False),
        sa.Column("source", sa.String(length=128), nullable=False),
        sa.Column("buy_price", sa.Numeric(18, 6), nullable=False),
        sa.Column("sell_price", sa.Numeric(18, 6), nullable=False),
        sa.Column("currency", sa.String(length=8), nullable=False),
        sa.Column("observed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("payload_json", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["asset_id"], ["assets.id"]),
        sa.ForeignKeyConstraint(["collector_run_id"], ["collector_runs.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("asset_id", "source", "observed_at", name="uq_raw_bank_prices_asset_source_observed"),
    )
    op.create_index(op.f("ix_raw_bank_prices_asset_id"), "raw_bank_prices", ["asset_id"], unique=False)
    op.create_index(op.f("ix_raw_bank_prices_collector_run_id"), "raw_bank_prices", ["collector_run_id"], unique=False)
    op.create_index(op.f("ix_raw_bank_prices_observed_at"), "raw_bank_prices", ["observed_at"], unique=False)
    op.create_index(op.f("ix_raw_bank_prices_source"), "raw_bank_prices", ["source"], unique=False)

    op.create_table(
        "raw_global_prices",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("collector_run_id", sa.Integer(), nullable=False),
        sa.Column("asset_id", sa.Integer(), nullable=False),
        sa.Column("source", sa.String(length=128), nullable=False),
        sa.Column("buy_price", sa.Numeric(18, 6), nullable=False),
        sa.Column("sell_price", sa.Numeric(18, 6), nullable=False),
        sa.Column("currency", sa.String(length=8), nullable=False),
        sa.Column("observed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("payload_json", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["asset_id"], ["assets.id"]),
        sa.ForeignKeyConstraint(["collector_run_id"], ["collector_runs.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("asset_id", "source", "observed_at", name="uq_raw_global_prices_asset_source_observed"),
    )
    op.create_index(op.f("ix_raw_global_prices_asset_id"), "raw_global_prices", ["asset_id"], unique=False)
    op.create_index(op.f("ix_raw_global_prices_collector_run_id"), "raw_global_prices", ["collector_run_id"], unique=False)
    op.create_index(op.f("ix_raw_global_prices_observed_at"), "raw_global_prices", ["observed_at"], unique=False)
    op.create_index(op.f("ix_raw_global_prices_source"), "raw_global_prices", ["source"], unique=False)

    op.create_table(
        "raw_fx_rates",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("collector_run_id", sa.Integer(), nullable=False),
        sa.Column("source", sa.String(length=128), nullable=False),
        sa.Column("base_currency", sa.String(length=8), nullable=False),
        sa.Column("quote_currency", sa.String(length=8), nullable=False),
        sa.Column("rate", sa.Numeric(18, 6), nullable=False),
        sa.Column("observed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("payload_json", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["collector_run_id"], ["collector_runs.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("source", "base_currency", "quote_currency", "observed_at", name="uq_raw_fx_source_pair_observed"),
    )
    op.create_index(op.f("ix_raw_fx_rates_collector_run_id"), "raw_fx_rates", ["collector_run_id"], unique=False)
    op.create_index(op.f("ix_raw_fx_rates_observed_at"), "raw_fx_rates", ["observed_at"], unique=False)
    op.create_index(op.f("ix_raw_fx_rates_source"), "raw_fx_rates", ["source"], unique=False)

    op.create_table(
        "raw_news",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("collector_run_id", sa.Integer(), nullable=False),
        sa.Column("source", sa.String(length=128), nullable=False),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("url", sa.Text(), nullable=False),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("payload_json", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["collector_run_id"], ["collector_runs.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("source", "url", name="uq_raw_news_source_url"),
    )
    op.create_index(op.f("ix_raw_news_collector_run_id"), "raw_news", ["collector_run_id"], unique=False)
    op.create_index(op.f("ix_raw_news_published_at"), "raw_news", ["published_at"], unique=False)
    op.create_index(op.f("ix_raw_news_source"), "raw_news", ["source"], unique=False)

    op.create_table(
        "raw_events",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("collector_run_id", sa.Integer(), nullable=True),
        sa.Column("source", sa.String(length=128), nullable=False),
        sa.Column("event_type", sa.String(length=64), nullable=False),
        sa.Column("payload_json", sa.JSON(), nullable=False),
        sa.Column("observed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["collector_run_id"], ["collector_runs.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_raw_events_collector_run_id"), "raw_events", ["collector_run_id"], unique=False)
    op.create_index(op.f("ix_raw_events_event_type"), "raw_events", ["event_type"], unique=False)
    op.create_index(op.f("ix_raw_events_observed_at"), "raw_events", ["observed_at"], unique=False)
    op.create_index(op.f("ix_raw_events_source"), "raw_events", ["source"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_raw_events_source"), table_name="raw_events")
    op.drop_index(op.f("ix_raw_events_observed_at"), table_name="raw_events")
    op.drop_index(op.f("ix_raw_events_event_type"), table_name="raw_events")
    op.drop_index(op.f("ix_raw_events_collector_run_id"), table_name="raw_events")
    op.drop_table("raw_events")
    op.drop_index(op.f("ix_raw_news_source"), table_name="raw_news")
    op.drop_index(op.f("ix_raw_news_published_at"), table_name="raw_news")
    op.drop_index(op.f("ix_raw_news_collector_run_id"), table_name="raw_news")
    op.drop_table("raw_news")
    op.drop_index(op.f("ix_raw_fx_rates_source"), table_name="raw_fx_rates")
    op.drop_index(op.f("ix_raw_fx_rates_observed_at"), table_name="raw_fx_rates")
    op.drop_index(op.f("ix_raw_fx_rates_collector_run_id"), table_name="raw_fx_rates")
    op.drop_table("raw_fx_rates")
    op.drop_index(op.f("ix_raw_global_prices_source"), table_name="raw_global_prices")
    op.drop_index(op.f("ix_raw_global_prices_observed_at"), table_name="raw_global_prices")
    op.drop_index(op.f("ix_raw_global_prices_collector_run_id"), table_name="raw_global_prices")
    op.drop_index(op.f("ix_raw_global_prices_asset_id"), table_name="raw_global_prices")
    op.drop_table("raw_global_prices")
    op.drop_index(op.f("ix_raw_bank_prices_source"), table_name="raw_bank_prices")
    op.drop_index(op.f("ix_raw_bank_prices_observed_at"), table_name="raw_bank_prices")
    op.drop_index(op.f("ix_raw_bank_prices_collector_run_id"), table_name="raw_bank_prices")
    op.drop_index(op.f("ix_raw_bank_prices_asset_id"), table_name="raw_bank_prices")
    op.drop_table("raw_bank_prices")
    op.drop_index(op.f("ix_collector_runs_status"), table_name="collector_runs")
    op.drop_index(op.f("ix_collector_runs_started_at"), table_name="collector_runs")
    op.drop_index(op.f("ix_collector_runs_source"), table_name="collector_runs")
    op.drop_index(op.f("ix_collector_runs_collector_name"), table_name="collector_runs")
    op.drop_table("collector_runs")
