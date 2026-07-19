"""Add append-only options analysis storage."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260719_0005"
down_revision: str | None = "20260719_0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_TABLES = (
    "options_analysis_runs",
    "option_contract_evaluations",
    "option_spread_candidates",
    "option_spread_warnings",
)


def upgrade() -> None:
    op.create_table(
        "options_analysis_runs",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("run_key", sa.String(512), nullable=False, unique=True),
        sa.Column("result_digest", sa.String(64), nullable=False),
        sa.Column("as_of", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_table(
        "option_contract_evaluations",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("evaluation_key", sa.String(512), nullable=False, unique=True),
        sa.Column(
            "run_id", sa.String(64), sa.ForeignKey("options_analysis_runs.id"), nullable=False
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_table(
        "option_spread_candidates",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("spread_key", sa.String(512), nullable=False, unique=True),
        sa.Column(
            "run_id", sa.String(64), sa.ForeignKey("options_analysis_runs.id"), nullable=False
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_table(
        "option_spread_warnings",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("warning_key", sa.String(512), nullable=False, unique=True),
        sa.Column(
            "spread_id",
            sa.String(64),
            sa.ForeignKey("option_spread_candidates.id"),
            nullable=False,
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    if op.get_bind().dialect.name == "sqlite":
        for table in _TABLES:
            _create_append_only_triggers(table)


def downgrade() -> None:
    if op.get_bind().dialect.name == "sqlite":
        for table in reversed(_TABLES):
            op.execute(f"DROP TRIGGER IF EXISTS {table}_no_delete")
            op.execute(f"DROP TRIGGER IF EXISTS {table}_no_update")
    for table in reversed(_TABLES):
        op.drop_table(table)


def _create_append_only_triggers(table: str) -> None:
    for operation in ("update", "delete"):
        op.execute(
            f"CREATE TRIGGER {table}_no_{operation} BEFORE {operation.upper()} ON {table} "
            f"BEGIN SELECT RAISE(ABORT, '{table} is append-only'); END;"
        )
