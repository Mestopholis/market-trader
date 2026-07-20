# ruff: noqa: E501

"""Add append-only risk decision storage.

Revision ID: 20260720_0006
Revises: 20260719_0005
Create Date: 2026-07-20
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260720_0006"
down_revision: str | None = "20260719_0005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_APPEND_ONLY_TABLES = ("risk_decisions", "risk_checks", "risk_reservations")


def upgrade() -> None:
    _create_decisions()
    _create_checks()
    _create_reservations()
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


def _create_decisions() -> None:
    op.create_table(
        "risk_decisions",
        sa.Column("id", sa.String(length=64), primary_key=True),
        sa.Column("decision_key", sa.String(length=512), nullable=False),
        sa.Column("status", sa.String(length=40), nullable=False),
        sa.Column("proposal_kind", sa.String(length=40), nullable=False),
        sa.Column("policy_version", sa.String(length=128), nullable=False),
        sa.Column("policy_hash", sa.String(length=64), nullable=False),
        sa.Column("input_digest", sa.String(length=64), nullable=False),
        sa.Column("result_digest", sa.String(length=64), nullable=False),
        sa.Column("as_of", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "reason_summary",
            sa.JSON().with_variant(postgresql.JSONB(), "postgresql"),
            nullable=False,
        ),
        sa.Column("sizing_payload", sa.JSON(), nullable=False),
        sa.Column(
            "decision_payload",
            sa.JSON().with_variant(postgresql.JSONB(), "postgresql"),
            nullable=False,
        ),
        sa.Column("correlation_id", sa.String(length=64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ux_risk_decisions_decision_key", "risk_decisions", ["decision_key"], unique=True)
    op.create_index("ix_risk_decisions_status_as_of", "risk_decisions", ["status", "as_of"])
    op.create_index("ix_risk_decisions_policy", "risk_decisions", ["policy_version", "policy_hash"])
    op.create_index("ix_risk_decisions_correlation_id", "risk_decisions", ["correlation_id"])
    op.create_index(
        "ix_risk_decisions_reason_summary",
        "risk_decisions",
        ["reason_summary"],
        postgresql_using="gin",
    )
    op.create_index(
        "ix_risk_decisions_decision_payload",
        "risk_decisions",
        ["decision_payload"],
        postgresql_using="gin",
    )


def _create_checks() -> None:
    op.create_table(
        "risk_checks",
        sa.Column("id", sa.String(length=64), primary_key=True),
        sa.Column("check_key", sa.String(length=512), nullable=False),
        sa.Column("decision_id", sa.String(length=64), nullable=False),
        sa.Column("code", sa.String(length=128), nullable=False),
        sa.Column("severity", sa.String(length=40), nullable=False),
        sa.Column("state", sa.String(length=40), nullable=False),
        sa.Column("facts", sa.JSON().with_variant(postgresql.JSONB(), "postgresql"), nullable=False),
        sa.Column("source_keys", sa.JSON().with_variant(postgresql.JSONB(), "postgresql"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["decision_id"], ["risk_decisions.id"]),
    )
    op.create_index("ux_risk_checks_check_key", "risk_checks", ["check_key"], unique=True)
    op.create_index("ix_risk_checks_decision_id", "risk_checks", ["decision_id"])
    op.create_index("ix_risk_checks_code_state", "risk_checks", ["code", "state"])
    op.create_index("ix_risk_checks_facts", "risk_checks", ["facts"], postgresql_using="gin")
    op.create_index(
        "ix_risk_checks_source_keys",
        "risk_checks",
        ["source_keys"],
        postgresql_using="gin",
    )


def _create_reservations() -> None:
    op.create_table(
        "risk_reservations",
        sa.Column("id", sa.String(length=64), primary_key=True),
        sa.Column("reservation_key", sa.String(length=512), nullable=False),
        sa.Column("decision_id", sa.String(length=64), nullable=False),
        sa.Column("amount", sa.Numeric(20, 8), nullable=False),
        sa.Column(
            "reservation_payload",
            sa.JSON().with_variant(postgresql.JSONB(), "postgresql"),
            nullable=False,
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["decision_id"], ["risk_decisions.id"]),
    )
    op.create_index(
        "ux_risk_reservations_reservation_key",
        "risk_reservations",
        ["reservation_key"],
        unique=True,
    )
    op.create_index("ix_risk_reservations_decision_id", "risk_reservations", ["decision_id"])
    op.create_index(
        "ix_risk_reservations_payload",
        "risk_reservations",
        ["reservation_payload"],
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
