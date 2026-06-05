"""add ml inference audits

Revision ID: c81f0a9d2e6b
Revises: 4ab9d80c31e2
Create Date: 2026-06-05 00:00:00.000000
"""

from alembic import op
import sqlalchemy as sa


revision = "c81f0a9d2e6b"
down_revision = "4ab9d80c31e2"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "ml_inference_audits",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("asset_id", sa.Integer(), nullable=False),
        sa.Column("risk_decision_id", sa.Integer(), nullable=True),
        sa.Column("model_run_id", sa.String(length=128), nullable=True),
        sa.Column("model_status", sa.String(length=32), nullable=False),
        sa.Column("model_target", sa.String(length=128), nullable=True),
        sa.Column("decision_mode", sa.String(length=32), nullable=False),
        sa.Column("recommendation", sa.String(length=64), nullable=False),
        sa.Column("predicted_probability", sa.Numeric(precision=8, scale=6), nullable=True),
        sa.Column("threshold", sa.Numeric(precision=8, scale=6), nullable=True),
        sa.Column("feature_snapshot", sa.JSON(), nullable=False),
        sa.Column("details_json", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["asset_id"], ["assets.id"], name="fk_ml_inference_audits_asset_id"),
        sa.ForeignKeyConstraint(
            ["risk_decision_id"], ["risk_decisions.id"], name="fk_ml_inference_audits_risk_decision_id"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_ml_inference_audits_asset_id"), "ml_inference_audits", ["asset_id"], unique=False)
    op.create_index(
        op.f("ix_ml_inference_audits_risk_decision_id"), "ml_inference_audits", ["risk_decision_id"], unique=False
    )
    op.create_index(op.f("ix_ml_inference_audits_model_run_id"), "ml_inference_audits", ["model_run_id"], unique=False)
    op.create_index(op.f("ix_ml_inference_audits_model_status"), "ml_inference_audits", ["model_status"], unique=False)
    op.create_index(
        op.f("ix_ml_inference_audits_decision_mode"), "ml_inference_audits", ["decision_mode"], unique=False
    )
    op.create_index(
        op.f("ix_ml_inference_audits_recommendation"), "ml_inference_audits", ["recommendation"], unique=False
    )
    op.create_index(op.f("ix_ml_inference_audits_created_at"), "ml_inference_audits", ["created_at"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_ml_inference_audits_created_at"), table_name="ml_inference_audits")
    op.drop_index(op.f("ix_ml_inference_audits_recommendation"), table_name="ml_inference_audits")
    op.drop_index(op.f("ix_ml_inference_audits_decision_mode"), table_name="ml_inference_audits")
    op.drop_index(op.f("ix_ml_inference_audits_model_status"), table_name="ml_inference_audits")
    op.drop_index(op.f("ix_ml_inference_audits_model_run_id"), table_name="ml_inference_audits")
    op.drop_index(op.f("ix_ml_inference_audits_risk_decision_id"), table_name="ml_inference_audits")
    op.drop_index(op.f("ix_ml_inference_audits_asset_id"), table_name="ml_inference_audits")
    op.drop_table("ml_inference_audits")
