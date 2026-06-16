"""add trade intent decision run fk

Revision ID: a7c9e3d4b5f6
Revises: f2b7c9d1a4e3
Create Date: 2026-06-16 00:00:00.000000
"""

from alembic import op
import sqlalchemy as sa


revision = "a7c9e3d4b5f6"
down_revision = "f2b7c9d1a4e3"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("trade_intents") as batch_op:
        batch_op.add_column(sa.Column("trading_decision_run_id", sa.Integer(), nullable=True))
        batch_op.create_index(
            batch_op.f("ix_trade_intents_trading_decision_run_id"),
            ["trading_decision_run_id"],
            unique=False,
        )
        batch_op.create_foreign_key(
            "fk_trade_intents_trading_decision_run_id_trading_decision_runs",
            "trading_decision_runs",
            ["trading_decision_run_id"],
            ["id"],
        )


def downgrade() -> None:
    with op.batch_alter_table("trade_intents") as batch_op:
        batch_op.drop_constraint(
            "fk_trade_intents_trading_decision_run_id_trading_decision_runs",
            type_="foreignkey",
        )
        batch_op.drop_index(batch_op.f("ix_trade_intents_trading_decision_run_id"))
        batch_op.drop_column("trading_decision_run_id")
