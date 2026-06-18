"""add risk decisions

Revision ID: 20260618_0005
Revises: 20260618_0004
Create Date: 2026-06-18 14:00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260618_0005"
down_revision: str | None = "20260618_0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _uuid_type() -> sa.Uuid:
    return sa.Uuid(as_uuid=True)


def _timestamp_column(name: str) -> sa.Column[sa.DateTime]:
    return sa.Column(name, sa.DateTime(timezone=True), nullable=False)


def _audit_columns() -> list[sa.Column[sa.DateTime]]:
    return [
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
    ]


def upgrade() -> None:
    op.create_table(
        "risk_decisions",
        sa.Column("id", _uuid_type(), nullable=False),
        sa.Column("trade_intent_id", _uuid_type(), nullable=False),
        sa.Column("quote_id", _uuid_type(), nullable=True),
        sa.Column("decision", sa.String(length=16), nullable=False),
        sa.Column("requested_cash_amount", sa.Numeric(precision=24, scale=8), nullable=False),
        sa.Column("approved_cash_amount", sa.Numeric(precision=24, scale=8), nullable=True),
        sa.Column("approved_quantity", sa.Numeric(precision=24, scale=8), nullable=True),
        sa.Column("policy_version", sa.String(length=80), nullable=False),
        sa.Column("reasons", sa.JSON(), nullable=False),
        sa.Column("constraints_applied", sa.JSON(), nullable=False),
        _timestamp_column("evaluated_at"),
        *_audit_columns(),
        sa.CheckConstraint(
            "decision IN ('approve', 'reduce', 'reject')",
            name=op.f("ck_risk_decisions_risk_decision_valid"),
        ),
        sa.CheckConstraint(
            "requested_cash_amount > 0",
            name=op.f("ck_risk_decisions_risk_requested_cash_amount_positive"),
        ),
        sa.CheckConstraint(
            "approved_cash_amount IS NULL OR approved_cash_amount >= 0",
            name=op.f("ck_risk_decisions_risk_approved_cash_amount_non_negative"),
        ),
        sa.CheckConstraint(
            "approved_quantity IS NULL OR approved_quantity >= 0",
            name=op.f("ck_risk_decisions_risk_approved_quantity_non_negative"),
        ),
        sa.CheckConstraint(
            "approved_cash_amount IS NULL OR approved_cash_amount <= requested_cash_amount",
            name=op.f("ck_risk_decisions_risk_approved_cash_amount_lte_requested"),
        ),
        sa.ForeignKeyConstraint(
            ["quote_id"],
            ["price_quotes.id"],
            name=op.f("fk_risk_decisions_quote_id_price_quotes"),
        ),
        sa.ForeignKeyConstraint(
            ["trade_intent_id"],
            ["trade_intents.id"],
            name=op.f("fk_risk_decisions_trade_intent_id_trade_intents"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_risk_decisions")),
        sa.UniqueConstraint(
            "trade_intent_id",
            "policy_version",
            name=op.f("uq_risk_decisions_trade_intent_id"),
        ),
    )
    op.create_index("ix_risk_decisions_intent", "risk_decisions", ["trade_intent_id"])
    op.create_index("ix_risk_decisions_decision", "risk_decisions", ["decision"])
    op.create_index("ix_risk_decisions_created_at", "risk_decisions", ["created_at"])


def downgrade() -> None:
    op.drop_index("ix_risk_decisions_created_at", table_name="risk_decisions")
    op.drop_index("ix_risk_decisions_decision", table_name="risk_decisions")
    op.drop_index("ix_risk_decisions_intent", table_name="risk_decisions")
    op.drop_table("risk_decisions")
