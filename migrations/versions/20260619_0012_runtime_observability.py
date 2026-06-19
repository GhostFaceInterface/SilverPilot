"""add runtime observability and sell-capable trade intents

Revision ID: 20260619_0012
Revises: 20260619_0011
Create Date: 2026-06-19 18:00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260619_0012"
down_revision: str | None = "20260619_0011"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _uuid_type() -> sa.Uuid:
    return sa.Uuid(as_uuid=True)


def _audit_columns() -> list[sa.Column[sa.DateTime]]:
    return [
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
    ]


def _replace_trade_intent_side_constraint(check_sql: str) -> None:
    op.execute(
        sa.text(
            f"""
            DO $$
            DECLARE
                constraint_name text;
            BEGIN
                FOR constraint_name IN
                    SELECT con.conname
                    FROM pg_constraint con
                    JOIN pg_class rel ON rel.oid = con.conrelid
                    JOIN pg_namespace nsp ON nsp.oid = rel.relnamespace
                    WHERE rel.relname = 'trade_intents'
                      AND nsp.nspname = current_schema()
                      AND con.contype = 'c'
                      AND pg_get_constraintdef(con.oid) LIKE '%side%'
                      AND pg_get_constraintdef(con.oid) LIKE '%buy%'
                LOOP
                    EXECUTE format(
                        'ALTER TABLE trade_intents DROP CONSTRAINT %I',
                        constraint_name
                    );
                END LOOP;

                IF NOT EXISTS (
                    SELECT 1
                    FROM pg_constraint con
                    JOIN pg_class rel ON rel.oid = con.conrelid
                    JOIN pg_namespace nsp ON nsp.oid = rel.relnamespace
                    WHERE rel.relname = 'trade_intents'
                      AND nsp.nspname = current_schema()
                      AND con.conname = 'ck_trade_intents_trade_intent_side_valid'
                ) THEN
                    ALTER TABLE trade_intents
                    ADD CONSTRAINT ck_trade_intents_trade_intent_side_valid
                    CHECK ({check_sql});
                END IF;
            END $$;
            """
        )
    )


def upgrade() -> None:
    if op.get_bind().dialect.name != "sqlite":
        _replace_trade_intent_side_constraint("side IN ('buy', 'sell')")

    op.create_table(
        "system_health_events",
        sa.Column("id", _uuid_type(), nullable=False),
        sa.Column("component", sa.String(length=80), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("severity", sa.String(length=16), nullable=False),
        sa.Column("message", sa.String(length=500), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        *_audit_columns(),
        sa.CheckConstraint(
            "status IN ('ok', 'warming_up', 'degraded', 'failed')",
            name=op.f("ck_system_health_events_system_health_event_status_valid"),
        ),
        sa.CheckConstraint(
            "severity IN ('info', 'warning', 'error')",
            name=op.f("ck_system_health_events_system_health_event_severity_valid"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_system_health_events")),
    )
    op.create_index(
        "ix_system_health_events_component_time",
        "system_health_events",
        ["component", "occurred_at"],
    )
    op.create_index("ix_system_health_events_status", "system_health_events", ["status"])

    op.create_table(
        "runtime_ticks",
        sa.Column("id", _uuid_type(), nullable=False),
        sa.Column("account_id", _uuid_type(), nullable=True),
        sa.Column("bank_instrument_id", _uuid_type(), nullable=True),
        sa.Column("execution_instrument_id", _uuid_type(), nullable=True),
        sa.Column("strategy_id", _uuid_type(), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("summary", sa.JSON(), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=False),
        *_audit_columns(),
        sa.CheckConstraint(
            "status IN ('ok', 'warming_up', 'degraded', 'failed')",
            name=op.f("ck_runtime_ticks_runtime_tick_status_valid"),
        ),
        sa.CheckConstraint(
            "finished_at >= started_at",
            name=op.f("ck_runtime_ticks_runtime_tick_finished_gte_started"),
        ),
        sa.ForeignKeyConstraint(
            ["account_id"],
            ["virtual_accounts.id"],
            name=op.f("fk_runtime_ticks_account_id_virtual_accounts"),
        ),
        sa.ForeignKeyConstraint(
            ["bank_instrument_id"],
            ["bank_instruments.id"],
            name=op.f("fk_runtime_ticks_bank_instrument_id_bank_instruments"),
        ),
        sa.ForeignKeyConstraint(
            ["execution_instrument_id"],
            ["execution_instruments.id"],
            name=op.f("fk_runtime_ticks_execution_instrument_id_execution_instruments"),
        ),
        sa.ForeignKeyConstraint(
            ["strategy_id"],
            ["strategies.id"],
            name=op.f("fk_runtime_ticks_strategy_id_strategies"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_runtime_ticks")),
    )
    op.create_index("ix_runtime_ticks_finished", "runtime_ticks", ["finished_at"])
    op.create_index("ix_runtime_ticks_status", "runtime_ticks", ["status"])

    op.create_table(
        "telegram_bot_state",
        sa.Column("id", _uuid_type(), nullable=False),
        sa.Column("bot_name", sa.String(length=80), nullable=False),
        sa.Column("last_update_id", sa.Integer(), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("last_error", sa.String(length=500), nullable=True),
        *_audit_columns(),
        sa.CheckConstraint(
            "status IN ('disabled', 'polling', 'degraded', 'failed')",
            name=op.f("ck_telegram_bot_state_telegram_bot_state_status_valid"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_telegram_bot_state")),
        sa.UniqueConstraint("bot_name", name=op.f("uq_telegram_bot_state_bot_name")),
    )


def downgrade() -> None:
    op.drop_table("telegram_bot_state")
    op.drop_index("ix_runtime_ticks_status", table_name="runtime_ticks")
    op.drop_index("ix_runtime_ticks_finished", table_name="runtime_ticks")
    op.drop_table("runtime_ticks")
    op.drop_index("ix_system_health_events_status", table_name="system_health_events")
    op.drop_index(
        "ix_system_health_events_component_time",
        table_name="system_health_events",
    )
    op.drop_table("system_health_events")

    if op.get_bind().dialect.name != "sqlite":
        _replace_trade_intent_side_constraint("side IN ('buy')")
