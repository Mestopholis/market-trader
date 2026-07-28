"""Add Schwab read-only OAuth token storage.

Revision ID: 20260726_0011
Revises: 20260720_0006
Create Date: 2026-07-26
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260726_0011"
down_revision: str | None = "20260720_0006"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "schwab_oauth_states",
        sa.Column("id", sa.String(length=64), primary_key=True),
        sa.Column("state_hash", sa.String(length=128), nullable=False),
        sa.Column("nonce_hash", sa.String(length=128), nullable=False),
        sa.Column("callback_url", sa.String(length=512), nullable=False),
        sa.Column("status", sa.String(length=40), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("consumed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("correlation_id", sa.String(length=64), nullable=False),
    )
    op.create_index(
        "ux_schwab_oauth_states_state_hash",
        "schwab_oauth_states",
        ["state_hash"],
        unique=True,
    )
    op.create_index(
        "ix_schwab_oauth_states_status_expires",
        "schwab_oauth_states",
        ["status", "expires_at"],
    )
    op.create_index(
        "ix_schwab_oauth_states_correlation_id",
        "schwab_oauth_states",
        ["correlation_id"],
    )

    op.create_table(
        "schwab_tokens",
        sa.Column("id", sa.String(length=64), primary_key=True),
        sa.Column("product", sa.String(length=40), nullable=False),
        sa.Column("status", sa.String(length=40), nullable=False),
        sa.Column(
            "encrypted_access_token",
            sa.JSON().with_variant(postgresql.JSONB(), "postgresql"),
            nullable=False,
        ),
        sa.Column(
            "encrypted_refresh_token",
            sa.JSON().with_variant(postgresql.JSONB(), "postgresql"),
            nullable=False,
        ),
        sa.Column("token_type", sa.String(length=40), nullable=False),
        sa.Column("scope", sa.String(length=512), nullable=False),
        sa.Column("access_token_expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("refresh_token_expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("encryption_key_id", sa.String(length=64), nullable=False),
        sa.Column("issued_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("refreshed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_error_code", sa.String(length=120), nullable=True),
        sa.Column("last_error_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("correlation_id", sa.String(length=64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index(
        "ix_schwab_tokens_product_status",
        "schwab_tokens",
        ["product", "status"],
    )
    op.create_index(
        "ix_schwab_tokens_expires",
        "schwab_tokens",
        ["access_token_expires_at"],
    )
    op.create_index(
        "ix_schwab_tokens_correlation_id",
        "schwab_tokens",
        ["correlation_id"],
    )

    op.create_table(
        "schwab_market_data_syncs",
        sa.Column("id", sa.String(length=64), primary_key=True),
        sa.Column("sync_key", sa.String(length=160), nullable=False),
        sa.Column("data_kind", sa.String(length=40), nullable=False),
        sa.Column("status", sa.String(length=40), nullable=False),
        sa.Column("provider_state", sa.String(length=40), nullable=False),
        sa.Column("observed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "payload",
            sa.JSON().with_variant(postgresql.JSONB(), "postgresql"),
            nullable=False,
        ),
        sa.Column("correlation_id", sa.String(length=64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index(
        "ux_schwab_market_data_syncs_sync_key",
        "schwab_market_data_syncs",
        ["sync_key"],
        unique=True,
    )
    op.create_index(
        "ix_schwab_market_data_syncs_kind_status",
        "schwab_market_data_syncs",
        ["data_kind", "status"],
    )
    op.create_index(
        "ix_schwab_market_data_syncs_observed",
        "schwab_market_data_syncs",
        ["observed_at"],
    )
    op.create_index(
        "ix_schwab_market_data_syncs_correlation_id",
        "schwab_market_data_syncs",
        ["correlation_id"],
    )


def downgrade() -> None:
    op.drop_table("schwab_market_data_syncs")
    op.drop_table("schwab_tokens")
    op.drop_table("schwab_oauth_states")
