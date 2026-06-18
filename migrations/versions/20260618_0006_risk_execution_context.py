"""add execution instrument to risk decisions

Revision ID: 20260618_0006
Revises: 20260618_0005
Create Date: 2026-06-18 16:00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260618_0006"
down_revision: str | None = "20260618_0005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _uuid_type() -> sa.Uuid:
    return sa.Uuid(as_uuid=True)


def upgrade() -> None:
    with op.batch_alter_table("risk_decisions") as batch_op:
        batch_op.add_column(
            sa.Column("execution_instrument_id", _uuid_type(), nullable=True),
        )
        batch_op.create_foreign_key(
            op.f("fk_risk_decisions_execution_instrument_id_execution_instruments"),
            "execution_instruments",
            ["execution_instrument_id"],
            ["id"],
        )
    op.create_index(
        "ix_risk_decisions_execution_instrument",
        "risk_decisions",
        ["execution_instrument_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_risk_decisions_execution_instrument", table_name="risk_decisions")
    with op.batch_alter_table("risk_decisions") as batch_op:
        batch_op.drop_constraint(
            op.f("fk_risk_decisions_execution_instrument_id_execution_instruments"),
            type_="foreignkey",
        )
        batch_op.drop_column("execution_instrument_id")
