"""add fx references and yahoo metadata backfill

Revision ID: 20260621_0016
Revises: 20260621_0015
Create Date: 2026-06-21 18:30:00
"""

from collections.abc import Sequence
from typing import Any

import sqlalchemy as sa
from alembic import op

revision: str = "20260621_0016"
down_revision: str | None = "20260621_0015"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _uuid_type() -> sa.Uuid[Any]:
    return sa.Uuid(as_uuid=True)


def _drop_reference_backfill_instrument_fk() -> None:
    op.execute(
        sa.text(
            """
            DO $$
            DECLARE
                constraint_name text;
            BEGIN
                SELECT c.conname
                INTO constraint_name
                FROM pg_constraint c
                JOIN pg_class t ON t.oid = c.conrelid
                JOIN pg_attribute a
                  ON a.attrelid = t.oid
                 AND a.attnum = ANY(c.conkey)
                JOIN pg_class rt ON rt.oid = c.confrelid
                WHERE c.contype = 'f'
                  AND t.relname = 'reference_data_backfill_runs'
                  AND a.attname = 'instrument_id'
                  AND rt.relname = 'reference_market_instruments'
                LIMIT 1;

                IF constraint_name IS NOT NULL THEN
                    EXECUTE format(
                        'ALTER TABLE reference_data_backfill_runs DROP CONSTRAINT %I',
                        constraint_name
                    );
                END IF;
            END $$;
            """
        )
    )


