"""Add append-only catalyst event storage.

Revision ID: 20260719_0004
Revises: 20260719_0003
Create Date: 2026-07-19
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260719_0004"
down_revision: str | None = "20260719_0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_APPEND_ONLY_TABLES = (
    "catalyst_observations",
    "catalyst_quarantine",
    "catalyst_decisions",
    "catalyst_summaries",
)


def upgrade() -> None:
    _create_source_runs()
    _create_observations()
    _create_quarantine()
    _create_decisions()
    _create_summaries()
    if op.get_bind().dialect.name == "sqlite":
        for table in _APPEND_ONLY_TABLES:
            _create_append_only_triggers(table)


def downgrade() -> None:
    if op.get_bind().dialect.name == "sqlite":
        for table in reversed(_APPEND_ONLY_TABLES):
            op.execute(f"DROP TRIGGER IF EXISTS {table}_no_delete")
            op.execute(f"DROP TRIGGER IF EXISTS {table}_no_update")
    op.drop_table("catalyst_summaries")
    op.drop_table("catalyst_decisions")
    op.drop_table("catalyst_quarantine")
    op.drop_table("catalyst_observations")
    op.drop_table("catalyst_source_runs")


def _create_source_runs() -> None:
    op.create_table(
        "catalyst_source_runs",
        sa.Column("id", sa.String(length=64), primary_key=True),
        sa.Column("run_key", sa.String(length=512), nullable=False),
        sa.Column("source_id", sa.String(length=128), nullable=False),
        sa.Column("capability", sa.String(length=80), nullable=False),
        sa.Column("request_digest", sa.String(length=64), nullable=False),
        sa.Column("source_policy_version", sa.String(length=128), nullable=False),
        sa.Column("as_of", sa.DateTime(timezone=True), nullable=False),
        sa.Column("state", sa.String(length=40), nullable=False),
        sa.Column("policy_versions", sa.JSON(), nullable=False),
        sa.Column("policy_hashes", sa.JSON(), nullable=False),
        sa.Column("result_counts", sa.JSON(), nullable=False),
        sa.Column(
            "reasons",
            sa.JSON().with_variant(postgresql.JSONB(), "postgresql"),
            nullable=False,
        ),
        sa.Column("result_digest", sa.String(length=64), nullable=False),
        sa.Column("correlation_id", sa.String(length=64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index(
        "ux_catalyst_source_runs_run_key",
        "catalyst_source_runs",
        ["run_key"],
        unique=True,
    )
    op.create_index(
        "ix_catalyst_source_runs_source_as_of",
        "catalyst_source_runs",
        ["source_id", "as_of"],
    )
    op.create_index("ix_catalyst_source_runs_state", "catalyst_source_runs", ["state"])
    op.create_index(
        "ix_catalyst_source_runs_reasons",
        "catalyst_source_runs",
        ["reasons"],
        postgresql_using="gin",
    )
    op.create_index(
        "ix_catalyst_source_runs_correlation_id",
        "catalyst_source_runs",
        ["correlation_id"],
    )


def _create_observations() -> None:
    op.create_table(
        "catalyst_observations",
        sa.Column("id", sa.String(length=64), primary_key=True),
        sa.Column("observation_key", sa.String(length=512), nullable=False),
        sa.Column("source_run_id", sa.String(length=64), nullable=False),
        sa.Column("ingestion_key", sa.String(length=512), nullable=False),
        sa.Column("authoritative_digest", sa.String(length=64), nullable=False),
        sa.Column("external_text_digest", sa.String(length=64), nullable=False),
        sa.Column("source_id", sa.String(length=128), nullable=False),
        sa.Column("authority_class", sa.String(length=40), nullable=False),
        sa.Column("event_family", sa.String(length=40), nullable=False),
        sa.Column("event_category", sa.String(length=128), nullable=False),
        sa.Column("provider_event_id", sa.String(length=512), nullable=False),
        sa.Column("source_reference", sa.String(length=2048), nullable=False),
        sa.Column("symbol_id", sa.String(length=64), nullable=True),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("ingested_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("scheduled_for", sa.DateTime(timezone=True), nullable=True),
        sa.Column("valid_until", sa.DateTime(timezone=True), nullable=False),
        sa.Column("structured_facts", sa.JSON(), nullable=False),
        sa.Column("external_text", sa.JSON(), nullable=False),
        sa.Column(
            "quality_reasons",
            sa.JSON().with_variant(postgresql.JSONB(), "postgresql"),
            nullable=False,
        ),
        sa.Column("source_schema_version", sa.Integer(), nullable=False),
        sa.Column("normalization_schema_version", sa.Integer(), nullable=False),
        sa.Column("configuration_version", sa.String(length=128), nullable=False),
        sa.Column("correlation_id", sa.String(length=64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["source_run_id"], ["catalyst_source_runs.id"]),
        sa.ForeignKeyConstraint(["symbol_id"], ["symbols.id"]),
    )
    op.create_index(
        "ux_catalyst_observations_observation_key",
        "catalyst_observations",
        ["observation_key"],
        unique=True,
    )
    op.create_index(
        "ux_catalyst_observations_ingestion_key",
        "catalyst_observations",
        ["ingestion_key"],
        unique=True,
    )
    op.create_index(
        "ix_catalyst_observations_source_published",
        "catalyst_observations",
        ["source_id", "published_at"],
    )
    op.create_index(
        "ix_catalyst_observations_symbol_published",
        "catalyst_observations",
        ["symbol_id", "published_at"],
    )
    op.create_index(
        "ix_catalyst_observations_family_category",
        "catalyst_observations",
        ["event_family", "event_category"],
    )
    op.create_index(
        "ix_catalyst_observations_quality_reasons",
        "catalyst_observations",
        ["quality_reasons"],
        postgresql_using="gin",
    )
    op.create_index(
        "ix_catalyst_observations_correlation_id",
        "catalyst_observations",
        ["correlation_id"],
    )


def _create_quarantine() -> None:
    op.create_table(
        "catalyst_quarantine",
        sa.Column("id", sa.String(length=64), primary_key=True),
        sa.Column("source_run_id", sa.String(length=64), nullable=False),
        sa.Column("ingestion_key", sa.String(length=512), nullable=False),
        sa.Column("sanitized_payload_digest", sa.String(length=64), nullable=False),
        sa.Column("source_id", sa.String(length=128), nullable=True),
        sa.Column("provider_event_id", sa.String(length=512), nullable=True),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("ingested_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "reasons",
            sa.JSON().with_variant(postgresql.JSONB(), "postgresql"),
            nullable=False,
        ),
        sa.Column("sanitized_payload", sa.JSON(), nullable=False),
        sa.Column("source_schema_version", sa.Integer(), nullable=True),
        sa.Column("normalization_schema_version", sa.Integer(), nullable=True),
        sa.Column("correlation_id", sa.String(length=64), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["source_run_id"], ["catalyst_source_runs.id"]),
    )
    op.create_index(
        "ux_catalyst_quarantine_ingestion_key",
        "catalyst_quarantine",
        ["ingestion_key"],
        unique=True,
    )
    op.create_index(
        "ix_catalyst_quarantine_source_ingested",
        "catalyst_quarantine",
        ["source_id", "ingested_at"],
    )
    op.create_index(
        "ix_catalyst_quarantine_reasons",
        "catalyst_quarantine",
        ["reasons"],
        postgresql_using="gin",
    )
    op.create_index(
        "ix_catalyst_quarantine_correlation_id",
        "catalyst_quarantine",
        ["correlation_id"],
    )


def _create_decisions() -> None:
    op.create_table(
        "catalyst_decisions",
        sa.Column("id", sa.String(length=64), primary_key=True),
        sa.Column("decision_key", sa.String(length=512), nullable=False),
        sa.Column("source_run_id", sa.String(length=64), nullable=False),
        sa.Column("scope", sa.String(length=40), nullable=False),
        sa.Column("symbol_id", sa.String(length=64), nullable=True),
        sa.Column("as_of", sa.DateTime(timezone=True), nullable=False),
        sa.Column("materiality", sa.String(length=40), nullable=False),
        sa.Column("direction", sa.String(length=40), nullable=False),
        sa.Column("confirmation", sa.String(length=40), nullable=False),
        sa.Column("risk_state", sa.String(length=40), nullable=False),
        sa.Column(
            "reasons",
            sa.JSON().with_variant(postgresql.JSONB(), "postgresql"),
            nullable=False,
        ),
        sa.Column(
            "observation_keys",
            sa.JSON().with_variant(postgresql.JSONB(), "postgresql"),
            nullable=False,
        ),
        sa.Column("policy_versions", sa.JSON(), nullable=False),
        sa.Column("input_digest", sa.String(length=64), nullable=False),
        sa.Column("explanation", sa.JSON(), nullable=False),
        sa.Column("correlation_id", sa.String(length=64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["source_run_id"], ["catalyst_source_runs.id"]),
        sa.ForeignKeyConstraint(["symbol_id"], ["symbols.id"]),
    )
    op.create_index(
        "ux_catalyst_decisions_decision_key",
        "catalyst_decisions",
        ["decision_key"],
        unique=True,
    )
    op.create_index(
        "ix_catalyst_decisions_source_run_id",
        "catalyst_decisions",
        ["source_run_id"],
    )
    op.create_index(
        "ix_catalyst_decisions_symbol_as_of",
        "catalyst_decisions",
        ["symbol_id", "as_of"],
    )
    op.create_index("ix_catalyst_decisions_as_of", "catalyst_decisions", ["as_of"])
    op.create_index(
        "ix_catalyst_decisions_reasons",
        "catalyst_decisions",
        ["reasons"],
        postgresql_using="gin",
    )
    op.create_index(
        "ix_catalyst_decisions_observation_keys",
        "catalyst_decisions",
        ["observation_keys"],
        postgresql_using="gin",
    )
    op.create_index(
        "ix_catalyst_decisions_correlation_id",
        "catalyst_decisions",
        ["correlation_id"],
    )


def _create_summaries() -> None:
    op.create_table(
        "catalyst_summaries",
        sa.Column("id", sa.String(length=64), primary_key=True),
        sa.Column("summary_key", sa.String(length=512), nullable=False),
        sa.Column("source_run_id", sa.String(length=64), nullable=False),
        sa.Column("provider_id", sa.String(length=128), nullable=False),
        sa.Column("generated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "segments",
            sa.JSON().with_variant(postgresql.JSONB(), "postgresql"),
            nullable=False,
        ),
        sa.Column("policy_version", sa.String(length=128), nullable=False),
        sa.Column("content_digest", sa.String(length=64), nullable=False),
        sa.Column("correlation_id", sa.String(length=64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["source_run_id"], ["catalyst_source_runs.id"]),
    )
    op.create_index(
        "ux_catalyst_summaries_summary_key",
        "catalyst_summaries",
        ["summary_key"],
        unique=True,
    )
    op.create_index(
        "ix_catalyst_summaries_source_run_id",
        "catalyst_summaries",
        ["source_run_id"],
    )
    op.create_index(
        "ix_catalyst_summaries_generated_at",
        "catalyst_summaries",
        ["generated_at"],
    )
    op.create_index(
        "ix_catalyst_summaries_segments",
        "catalyst_summaries",
        ["segments"],
        postgresql_using="gin",
    )
    op.create_index(
        "ix_catalyst_summaries_correlation_id",
        "catalyst_summaries",
        ["correlation_id"],
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
