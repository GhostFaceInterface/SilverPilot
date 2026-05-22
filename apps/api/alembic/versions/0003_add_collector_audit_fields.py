"""Add collector audit fields.

Revision ID: 0003_add_collector_audit_fields
Revises: 0002_collector_foundation
Create Date: 2026-05-13
"""

from alembic import op
import sqlalchemy as sa


revision = "0003_add_collector_audit_fields"
down_revision = "0002_collector_foundation"
branch_labels = None
depends_on = None


RAW_TABLES = ("raw_bank_prices", "raw_global_prices", "raw_fx_rates", "raw_news", "raw_events")


def upgrade() -> None:
    for table_name in RAW_TABLES:
        op.add_column(
            table_name,
            sa.Column("fetched_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        )
        op.add_column(
            table_name,
            sa.Column("raw_payload_hash", sa.String(length=64), server_default="", nullable=False),
        )
        op.add_column(
            table_name,
            sa.Column("parser_version", sa.String(length=64), server_default="unknown", nullable=False),
        )
        op.create_index(op.f(f"ix_{table_name}_fetched_at"), table_name, ["fetched_at"], unique=False)
        op.create_index(op.f(f"ix_{table_name}_raw_payload_hash"), table_name, ["raw_payload_hash"], unique=False)

    for table_name in RAW_TABLES:
        op.alter_column(table_name, "raw_payload_hash", server_default=None)
        op.alter_column(table_name, "parser_version", server_default=None)


def downgrade() -> None:
    for table_name in reversed(RAW_TABLES):
        op.drop_index(op.f(f"ix_{table_name}_raw_payload_hash"), table_name=table_name)
        op.drop_index(op.f(f"ix_{table_name}_fetched_at"), table_name=table_name)
        op.drop_column(table_name, "parser_version")
        op.drop_column(table_name, "raw_payload_hash")
        op.drop_column(table_name, "fetched_at")
