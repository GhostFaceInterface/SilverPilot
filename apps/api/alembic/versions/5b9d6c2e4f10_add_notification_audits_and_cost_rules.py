"""add notification audits and provider cost rules

Revision ID: 5b9d6c2e4f10
Revises: e0f7a634cb21
Create Date: 2026-06-12 00:00:00.000000
"""

from alembic import op
import sqlalchemy as sa


revision = "5b9d6c2e4f10"
down_revision = "e0f7a634cb21"
branch_labels = None
depends_on = None


def _json_default() -> sa.TextClause:
    bind = op.get_bind()
    return sa.text("'{}'::json") if bind.dialect.name == "postgresql" else sa.text("'{}'")


def upgrade() -> None:
    json_default = _json_default()
    op.create_table(
        "notification_audits",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("signal_id", sa.Integer(), nullable=True),
        sa.Column("asset_symbol", sa.String(length=32), nullable=False),
        sa.Column("strategy_name", sa.String(length=128), nullable=False),
        sa.Column("notification_action", sa.String(length=32), nullable=False),
        sa.Column("reason_code", sa.String(length=64), nullable=False),
        sa.Column("sent", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("skipped_reason", sa.String(length=64), nullable=True),
        sa.Column("cooldown_seconds", sa.Integer(), server_default="0", nullable=False),
        sa.Column("observed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("details_json", sa.JSON(), server_default=json_default, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["signal_id"], ["signals.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_notification_audits_signal_id"), "notification_audits", ["signal_id"], unique=False)
    op.create_index(op.f("ix_notification_audits_asset_symbol"), "notification_audits", ["asset_symbol"], unique=False)
    op.create_index(
        op.f("ix_notification_audits_strategy_name"), "notification_audits", ["strategy_name"], unique=False
    )
    op.create_index(
        op.f("ix_notification_audits_notification_action"),
        "notification_audits",
        ["notification_action"],
        unique=False,
    )
    op.create_index(op.f("ix_notification_audits_reason_code"), "notification_audits", ["reason_code"], unique=False)
    op.create_index(op.f("ix_notification_audits_sent"), "notification_audits", ["sent"], unique=False)
    op.create_index(op.f("ix_notification_audits_observed_at"), "notification_audits", ["observed_at"], unique=False)
    op.create_index(op.f("ix_notification_audits_created_at"), "notification_audits", ["created_at"], unique=False)
    op.create_index(
        "ix_notification_audits_dedupe",
        "notification_audits",
        ["asset_symbol", "strategy_name", "notification_action", "reason_code", "observed_at"],
        unique=False,
    )

    op.create_table(
        "provider_cost_rules",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("provider_id", sa.Integer(), nullable=False),
        sa.Column("asset_id", sa.Integer(), nullable=True),
        sa.Column("asset_type", sa.String(length=32), nullable=True),
        sa.Column("action", sa.String(length=32), server_default="*", nullable=False),
        sa.Column("fee_rate", sa.Numeric(precision=10, scale=6), server_default="0", nullable=False),
        sa.Column("tax_rate", sa.Numeric(precision=10, scale=6), server_default="0", nullable=False),
        sa.Column("fixed_fee", sa.Numeric(precision=18, scale=6), server_default="0", nullable=False),
        sa.Column("is_active", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column("effective_from", sa.DateTime(timezone=True), nullable=True),
        sa.Column("effective_to", sa.DateTime(timezone=True), nullable=True),
        sa.Column("details_json", sa.JSON(), server_default=json_default, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["asset_id"], ["assets.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["provider_id"], ["providers.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "provider_id",
            "asset_id",
            "asset_type",
            "action",
            "effective_from",
            name="uq_provider_cost_rules_provider_asset_action_effective",
        ),
    )
    op.create_index(op.f("ix_provider_cost_rules_provider_id"), "provider_cost_rules", ["provider_id"], unique=False)
    op.create_index(op.f("ix_provider_cost_rules_asset_id"), "provider_cost_rules", ["asset_id"], unique=False)
    op.create_index(op.f("ix_provider_cost_rules_asset_type"), "provider_cost_rules", ["asset_type"], unique=False)
    op.create_index(op.f("ix_provider_cost_rules_action"), "provider_cost_rules", ["action"], unique=False)
    op.create_index(op.f("ix_provider_cost_rules_is_active"), "provider_cost_rules", ["is_active"], unique=False)
    op.create_index(
        op.f("ix_provider_cost_rules_effective_from"), "provider_cost_rules", ["effective_from"], unique=False
    )
    op.create_index(op.f("ix_provider_cost_rules_effective_to"), "provider_cost_rules", ["effective_to"], unique=False)
    op.create_index(op.f("ix_provider_cost_rules_created_at"), "provider_cost_rules", ["created_at"], unique=False)
    op.create_index(
        "ix_provider_cost_rules_lookup",
        "provider_cost_rules",
        ["provider_id", "asset_id", "asset_type", "action", "is_active"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_provider_cost_rules_lookup", table_name="provider_cost_rules")
    op.drop_index(op.f("ix_provider_cost_rules_created_at"), table_name="provider_cost_rules")
    op.drop_index(op.f("ix_provider_cost_rules_effective_to"), table_name="provider_cost_rules")
    op.drop_index(op.f("ix_provider_cost_rules_effective_from"), table_name="provider_cost_rules")
    op.drop_index(op.f("ix_provider_cost_rules_is_active"), table_name="provider_cost_rules")
    op.drop_index(op.f("ix_provider_cost_rules_action"), table_name="provider_cost_rules")
    op.drop_index(op.f("ix_provider_cost_rules_asset_type"), table_name="provider_cost_rules")
    op.drop_index(op.f("ix_provider_cost_rules_asset_id"), table_name="provider_cost_rules")
    op.drop_index(op.f("ix_provider_cost_rules_provider_id"), table_name="provider_cost_rules")
    op.drop_table("provider_cost_rules")

    op.drop_index("ix_notification_audits_dedupe", table_name="notification_audits")
    op.drop_index(op.f("ix_notification_audits_created_at"), table_name="notification_audits")
    op.drop_index(op.f("ix_notification_audits_observed_at"), table_name="notification_audits")
    op.drop_index(op.f("ix_notification_audits_sent"), table_name="notification_audits")
    op.drop_index(op.f("ix_notification_audits_reason_code"), table_name="notification_audits")
    op.drop_index(op.f("ix_notification_audits_notification_action"), table_name="notification_audits")
    op.drop_index(op.f("ix_notification_audits_strategy_name"), table_name="notification_audits")
    op.drop_index(op.f("ix_notification_audits_asset_symbol"), table_name="notification_audits")
    op.drop_index(op.f("ix_notification_audits_signal_id"), table_name="notification_audits")
    op.drop_table("notification_audits")
