"""Add deterministic scanner decision storage.

Revision ID: 20260719_0003
Revises: 20260718_0002
Create Date: 2026-07-19
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260719_0003"
down_revision: str | None = "20260718_0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "scanner_runs",
        sa.Column("id", sa.String(length=64), primary_key=True),
        sa.Column("run_key", sa.String(length=512), nullable=False),
        sa.Column("as_of", sa.DateTime(timezone=True), nullable=False),
        sa.Column("session_date", sa.Date(), nullable=False),
        sa.Column("input_digest", sa.String(length=64), nullable=False),
        sa.Column("universe_version", sa.String(length=80), nullable=False),
        sa.Column("universe_content_hash", sa.String(length=64), nullable=False),
        sa.Column("policy_versions", sa.JSON(), nullable=False),
        sa.Column("regime_state", sa.String(length=40), nullable=False),
        sa.Column("regime_score", sa.Numeric(12, 6), nullable=False),
        sa.Column("regime_explanation", sa.JSON(), nullable=False),
        sa.Column("result_counts", sa.JSON(), nullable=False),
        sa.Column("result_digest", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(length=40), nullable=False),
        sa.Column("correlation_id", sa.String(length=64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ux_scanner_runs_run_key", "scanner_runs", ["run_key"], unique=True)
    op.create_index("ix_scanner_runs_session_date", "scanner_runs", ["session_date"])
    op.create_index("ix_scanner_runs_status", "scanner_runs", ["status"])
    op.create_index("ix_scanner_runs_correlation_id", "scanner_runs", ["correlation_id"])

    op.create_table(
        "eligibility_decisions",
        sa.Column("id", sa.String(length=64), primary_key=True),
        sa.Column("decision_key", sa.String(length=512), nullable=False),
        sa.Column("scanner_run_id", sa.String(length=64), nullable=False),
        sa.Column("symbol_id", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(length=40), nullable=False),
        sa.Column(
            "reason_codes",
            sa.JSON().with_variant(postgresql.JSONB(), "postgresql"),
            nullable=False,
        ),
        sa.Column("observed_payload", sa.JSON(), nullable=False),
        sa.Column("input_digest", sa.String(length=64), nullable=False),
        sa.Column("policy_version", sa.String(length=80), nullable=False),
        sa.Column("correlation_id", sa.String(length=64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["scanner_run_id"], ["scanner_runs.id"]),
        sa.ForeignKeyConstraint(["symbol_id"], ["symbols.id"]),
        sa.UniqueConstraint(
            "scanner_run_id",
            "symbol_id",
            name="uq_eligibility_decisions_run_symbol",
        ),
    )
    op.create_index(
        "ux_eligibility_decisions_decision_key",
        "eligibility_decisions",
        ["decision_key"],
        unique=True,
    )
    op.create_index(
        "ix_eligibility_decisions_scanner_run_id",
        "eligibility_decisions",
        ["scanner_run_id"],
    )
    op.create_index(
        "ix_eligibility_decisions_symbol_id",
        "eligibility_decisions",
        ["symbol_id"],
    )
    op.create_index("ix_eligibility_decisions_status", "eligibility_decisions", ["status"])
    op.create_index(
        "ix_eligibility_decisions_reason_codes",
        "eligibility_decisions",
        ["reason_codes"],
        postgresql_using="gin",
    )
    op.create_index(
        "ix_eligibility_decisions_correlation_id",
        "eligibility_decisions",
        ["correlation_id"],
    )

    with op.batch_alter_table("signals") as batch_op:
        batch_op.add_column(sa.Column("signal_key", sa.String(length=512), nullable=True))
        batch_op.add_column(
            sa.Column(
                "scanner_run_id",
                sa.String(length=64),
                sa.ForeignKey("scanner_runs.id", name="fk_signals_scanner_run_id"),
                nullable=True,
            )
        )
        batch_op.add_column(sa.Column("strategy_id", sa.String(length=80), nullable=True))
        batch_op.add_column(sa.Column("input_digest", sa.String(length=64), nullable=True))
        batch_op.add_column(
            sa.Column(
                "reason_codes",
                sa.JSON().with_variant(postgresql.JSONB(), "postgresql"),
                nullable=True,
            )
        )
        batch_op.add_column(sa.Column("gate_payload", sa.JSON(), nullable=True))
        batch_op.add_column(sa.Column("component_score_payload", sa.JSON(), nullable=True))
        batch_op.add_column(
            sa.Column("scoring_policy_version", sa.String(length=80), nullable=True)
        )
    op.create_index("ux_signals_signal_key", "signals", ["signal_key"], unique=True)
    op.create_index("ix_signals_scanner_run_id", "signals", ["scanner_run_id"])

    with op.batch_alter_table("candidates") as batch_op:
        batch_op.add_column(sa.Column("candidate_key", sa.String(length=512), nullable=True))
        batch_op.add_column(
            sa.Column(
                "scanner_run_id",
                sa.String(length=64),
                sa.ForeignKey("scanner_runs.id", name="fk_candidates_scanner_run_id"),
                nullable=True,
            )
        )
        batch_op.add_column(sa.Column("strategy_id", sa.String(length=80), nullable=True))
        batch_op.add_column(sa.Column("direction", sa.String(length=20), nullable=True))
        batch_op.add_column(sa.Column("input_digest", sa.String(length=64), nullable=True))
        batch_op.add_column(
            sa.Column("scoring_policy_version", sa.String(length=80), nullable=True)
        )
    op.create_index("ux_candidates_candidate_key", "candidates", ["candidate_key"], unique=True)
    op.create_index("ix_candidates_scanner_run_id", "candidates", ["scanner_run_id"])


def downgrade() -> None:
    op.drop_index("ix_candidates_scanner_run_id", table_name="candidates")
    op.drop_index("ux_candidates_candidate_key", table_name="candidates")
    with op.batch_alter_table("candidates") as batch_op:
        batch_op.drop_column("scoring_policy_version")
        batch_op.drop_column("input_digest")
        batch_op.drop_column("direction")
        batch_op.drop_column("strategy_id")
        batch_op.drop_column("scanner_run_id")
        batch_op.drop_column("candidate_key")

    op.drop_index("ix_signals_scanner_run_id", table_name="signals")
    op.drop_index("ux_signals_signal_key", table_name="signals")
    with op.batch_alter_table("signals") as batch_op:
        batch_op.drop_column("scoring_policy_version")
        batch_op.drop_column("component_score_payload")
        batch_op.drop_column("gate_payload")
        batch_op.drop_column("reason_codes")
        batch_op.drop_column("input_digest")
        batch_op.drop_column("strategy_id")
        batch_op.drop_column("scanner_run_id")
        batch_op.drop_column("signal_key")

    op.drop_table("eligibility_decisions")
    op.drop_table("scanner_runs")
