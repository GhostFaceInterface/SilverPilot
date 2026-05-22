"""Initial backend core schema.

Revision ID: 0001_initial_schema
Revises:
Create Date: 2026-05-13
"""

from alembic import op
import sqlalchemy as sa


revision = "0001_initial_schema"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "assets",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("symbol", sa.String(length=32), nullable=False),
        sa.Column("name", sa.String(length=128), nullable=False),
        sa.Column("asset_type", sa.String(length=32), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("symbol"),
    )
    op.create_index(op.f("ix_assets_symbol"), "assets", ["symbol"], unique=False)

    op.create_table(
        "portfolios",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=128), nullable=False),
        sa.Column("base_currency", sa.String(length=8), nullable=False),
        sa.Column("initial_cash", sa.Numeric(18, 6), nullable=False),
        sa.Column("cash_balance", sa.Numeric(18, 6), nullable=False),
        sa.Column("is_real_money", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("name"),
    )

    op.create_table(
        "risk_decisions",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("decision", sa.String(length=32), nullable=False),
        sa.Column("reason_code", sa.String(length=64), nullable=False),
        sa.Column("risk_level", sa.String(length=32), nullable=False),
        sa.Column("confidence", sa.Numeric(5, 4), nullable=False),
        sa.Column("details_json", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_risk_decisions_decision"), "risk_decisions", ["decision"], unique=False)
    op.create_index(op.f("ix_risk_decisions_reason_code"), "risk_decisions", ["reason_code"], unique=False)

    op.create_table(
        "risk_rules",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("code", sa.String(length=64), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("severity", sa.String(length=32), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("params_json", sa.JSON(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("code"),
    )
    op.create_index(op.f("ix_risk_rules_code"), "risk_rules", ["code"], unique=False)

    op.create_table(
        "agent_runs",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("agent_name", sa.String(length=128), nullable=False),
        sa.Column("model", sa.String(length=128), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("trace_id", sa.String(length=128), nullable=True),
        sa.Column("input_tokens", sa.Integer(), nullable=False),
        sa.Column("output_tokens", sa.Integer(), nullable=False),
        sa.Column("cost_estimate", sa.Numeric(12, 6), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_agent_runs_agent_name"), "agent_runs", ["agent_name"], unique=False)
    op.create_index(op.f("ix_agent_runs_status"), "agent_runs", ["status"], unique=False)
    op.create_index(op.f("ix_agent_runs_trace_id"), "agent_runs", ["trace_id"], unique=False)

    op.create_table(
        "price_snapshots",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("asset_id", sa.Integer(), nullable=False),
        sa.Column("source", sa.String(length=128), nullable=False),
        sa.Column("buy_price", sa.Numeric(18, 6), nullable=False),
        sa.Column("sell_price", sa.Numeric(18, 6), nullable=False),
        sa.Column("mid_price", sa.Numeric(18, 6), nullable=False),
        sa.Column("currency", sa.String(length=8), nullable=False),
        sa.Column("spread_absolute", sa.Numeric(18, 6), nullable=False),
        sa.Column("spread_percent", sa.Numeric(10, 6), nullable=False),
        sa.Column("observed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["asset_id"], ["assets.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_price_snapshots_asset_id"), "price_snapshots", ["asset_id"], unique=False)
    op.create_index(
        "ix_price_snapshots_asset_source_observed",
        "price_snapshots",
        ["asset_id", "source", "observed_at"],
        unique=False,
    )
    op.create_index(op.f("ix_price_snapshots_observed_at"), "price_snapshots", ["observed_at"], unique=False)
    op.create_index(op.f("ix_price_snapshots_source"), "price_snapshots", ["source"], unique=False)

    op.create_table(
        "portfolio_snapshots",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("portfolio_id", sa.Integer(), nullable=False),
        sa.Column("cash_balance", sa.Numeric(18, 6), nullable=False),
        sa.Column("asset_quantity", sa.Numeric(18, 6), nullable=False),
        sa.Column("portfolio_value", sa.Numeric(18, 6), nullable=False),
        sa.Column("realized_pnl", sa.Numeric(18, 6), nullable=False),
        sa.Column("unrealized_pnl", sa.Numeric(18, 6), nullable=False),
        sa.Column("observed_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["portfolio_id"], ["portfolios.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_portfolio_snapshots_observed_at"), "portfolio_snapshots", ["observed_at"], unique=False)
    op.create_index(op.f("ix_portfolio_snapshots_portfolio_id"), "portfolio_snapshots", ["portfolio_id"], unique=False)

    op.create_table(
        "paper_trades",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("portfolio_id", sa.Integer(), nullable=False),
        sa.Column("asset_id", sa.Integer(), nullable=False),
        sa.Column("action", sa.String(length=32), nullable=False),
        sa.Column("quantity", sa.Numeric(18, 6), nullable=False),
        sa.Column("price", sa.Numeric(18, 6), nullable=False),
        sa.Column("gross_amount", sa.Numeric(18, 6), nullable=False),
        sa.Column("fees", sa.Numeric(18, 6), nullable=False),
        sa.Column("taxes", sa.Numeric(18, 6), nullable=False),
        sa.Column("net_amount", sa.Numeric(18, 6), nullable=False),
        sa.Column("risk_decision_id", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["asset_id"], ["assets.id"]),
        sa.ForeignKeyConstraint(["portfolio_id"], ["portfolios.id"]),
        sa.ForeignKeyConstraint(["risk_decision_id"], ["risk_decisions.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_paper_trades_action"), "paper_trades", ["action"], unique=False)
    op.create_index(op.f("ix_paper_trades_asset_id"), "paper_trades", ["asset_id"], unique=False)
    op.create_index(op.f("ix_paper_trades_portfolio_id"), "paper_trades", ["portfolio_id"], unique=False)

    op.create_table(
        "signals",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("source", sa.String(length=128), nullable=False),
        sa.Column("asset_id", sa.Integer(), nullable=True),
        sa.Column("signal", sa.String(length=32), nullable=False),
        sa.Column("confidence", sa.Numeric(5, 4), nullable=False),
        sa.Column("risk_decision_id", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["asset_id"], ["assets.id"]),
        sa.ForeignKeyConstraint(["risk_decision_id"], ["risk_decisions.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_signals_asset_id"), "signals", ["asset_id"], unique=False)
    op.create_index(op.f("ix_signals_signal"), "signals", ["signal"], unique=False)
    op.create_index(op.f("ix_signals_source"), "signals", ["source"], unique=False)

    op.create_table(
        "reports",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("report_type", sa.String(length=64), nullable=False),
        sa.Column("period_start", sa.DateTime(timezone=True), nullable=False),
        sa.Column("period_end", sa.DateTime(timezone=True), nullable=False),
        sa.Column("payload_json", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_reports_report_type"), "reports", ["report_type"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_reports_report_type"), table_name="reports")
    op.drop_table("reports")
    op.drop_index(op.f("ix_signals_source"), table_name="signals")
    op.drop_index(op.f("ix_signals_signal"), table_name="signals")
    op.drop_index(op.f("ix_signals_asset_id"), table_name="signals")
    op.drop_table("signals")
    op.drop_index(op.f("ix_paper_trades_portfolio_id"), table_name="paper_trades")
    op.drop_index(op.f("ix_paper_trades_asset_id"), table_name="paper_trades")
    op.drop_index(op.f("ix_paper_trades_action"), table_name="paper_trades")
    op.drop_table("paper_trades")
    op.drop_index(op.f("ix_portfolio_snapshots_portfolio_id"), table_name="portfolio_snapshots")
    op.drop_index(op.f("ix_portfolio_snapshots_observed_at"), table_name="portfolio_snapshots")
    op.drop_table("portfolio_snapshots")
    op.drop_index(op.f("ix_price_snapshots_source"), table_name="price_snapshots")
    op.drop_index(op.f("ix_price_snapshots_observed_at"), table_name="price_snapshots")
    op.drop_index("ix_price_snapshots_asset_source_observed", table_name="price_snapshots")
    op.drop_index(op.f("ix_price_snapshots_asset_id"), table_name="price_snapshots")
    op.drop_table("price_snapshots")
    op.drop_index(op.f("ix_agent_runs_trace_id"), table_name="agent_runs")
    op.drop_index(op.f("ix_agent_runs_status"), table_name="agent_runs")
    op.drop_index(op.f("ix_agent_runs_agent_name"), table_name="agent_runs")
    op.drop_table("agent_runs")
    op.drop_index(op.f("ix_risk_rules_code"), table_name="risk_rules")
    op.drop_table("risk_rules")
    op.drop_index(op.f("ix_risk_decisions_reason_code"), table_name="risk_decisions")
    op.drop_index(op.f("ix_risk_decisions_decision"), table_name="risk_decisions")
    op.drop_table("risk_decisions")
    op.drop_table("portfolios")
    op.drop_index(op.f("ix_assets_symbol"), table_name="assets")
    op.drop_table("assets")
