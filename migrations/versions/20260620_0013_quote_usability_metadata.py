"""add quote usability metadata

Revision ID: 20260620_0013
Revises: 20260619_0012
Create Date: 2026-06-20 14:45:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260620_0013"
down_revision: str | None = "20260619_0012"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("price_quotes") as batch_op:
        batch_op.add_column(
            sa.Column("provider_reported_at", sa.DateTime(timezone=True), nullable=True)
        )
        batch_op.add_column(
            sa.Column("indicative", sa.Boolean(), server_default=sa.true(), nullable=False)
        )
        batch_op.add_column(
            sa.Column(
                "endpoint_status",
                sa.String(length=32),
                server_default="unknown",
                nullable=False,
            )
        )
        batch_op.add_column(
            sa.Column(
                "market_session_status",
                sa.String(length=32),
                server_default="unknown",
                nullable=False,
            )
        )
        batch_op.add_column(
            sa.Column(
                "quote_usability",
                sa.String(length=32),
                server_default="indicative_only",
                nullable=False,
            )
        )
        batch_op.create_check_constraint(
            "ck_price_quotes_price_quote_fetched_gte_provider_reported",
            "provider_reported_at IS NULL OR fetched_at >= provider_reported_at",
        )
        batch_op.create_check_constraint(
            "ck_price_quotes_price_quote_endpoint_status_valid",
            "endpoint_status IN ('unknown', 'ok', 'degraded', 'failed')",
        )
        batch_op.create_check_constraint(
            "ck_price_quotes_price_quote_market_session_status_valid",
            "market_session_status IN ('unknown', 'open', 'closed', 'indicative_only')",
        )
        batch_op.create_check_constraint(
            "ck_price_quotes_price_quote_quote_usability_valid",
            "quote_usability IN "
            "('unknown', 'eligible', 'blocked', 'observation_only', 'indicative_only')",
        )
        batch_op.create_index("ix_price_quotes_usability", ["quote_usability"])

    if op.get_bind().dialect.name != "sqlite":
        op.alter_column("price_quotes", "indicative", server_default=None)
        op.alter_column("price_quotes", "endpoint_status", server_default=None)
        op.alter_column("price_quotes", "market_session_status", server_default=None)
        op.alter_column("price_quotes", "quote_usability", server_default=None)


def downgrade() -> None:
    with op.batch_alter_table("price_quotes") as batch_op:
        batch_op.drop_index("ix_price_quotes_usability")
        batch_op.drop_constraint(
            "ck_price_quotes_price_quote_quote_usability_valid",
            type_="check",
        )
        batch_op.drop_constraint(
            "ck_price_quotes_price_quote_market_session_status_valid",
            type_="check",
        )
        batch_op.drop_constraint(
            "ck_price_quotes_price_quote_endpoint_status_valid",
            type_="check",
        )
        batch_op.drop_constraint(
            "ck_price_quotes_price_quote_fetched_gte_provider_reported",
            type_="check",
        )
        batch_op.drop_column("quote_usability")
        batch_op.drop_column("market_session_status")
        batch_op.drop_column("endpoint_status")
        batch_op.drop_column("indicative")
        batch_op.drop_column("provider_reported_at")
