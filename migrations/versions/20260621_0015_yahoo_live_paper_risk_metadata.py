"""add yahoo live-paper risk metadata

Revision ID: 20260621_0015
Revises: 20260621_0014
Create Date: 2026-06-21 16:00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260621_0015"
down_revision: str | None = "20260621_0014"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("reference_market_instruments") as batch_op:
        batch_op.add_column(sa.Column("source_delay_status", sa.String(length=32), nullable=True))
        batch_op.add_column(sa.Column("source_risk_status", sa.String(length=64), nullable=True))
        batch_op.add_column(sa.Column("approved_by", sa.String(length=120), nullable=True))
        batch_op.add_column(sa.Column("approved_at", sa.DateTime(timezone=True), nullable=True))
        batch_op.add_column(sa.Column("approved_scope", sa.String(length=80), nullable=True))
        batch_op.add_column(sa.Column("approved_symbols", sa.String(length=255), nullable=True))
        batch_op.add_column(sa.Column("approved_timeframe", sa.String(length=20), nullable=True))
        batch_op.add_column(
            sa.Column(
                "real_money_allowed",
                sa.Boolean(),
                server_default=sa.false(),
                nullable=False,
            )
        )
        batch_op.create_check_constraint(
            "ck_reference_market_instruments_reference_market_source_delay_status_valid",
            "source_delay_status IS NULL OR source_delay_status IN "
            "('unknown', 'verified', 'assumed_conservative', 'not_applicable')",
        )
        batch_op.create_check_constraint(
            "ck_reference_market_instruments_reference_market_source_risk_status_valid",
            "source_risk_status IS NULL OR source_risk_status IN "
            "('unknown', 'owner_accepted_paper_use_risk', 'not_approved')",
        )
        batch_op.create_check_constraint(
            "ck_reference_market_instruments_reference_market_approved_scope_valid",
            "approved_scope IS NULL OR approved_scope IN ('live-paper only')",
        )

    if op.get_bind().dialect.name != "sqlite":
        op.alter_column("reference_market_instruments", "real_money_allowed", server_default=None)


def downgrade() -> None:
    with op.batch_alter_table("reference_market_instruments") as batch_op:
        batch_op.drop_constraint(
            "ck_reference_market_instruments_reference_market_approved_scope_valid",
            type_="check",
        )
        batch_op.drop_constraint(
            "ck_reference_market_instruments_reference_market_source_risk_status_valid",
            type_="check",
        )
        batch_op.drop_constraint(
            "ck_reference_market_instruments_reference_market_source_delay_status_valid",
            type_="check",
        )
        batch_op.drop_column("real_money_allowed")
        batch_op.drop_column("approved_timeframe")
        batch_op.drop_column("approved_symbols")
        batch_op.drop_column("approved_scope")
        batch_op.drop_column("approved_at")
        batch_op.drop_column("approved_by")
        batch_op.drop_column("source_risk_status")
        batch_op.drop_column("source_delay_status")
