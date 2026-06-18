"""add news sources and event risk snapshots

Revision ID: 20260618_0009
Revises: 20260618_0008
Create Date: 2026-06-18 21:00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260618_0009"
down_revision: str | None = "20260618_0008"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _uuid_type() -> sa.Uuid:
    return sa.Uuid(as_uuid=True)


def _audit_columns() -> list[sa.Column[sa.DateTime]]:
    return [
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
    ]


def upgrade() -> None:
    op.create_table(
        "news_sources",
        sa.Column("id", _uuid_type(), nullable=False),
        sa.Column("code", sa.String(length=80), nullable=False),
        sa.Column("name", sa.String(length=160), nullable=False),
        sa.Column("category", sa.String(length=80), nullable=False),
        sa.Column("reliability_score", sa.Numeric(precision=5, scale=4), nullable=False),
        sa.Column("source_policy", sa.String(length=500), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        *_audit_columns(),
        sa.CheckConstraint(
            "category IN ('central_bank', 'turkish_financial', 'global_financial', "
            "'commodity', 'economic_calendar')",
            name=op.f("ck_news_sources_news_source_category_valid"),
        ),
        sa.CheckConstraint(
            "reliability_score >= 0 AND reliability_score <= 1",
            name=op.f("ck_news_sources_news_source_reliability_range"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_news_sources")),
        sa.UniqueConstraint("code", name=op.f("uq_news_sources_code")),
    )
    op.create_index("ix_news_sources_status", "news_sources", ["status"])

    op.create_table(
        "news_events",
        sa.Column("id", _uuid_type(), nullable=False),
        sa.Column("source_id", _uuid_type(), nullable=False),
        sa.Column("source_event_time", sa.DateTime(timezone=True), nullable=True),
        sa.Column("provider_reported_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("fetched_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("title", sa.String(length=300), nullable=False),
        sa.Column("summary", sa.String(length=1000), nullable=False),
        sa.Column("url", sa.String(length=500), nullable=True),
        sa.Column("affected_assets", sa.JSON(), nullable=False),
        sa.Column("event_type", sa.String(length=80), nullable=False),
        sa.Column("content_hash", sa.String(length=64), nullable=False),
        *_audit_columns(),
        sa.CheckConstraint(
            "fetched_at >= published_at",
            name=op.f("ck_news_events_news_event_fetched_gte_published"),
        ),
        sa.ForeignKeyConstraint(
            ["source_id"],
            ["news_sources.id"],
            name=op.f("fk_news_events_source_id_news_sources"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_news_events")),
        sa.UniqueConstraint("source_id", "content_hash", name=op.f("uq_news_events_source_id")),
    )
    op.create_index("ix_news_events_source_published", "news_events", ["source_id", "published_at"])
    op.create_index("ix_news_events_event_type", "news_events", ["event_type"])

    op.create_table(
        "event_risk_snapshots",
        sa.Column("id", _uuid_type(), nullable=False),
        sa.Column("news_event_id", _uuid_type(), nullable=False),
        sa.Column("source", sa.String(length=80), nullable=False),
        sa.Column("schema_version", sa.String(length=80), nullable=False),
        sa.Column("event_type", sa.String(length=80), nullable=False),
        sa.Column("affected_assets", sa.JSON(), nullable=False),
        sa.Column("direction_bias", sa.String(length=16), nullable=False),
        sa.Column("confidence", sa.Numeric(precision=5, scale=4), nullable=False),
        sa.Column("time_horizon", sa.String(length=16), nullable=False),
        sa.Column("risk_level", sa.String(length=16), nullable=False),
        sa.Column("reasoning", sa.String(length=1000), nullable=False),
        sa.Column("action_recommendation", sa.String(length=32), nullable=False),
        sa.Column("interpreted_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
        *_audit_columns(),
        sa.CheckConstraint(
            "direction_bias IN ('bullish', 'bearish', 'neutral', 'mixed', 'unknown')",
            name=op.f("ck_event_risk_snapshots_event_risk_direction_bias_valid"),
        ),
        sa.CheckConstraint(
            "time_horizon IN ('intraday', '1d', '1w', '1m', 'unknown')",
            name=op.f("ck_event_risk_snapshots_event_risk_time_horizon_valid"),
        ),
        sa.CheckConstraint(
            "risk_level IN ('low', 'medium', 'high', 'unknown')",
            name=op.f("ck_event_risk_snapshots_event_risk_level_valid"),
        ),
        sa.CheckConstraint(
            "action_recommendation IN ('veto', 'reduce_risk', 'no_trade', 'monitor', 'none')",
            name=op.f("ck_event_risk_snapshots_event_risk_action_valid"),
        ),
        sa.CheckConstraint(
            "confidence >= 0 AND confidence <= 1",
            name=op.f("ck_event_risk_snapshots_event_risk_confidence_range"),
        ),
        sa.CheckConstraint(
            "expires_at > interpreted_at",
            name=op.f("ck_event_risk_snapshots_event_risk_expiry_valid"),
        ),
        sa.ForeignKeyConstraint(
            ["news_event_id"],
            ["news_events.id"],
            name=op.f("fk_event_risk_snapshots_news_event_id_news_events"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_event_risk_snapshots")),
        sa.UniqueConstraint(
            "news_event_id",
            "schema_version",
            name=op.f("uq_event_risk_snapshots_news_event_id"),
        ),
    )
    op.create_index("ix_event_risk_snapshots_event", "event_risk_snapshots", ["news_event_id"])
    op.create_index(
        "ix_event_risk_snapshots_action",
        "event_risk_snapshots",
        ["action_recommendation"],
    )
    op.create_index("ix_event_risk_snapshots_expires", "event_risk_snapshots", ["expires_at"])


def downgrade() -> None:
    op.drop_index("ix_event_risk_snapshots_expires", table_name="event_risk_snapshots")
    op.drop_index("ix_event_risk_snapshots_action", table_name="event_risk_snapshots")
    op.drop_index("ix_event_risk_snapshots_event", table_name="event_risk_snapshots")
    op.drop_table("event_risk_snapshots")
    op.drop_index("ix_news_events_event_type", table_name="news_events")
    op.drop_index("ix_news_events_source_published", table_name="news_events")
    op.drop_table("news_events")
    op.drop_index("ix_news_sources_status", table_name="news_sources")
    op.drop_table("news_sources")
