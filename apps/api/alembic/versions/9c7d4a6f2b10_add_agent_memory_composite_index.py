"""add_agent_memory_composite_index

Revision ID: 9c7d4a6f2b10
Revises: b2813bc6e7b0
Create Date: 2026-06-04 00:00:00.000000
"""

from alembic import op


revision = "9c7d4a6f2b10"
down_revision = "b2813bc6e7b0"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_index(
        op.f("ix_agent_memory_events_composite"),
        "agent_memory_events",
        ["agent_name", "event_type", "key", "created_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_agent_memory_events_composite"), table_name="agent_memory_events")
