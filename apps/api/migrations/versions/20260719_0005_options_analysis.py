# ruff: noqa: E501

"""Add append-only options analysis storage.

Revision ID: 20260719_0005
Revises: 20260719_0004
Create Date: 2026-07-19
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260719_0005"
down_revision: str | None = "20260719_0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_APPEND_ONLY_TABLES = (
    "options_analysis_runs",
    "option_contract_evaluations",
    "option_spread_candidates",
    "option_spread_warnings",
)


def upgrade() -> None:
    _create_runs()
    _create_evaluations()
    _create_spreads()
    _create_warnings()
    if op.get_bind().dialect.name == "sqlite":
        for table in _APPEND_ONLY_TABLES:
            _create_append_only_triggers(table)


def downgrade() -> None:
    if op.get_bind().dialect.name == "sqlite":
        for table in reversed(_APPEND_ONLY_TABLES):
            op.execute(f"DROP TRIGGER IF EXISTS {table}_no_delete")
            op.execute(f"DROP TRIGGER IF EXISTS {table}_no_update")
    for table in reversed(_APPEND_ONLY_TABLES):
        op.drop_table(table)


def _create_runs() -> None:
    op.create_table(
        "options_analysis_runs",
        sa.Column("id", sa.String(length=64), primary_key=True),
        sa.Column("run_key", sa.String(length=512), nullable=False),
        sa.Column("scanner_run_id", sa.String(length=64), nullable=False),
        sa.Column("candidate_id", sa.String(length=64), nullable=False),
        sa.Column("symbol_id", sa.String(length=64), nullable=False),
        sa.Column("input_digest", sa.String(length=64), nullable=False),
        sa.Column("result_digest", sa.String(length=64), nullable=False),
        sa.Column("policy_version", sa.String(length=128), nullable=False),
        sa.Column("policy_hash", sa.String(length=64), nullable=False),
        sa.Column("as_of", sa.DateTime(timezone=True), nullable=False),
        sa.Column("result_counts", sa.JSON(), nullable=False),
        sa.Column(
            "reason_summary",
            sa.JSON().with_variant(postgresql.JSONB(), "postgresql"),
            nullable=False,
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["scanner_run_id"], ["scanner_runs.id"]),
        sa.ForeignKeyConstraint(["candidate_id"], ["candidates.id"]),
        sa.ForeignKeyConstraint(["symbol_id"], ["symbols.id"]),
    )
    op.create_index(
        "ux_options_analysis_runs_run_key", "options_analysis_runs", ["run_key"], unique=True
    )
    op.create_index(
        "ix_options_analysis_runs_candidate_as_of",
        "options_analysis_runs",
        ["candidate_id", "as_of"],
    )
    op.create_index(
        "ix_options_analysis_runs_symbol_as_of", "options_analysis_runs", ["symbol_id", "as_of"]
    )
    op.create_index(
        "ix_options_analysis_runs_reason_summary",
        "options_analysis_runs",
        ["reason_summary"],
        postgresql_using="gin",
    )


def _create_evaluations() -> None:
    op.create_table(
        "option_contract_evaluations",
        sa.Column("id", sa.String(length=64), primary_key=True),
        sa.Column("evaluation_key", sa.String(length=512), nullable=False),
        sa.Column("run_id", sa.String(length=64), nullable=False),
        sa.Column("contract_id", sa.String(length=512), nullable=False),
        sa.Column("state", sa.String(length=40), nullable=False),
        sa.Column(
            "reasons", sa.JSON().with_variant(postgresql.JSONB(), "postgresql"), nullable=False
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["run_id"], ["options_analysis_runs.id"]),
    )
    op.create_index(
        "ux_option_contract_evaluations_evaluation_key",
        "option_contract_evaluations",
        ["evaluation_key"],
        unique=True,
    )
    op.create_index(
        "ix_option_contract_evaluations_run_id", "option_contract_evaluations", ["run_id"]
    )
    op.create_index(
        "ix_option_contract_evaluations_reasons",
        "option_contract_evaluations",
        ["reasons"],
        postgresql_using="gin",
    )


def _create_spreads() -> None:
    op.create_table(
        "option_spread_candidates",
        sa.Column("id", sa.String(length=64), primary_key=True),
        sa.Column("spread_key", sa.String(length=512), nullable=False),
        sa.Column("run_id", sa.String(length=64), nullable=False),
        sa.Column("strategy", sa.String(length=40), nullable=False),
        sa.Column("long_contract_id", sa.String(length=512), nullable=False),
        sa.Column("short_contract_id", sa.String(length=512), nullable=False),
        sa.Column("expiration", sa.Date(), nullable=False),
        sa.Column("blocked", sa.Boolean(), nullable=False),
        sa.Column(
            "calculations", sa.JSON().with_variant(postgresql.JSONB(), "postgresql"), nullable=False
        ),
        sa.Column(
            "warning_keys", sa.JSON().with_variant(postgresql.JSONB(), "postgresql"), nullable=False
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["run_id"], ["options_analysis_runs.id"]),
    )
    op.create_index(
        "ux_option_spread_candidates_spread_key",
        "option_spread_candidates",
        ["spread_key"],
        unique=True,
    )
    op.create_index("ix_option_spread_candidates_run_id", "option_spread_candidates", ["run_id"])
    op.create_index(
        "ix_option_spread_candidates_calculations",
        "option_spread_candidates",
        ["calculations"],
        postgresql_using="gin",
    )


def _create_warnings() -> None:
    op.create_table(
        "option_spread_warnings",
        sa.Column("id", sa.String(length=64), primary_key=True),
        sa.Column("warning_key", sa.String(length=512), nullable=False),
        sa.Column("spread_id", sa.String(length=64), nullable=False),
        sa.Column("code", sa.String(length=128), nullable=False),
        sa.Column("severity", sa.String(length=40), nullable=False),
        sa.Column(
            "facts", sa.JSON().with_variant(postgresql.JSONB(), "postgresql"), nullable=False
        ),
        sa.Column(
            "source_keys", sa.JSON().with_variant(postgresql.JSONB(), "postgresql"), nullable=False
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["spread_id"], ["option_spread_candidates.id"]),
    )
    op.create_index(
        "ux_option_spread_warnings_warning_key",
        "option_spread_warnings",
        ["warning_key"],
        unique=True,
    )
    op.create_index("ix_option_spread_warnings_spread_id", "option_spread_warnings", ["spread_id"])
    op.create_index(
        "ix_option_spread_warnings_facts",
        "option_spread_warnings",
        ["facts"],
        postgresql_using="gin",
    )


def _create_append_only_triggers(table: str) -> None:
    op.execute(
        f"""
        CREATE TRIGGER {table}_no_update
        BEFORE UPDATE ON {table}
        BEGIN
          SELECT RAISE(ABORT, '{table} is append-only');
        END;
        """
    )
    op.execute(
        f"""
        CREATE TRIGGER {table}_no_delete
        BEFORE DELETE ON {table}
        BEGIN
          SELECT RAISE(ABORT, '{table} is append-only');
        END;
        """
    )
