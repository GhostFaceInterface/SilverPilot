"""add policy source profiles

Revision ID: f2b7c9d1a4e3
Revises: d4a1b9c7e8f2
Create Date: 2026-06-16 00:00:00.000000
"""

from alembic import op
import sqlalchemy as sa


revision = "f2b7c9d1a4e3"
down_revision = "d4a1b9c7e8f2"
branch_labels = None
depends_on = None


source_profiles = sa.table(
    "source_profiles",
    sa.column("source_key", sa.String),
    sa.column("role", sa.String),
    sa.column("priority", sa.Integer),
    sa.column("enabled", sa.Boolean),
    sa.column("stale_after_minutes", sa.Integer),
    sa.column("market_calendar", sa.String),
    sa.column("reliability_weight", sa.Numeric),
    sa.column("details_json", sa.JSON),
)

strategy_policies = sa.table(
    "strategy_policies",
    sa.column("strategy_name", sa.String),
    sa.column("execution_mode", sa.String),
    sa.column("timeframe_roles", sa.JSON),
    sa.column("freshness_policy", sa.JSON),
    sa.column("min_history", sa.JSON),
    sa.column("notification_policy", sa.JSON),
    sa.column("details_json", sa.JSON),
)


def upgrade() -> None:
    op.create_table(
        "source_profiles",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("source_key", sa.String(length=128), nullable=False),
        sa.Column("role", sa.String(length=64), nullable=False),
        sa.Column("priority", sa.Integer(), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False),
        sa.Column("stale_after_minutes", sa.Integer(), nullable=False),
        sa.Column("market_calendar", sa.String(length=64), nullable=True),
        sa.Column("reliability_weight", sa.Numeric(8, 4), nullable=False),
        sa.Column("details_json", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("source_key", name="uq_source_profiles_source_key"),
    )
    op.create_index(op.f("ix_source_profiles_created_at"), "source_profiles", ["created_at"], unique=False)
    op.create_index(op.f("ix_source_profiles_enabled"), "source_profiles", ["enabled"], unique=False)
    op.create_index(op.f("ix_source_profiles_priority"), "source_profiles", ["priority"], unique=False)
    op.create_index(op.f("ix_source_profiles_role"), "source_profiles", ["role"], unique=False)
    op.create_index(op.f("ix_source_profiles_source_key"), "source_profiles", ["source_key"], unique=False)
    op.create_index(op.f("ix_source_profiles_updated_at"), "source_profiles", ["updated_at"], unique=False)

    op.create_table(
        "strategy_policies",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("strategy_name", sa.String(length=128), nullable=False),
        sa.Column("execution_mode", sa.String(length=32), nullable=False),
        sa.Column("timeframe_roles", sa.JSON(), nullable=False),
        sa.Column("freshness_policy", sa.JSON(), nullable=False),
        sa.Column("min_history", sa.JSON(), nullable=False),
        sa.Column("notification_policy", sa.JSON(), nullable=False),
        sa.Column("details_json", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("strategy_name", name="uq_strategy_policies_strategy_name"),
    )
    op.create_index(op.f("ix_strategy_policies_created_at"), "strategy_policies", ["created_at"], unique=False)
    op.create_index(op.f("ix_strategy_policies_execution_mode"), "strategy_policies", ["execution_mode"], unique=False)
    op.create_index(op.f("ix_strategy_policies_strategy_name"), "strategy_policies", ["strategy_name"], unique=False)
    op.create_index(op.f("ix_strategy_policies_updated_at"), "strategy_policies", ["updated_at"], unique=False)

    op.bulk_insert(
        source_profiles,
        [
            {
                "source_key": "kuveyt-public-silver-page",
                "role": "execution_price",
                "priority": 10,
                "enabled": True,
                "stale_after_minutes": 60,
                "market_calendar": "bank_trading",
                "reliability_weight": 1.0,
                "details_json": {"collector_name": "kuveyt_public_silver", "asset_symbol": "XAG_GRAM"},
            },
            {
                "source_key": "global-xag-usd",
                "role": "trend_cross_check",
                "priority": 20,
                "enabled": True,
                "stale_after_minutes": 90,
                "market_calendar": "comex",
                "reliability_weight": 0.8,
                "details_json": {"sources": ["yahoo-si-f", "gold-api-xag-usd", "metals-dev-silver-spot"]},
            },
            {
                "source_key": "tcmb-today-xml",
                "role": "fx_conversion",
                "priority": 30,
                "enabled": True,
                "stale_after_minutes": 180,
                "market_calendar": "tcmb_business_day",
                "reliability_weight": 0.9,
                "details_json": {"pair": "USDTRY", "collector_name": "tcmb_usd_try"},
            },
            {
                "source_key": "rss-news-context",
                "role": "news_context",
                "priority": 100,
                "enabled": True,
                "stale_after_minutes": 360,
                "market_calendar": None,
                "reliability_weight": 0.5,
                "details_json": {"sources": ["fed-rss", "bloomberght-rss", "fxstreet-rss", "investing-rss"]},
            },
        ],
    )
    default_policy = {
        "execution_mode": "diagnostic",
        "timeframe_roles": {"trend": "1d", "entry": "1h", "execution": "5m"},
        "freshness_policy": {"1d": 138240, "1h": 180, "5m": 20},
        "min_history": {"default": 50},
        "notification_policy": {
            "trade": "always",
            "critical": "always",
            "block_change": "reason_change",
            "hourly_digest": "hourly",
        },
        "details_json": {"source_divergence_threshold_percent": 3.0, "policy_version": 1},
    }
    op.bulk_insert(
        strategy_policies,
        [
            {"strategy_name": "strategy_v2", **default_policy},
            {"strategy_name": "blended", **default_policy},
        ],
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_strategy_policies_updated_at"), table_name="strategy_policies")
    op.drop_index(op.f("ix_strategy_policies_strategy_name"), table_name="strategy_policies")
    op.drop_index(op.f("ix_strategy_policies_execution_mode"), table_name="strategy_policies")
    op.drop_index(op.f("ix_strategy_policies_created_at"), table_name="strategy_policies")
    op.drop_table("strategy_policies")

    op.drop_index(op.f("ix_source_profiles_updated_at"), table_name="source_profiles")
    op.drop_index(op.f("ix_source_profiles_source_key"), table_name="source_profiles")
    op.drop_index(op.f("ix_source_profiles_role"), table_name="source_profiles")
    op.drop_index(op.f("ix_source_profiles_priority"), table_name="source_profiles")
    op.drop_index(op.f("ix_source_profiles_enabled"), table_name="source_profiles")
    op.drop_index(op.f("ix_source_profiles_created_at"), table_name="source_profiles")
    op.drop_table("source_profiles")
