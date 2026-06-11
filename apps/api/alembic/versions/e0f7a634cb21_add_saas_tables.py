"""add saas tables

Revision ID: e0f7a634cb21
Revises: 0d9d9ef4c1a2
Create Date: 2026-06-12 00:00:00.000000
"""

from alembic import op
import sqlalchemy as sa

revision = "e0f7a634cb21"
down_revision = "0d9d9ef4c1a2"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 1. Create providers table
    op.create_table(
        "providers",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("name", sa.String(length=64), nullable=False),
        sa.Column("display_name", sa.String(length=128), nullable=False),
        sa.Column("is_active", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column("config_json", sa.JSON(), server_default=sa.text("'{}'"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_providers_name"), "providers", ["name"], unique=True)

    # 2. Create tenant_portfolios table
    op.create_table(
        "tenant_portfolios",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("tenant_id", sa.String(length=64), nullable=False),
        sa.Column("portfolio_id", sa.Integer(), nullable=False),
        sa.Column("provider_id", sa.Integer(), nullable=False),
        sa.Column("is_active", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.ForeignKeyConstraint(
            ["portfolio_id"], ["portfolios.id"], ondelete="CASCADE", name="fk_tenant_portfolios_portfolio_id"
        ),
        sa.ForeignKeyConstraint(
            ["provider_id"], ["providers.id"], ondelete="CASCADE", name="fk_tenant_portfolios_provider_id"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_tenant_portfolios_tenant_id"), "tenant_portfolios", ["tenant_id"], unique=False)
    op.create_index(op.f("ix_tenant_portfolios_portfolio_id"), "tenant_portfolios", ["portfolio_id"], unique=False)
    op.create_index(op.f("ix_tenant_portfolios_provider_id"), "tenant_portfolios", ["provider_id"], unique=False)

    # 3. Create strategy_parameters table
    op.create_table(
        "strategy_parameters",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("tenant_id", sa.String(length=64), nullable=False),
        sa.Column("strategy_name", sa.String(length=128), nullable=False),
        sa.Column("parameter_key", sa.String(length=128), nullable=False),
        sa.Column("parameter_value", sa.Text(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "tenant_id", "strategy_name", "parameter_key", name="uq_strategy_parameters_tenant_strategy_key"
        ),
    )
    op.create_index(op.f("ix_strategy_parameters_tenant_id"), "strategy_parameters", ["tenant_id"], unique=False)
    op.create_index(
        op.f("ix_strategy_parameters_strategy_name"), "strategy_parameters", ["strategy_name"], unique=False
    )
    op.create_index(
        op.f("ix_strategy_parameters_parameter_key"), "strategy_parameters", ["parameter_key"], unique=False
    )

    # 4. Create asset_conversions table
    op.create_table(
        "asset_conversions",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("from_asset_id", sa.Integer(), nullable=False),
        sa.Column("to_asset_id", sa.Integer(), nullable=False),
        sa.Column("conversion_rate", sa.Numeric(precision=18, scale=6), nullable=False),
        sa.ForeignKeyConstraint(
            ["from_asset_id"], ["assets.id"], ondelete="CASCADE", name="fk_asset_conversions_from_asset_id"
        ),
        sa.ForeignKeyConstraint(
            ["to_asset_id"], ["assets.id"], ondelete="CASCADE", name="fk_asset_conversions_to_asset_id"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("from_asset_id", "to_asset_id", name="uq_asset_conversions_from_to"),
    )
    op.create_index(op.f("ix_asset_conversions_from_asset_id"), "asset_conversions", ["from_asset_id"], unique=False)
    op.create_index(op.f("ix_asset_conversions_to_asset_id"), "asset_conversions", ["to_asset_id"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_asset_conversions_to_asset_id"), table_name="asset_conversions")
    op.drop_index(op.f("ix_asset_conversions_from_asset_id"), table_name="asset_conversions")
    op.drop_table("asset_conversions")

    op.drop_index(op.f("ix_strategy_parameters_parameter_key"), table_name="strategy_parameters")
    op.drop_index(op.f("ix_strategy_parameters_strategy_name"), table_name="strategy_parameters")
    op.drop_index(op.f("ix_strategy_parameters_tenant_id"), table_name="strategy_parameters")
    op.drop_table("strategy_parameters")

    op.drop_index(op.f("ix_tenant_portfolios_provider_id"), table_name="tenant_portfolios")
    op.drop_index(op.f("ix_tenant_portfolios_portfolio_id"), table_name="tenant_portfolios")
    op.drop_index(op.f("ix_tenant_portfolios_tenant_id"), table_name="tenant_portfolios")
    op.drop_table("tenant_portfolios")

    op.drop_index(op.f("ix_providers_name"), table_name="providers")
    op.drop_table("providers")