def upgrade() -> None:
    op.create_table(
        "fx_reference_instruments",
        sa.Column("id", _uuid_type(), nullable=False),
        sa.Column("pair", sa.String(length=20), nullable=False),
        sa.Column("symbol", sa.String(length=120), nullable=False),
        sa.Column("source", sa.String(length=120), nullable=False),
        sa.Column("base_currency_id", _uuid_type(), nullable=False),
        sa.Column("quote_currency_id", _uuid_type(), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("provider", sa.String(length=120), nullable=True),
        sa.Column("exchange", sa.String(length=120), nullable=True),
        sa.Column("timezone", sa.String(length=80), nullable=True),
        sa.Column("data_delay_seconds", sa.Integer(), nullable=True),
        sa.Column("delay_policy", sa.String(length=32), nullable=True),
        sa.Column("source_delay_status", sa.String(length=32), nullable=True),
        sa.Column("session_calendar_code", sa.String(length=80), nullable=True),
        sa.Column("source_terms_status", sa.String(length=32), nullable=True),
        sa.Column("source_risk_status", sa.String(length=64), nullable=True),
        sa.Column("approved_by", sa.String(length=120), nullable=True),
        sa.Column("approved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("approved_scope", sa.String(length=80), nullable=True),
        sa.Column("approved_symbols", sa.String(length=255), nullable=True),
        sa.Column("approved_timeframe", sa.String(length=20), nullable=True),
        sa.Column("real_money_allowed", sa.Boolean(), server_default=sa.false(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "data_delay_seconds IS NULL OR data_delay_seconds >= 0",
            name=op.f("ck_fx_reference_instruments_fx_reference_data_delay_non_negative"),
        ),
        sa.CheckConstraint(
            "delay_policy IS NULL OR delay_policy IN "
            "('none', 'provider_delayed', 'end_of_day', 'manual_review')",
            name=op.f("ck_fx_reference_instruments_fx_reference_delay_policy_valid"),
        ),
        sa.CheckConstraint(
            "source_delay_status IS NULL OR source_delay_status IN "
            "('unknown', 'verified', 'assumed_conservative', 'not_applicable')",
            name=op.f("ck_fx_reference_instruments_fx_reference_source_delay_status_valid"),
        ),
        sa.CheckConstraint(
            "source_terms_status IS NULL OR source_terms_status IN "
            "('unknown', 'research_only', 'not_approved', 'approved')",
            name=op.f("ck_fx_reference_instruments_fx_reference_terms_status_valid"),
        ),
        sa.CheckConstraint(
            "source_risk_status IS NULL OR source_risk_status IN "
            "('unknown', 'owner_accepted_paper_use_risk', 'not_approved')",
            name=op.f("ck_fx_reference_instruments_fx_reference_source_risk_status_valid"),
        ),
        sa.CheckConstraint(
            "approved_scope IS NULL OR approved_scope IN ('live-paper only')",
            name=op.f("ck_fx_reference_instruments_fx_reference_approved_scope_valid"),
        ),
        sa.ForeignKeyConstraint(
            ["base_currency_id"],
            ["currencies.id"],
            name=op.f("fk_fx_reference_instruments_base_currency_id_currencies"),
        ),
        sa.ForeignKeyConstraint(
            ["quote_currency_id"],
            ["currencies.id"],
            name=op.f("fk_fx_reference_instruments_quote_currency_id_currencies"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_fx_reference_instruments")),
        sa.UniqueConstraint("pair", "source", name=op.f("uq_fx_reference_instruments_pair")),
        sa.UniqueConstraint("symbol", "source", name=op.f("uq_fx_reference_instruments_symbol")),
    )
    op.create_index(
        "ix_fx_reference_instruments_status",
        "fx_reference_instruments",
        ["status"],
    )
    if op.get_bind().dialect.name != "sqlite":
        op.alter_column("fx_reference_instruments", "real_money_allowed", server_default=None)

    with op.batch_alter_table("reference_data_backfill_runs") as batch_op:
        if op.get_bind().dialect.name != "sqlite":
            _drop_reference_backfill_instrument_fk()
        batch_op.add_column(sa.Column("feasibility_summary", sa.JSON(), nullable=True))

    op.execute(
        sa.text(
            """
            UPDATE reference_market_instruments
            SET
                provider = 'yahoo_finance_chart',
                exchange = CASE
                    WHEN symbol IN ('SI=F', 'GC=F') THEN 'COMEX'
                    ELSE exchange
                END,
                timezone = COALESCE(timezone, 'America/New_York'),
                data_delay_seconds = NULL,
                delay_policy = 'manual_review',
                source_delay_status = CASE
                    WHEN symbol = 'SI=F' THEN 'assumed_conservative'
                    WHEN symbol = 'GC=F' THEN 'unknown'
                    ELSE source_delay_status
                END,
                session_calendar_code = 'yahoo-research-manual-review',
                source_terms_status = 'not_approved',
                source_risk_status = CASE
                    WHEN symbol = 'SI=F' THEN 'owner_accepted_paper_use_risk'
                    WHEN symbol = 'GC=F' THEN 'not_approved'
                    ELSE source_risk_status
                END,
                approved_by = CASE
                    WHEN symbol = 'SI=F' THEN COALESCE(approved_by, 'owner/manual')
                    ELSE approved_by
                END,
                approved_scope = CASE
                    WHEN symbol = 'SI=F' THEN 'live-paper only'
                    ELSE approved_scope
                END,
                approved_symbols = CASE
                    WHEN symbol = 'SI=F' THEN 'SI=F,TRY=X'
                    ELSE approved_symbols
                END,
                approved_timeframe = CASE
                    WHEN symbol = 'SI=F' THEN '4h'
                    ELSE approved_timeframe
                END,
                real_money_allowed = false
            WHERE source = 'yahoo_research'
              AND symbol IN ('SI=F', 'GC=F')
            """
        )
    )
    if op.get_bind().dialect.name == "sqlite":
        op.execute(
            sa.text(
                """
                UPDATE instrument_mappings
                SET unit_conversion_rule_id = (
                    SELECT ucr.id
                    FROM unit_conversion_rules ucr
                    JOIN units from_unit ON from_unit.id = ucr.from_unit_id
                    JOIN units to_unit ON to_unit.id = ucr.to_unit_id
                    WHERE from_unit.code = 'OZ'
                      AND to_unit.code = 'GRAM'
                      AND ucr.effective_to IS NULL
                    LIMIT 1
                )
                WHERE fx_pair = 'USDTRY'
                  AND reference_market_instrument_id IN (
                    SELECT id
                    FROM reference_market_instruments
                    WHERE source = 'yahoo_research'
                      AND symbol = 'SI=F'
                  )
                """
            )
        )
    else:
        op.execute(
            sa.text(
                """
                UPDATE instrument_mappings im
                SET unit_conversion_rule_id = ucr.id
                FROM reference_market_instruments rmi,
                     units from_unit,
                     units to_unit,
                     unit_conversion_rules ucr
                WHERE im.reference_market_instrument_id = rmi.id
                  AND rmi.source = 'yahoo_research'
                  AND rmi.symbol = 'SI=F'
                  AND im.fx_pair = 'USDTRY'
                  AND from_unit.code = 'OZ'
                  AND to_unit.code = 'GRAM'
                  AND ucr.from_unit_id = from_unit.id
                  AND ucr.to_unit_id = to_unit.id
                  AND ucr.effective_to IS NULL
                """
            )
        )


def downgrade() -> None:
    with op.batch_alter_table("reference_data_backfill_runs") as batch_op:
        batch_op.drop_column("feasibility_summary")
        if op.get_bind().dialect.name != "sqlite":
            batch_op.create_foreign_key(
                "fk_ref_backfill_runs_instrument_id",
                "reference_market_instruments",
                ["instrument_id"],
                ["id"],
            )
    op.drop_index("ix_fx_reference_instruments_status", table_name="fx_reference_instruments")
    op.drop_table("fx_reference_instruments")
