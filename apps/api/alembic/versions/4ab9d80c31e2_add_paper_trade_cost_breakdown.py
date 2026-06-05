"""add paper trade cost breakdown

Revision ID: 4ab9d80c31e2
Revises: 7f3c2a1d9b40
Create Date: 2026-06-04 00:00:00.000000
"""

from alembic import op
import sqlalchemy as sa


revision = "4ab9d80c31e2"
down_revision = "7f3c2a1d9b40"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    json_default = sa.text("'{}'::json") if bind.dialect.name == "postgresql" else sa.text("'{}'")
    op.add_column(
        "paper_trades",
        sa.Column("spread_impact", sa.Numeric(precision=18, scale=6), server_default="0", nullable=False),
    )
    op.add_column(
        "paper_trades",
        sa.Column("cost_breakdown_json", sa.JSON(), server_default=json_default, nullable=False),
    )
    op.alter_column("paper_trades", "spread_impact", server_default=None)
    op.alter_column("paper_trades", "cost_breakdown_json", server_default=None)


def downgrade() -> None:
    op.drop_column("paper_trades", "cost_breakdown_json")
    op.drop_column("paper_trades", "spread_impact")
