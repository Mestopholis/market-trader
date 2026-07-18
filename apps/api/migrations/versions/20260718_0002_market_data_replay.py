"""Add provider-neutral market data replay storage.

Revision ID: 20260718_0002
Revises: 20260718_0001
Create Date: 2026-07-18
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260718_0002"
down_revision: str | None = "20260718_0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "market_data_snapshots",
        sa.Column(
            "data_kind",
            sa.String(length=40),
            nullable=False,
            server_default="legacy",
        ),
    )
    op.add_column(
        "market_data_snapshots",
        sa.Column("ingestion_key", sa.String(length=80), nullable=True),
    )
    op.add_column(
        "market_data_snapshots",
        sa.Column("payload_digest", sa.String(length=64), nullable=True),
    )
    op.execute(
        "UPDATE market_data_snapshots "
        "SET ingestion_key = 'legacy:' || id, payload_digest = 'legacy:' || id "
        "WHERE ingestion_key IS NULL OR payload_digest IS NULL"
    )
    with op.batch_alter_table("market_data_snapshots") as batch_op:
        batch_op.alter_column(
            "data_kind",
            existing_type=sa.String(length=40),
            existing_nullable=False,
            server_default=None,
        )
        batch_op.alter_column(
            "ingestion_key",
            existing_type=sa.String(length=80),
            nullable=False,
        )
        batch_op.alter_column(
            "payload_digest",
            existing_type=sa.String(length=64),
            nullable=False,
        )
    op.create_index(
        "ux_market_data_snapshot_ingestion_key",
        "market_data_snapshots",
        ["ingestion_key"],
        unique=True,
    )
    op.create_index(
        "ix_market_data_source_kind_ingested",
        "market_data_snapshots",
        ["source", "data_kind", "ingested_at"],
    )

    op.create_table(
        "market_data_quarantine",
        sa.Column("id", sa.String(length=64), primary_key=True),
        sa.Column("ingestion_key", sa.String(length=80), nullable=False),
        sa.Column("source", sa.String(length=80), nullable=False),
        sa.Column("event_id", sa.String(length=120), nullable=False),
        sa.Column("data_kind", sa.String(length=40), nullable=False),
        sa.Column("observed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("ingested_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("symbol_identity", sa.String(length=80), nullable=True),
        sa.Column("instrument_identity", sa.String(length=160), nullable=True),
        sa.Column("sanitized_payload", sa.JSON(), nullable=False),
        sa.Column("payload_digest", sa.String(length=64), nullable=False),
        sa.Column(
            "reason_codes",
            sa.JSON().with_variant(postgresql.JSONB(), "postgresql"),
            nullable=False,
        ),
        sa.Column("fixture_schema_version", sa.Integer(), nullable=False),
        sa.Column("normalized_schema_version", sa.Integer(), nullable=True),
        sa.Column("configuration_version", sa.String(length=80), nullable=False),
        sa.Column("correlation_id", sa.String(length=64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index(
        "ux_market_data_quarantine_ingestion_key",
        "market_data_quarantine",
        ["ingestion_key"],
        unique=True,
    )
    op.create_index(
        "ix_market_data_quarantine_identity_ingested",
        "market_data_quarantine",
        ["source", "data_kind", "symbol_identity", "ingested_at"],
    )
    op.create_index(
        "ix_market_data_quarantine_reason_codes",
        "market_data_quarantine",
        ["reason_codes"],
        postgresql_using="gin",
    )
    op.create_index(
        "ix_market_data_quarantine_correlation_id",
        "market_data_quarantine",
        ["correlation_id"],
    )

    if op.get_bind().dialect.name == "sqlite":
        op.execute(
            """
            CREATE TRIGGER market_data_quarantine_no_update
            BEFORE UPDATE ON market_data_quarantine
            BEGIN
              SELECT RAISE(ABORT, 'market_data_quarantine is append-only');
            END;
            """
        )
        op.execute(
            """
            CREATE TRIGGER market_data_quarantine_no_delete
            BEFORE DELETE ON market_data_quarantine
            BEGIN
              SELECT RAISE(ABORT, 'market_data_quarantine is append-only');
            END;
            """
        )


def downgrade() -> None:
    if op.get_bind().dialect.name == "sqlite":
        op.execute("DROP TRIGGER IF EXISTS market_data_quarantine_no_delete")
        op.execute("DROP TRIGGER IF EXISTS market_data_quarantine_no_update")

    op.drop_table("market_data_quarantine")
    op.drop_index("ix_market_data_source_kind_ingested", table_name="market_data_snapshots")
    op.drop_index("ux_market_data_snapshot_ingestion_key", table_name="market_data_snapshots")
    with op.batch_alter_table("market_data_snapshots") as batch_op:
        batch_op.drop_column("payload_digest")
        batch_op.drop_column("ingestion_key")
        batch_op.drop_column("data_kind")
