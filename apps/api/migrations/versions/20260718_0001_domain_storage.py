"""Create Milestone 1 domain storage.

Revision ID: 20260718_0001
Revises:
Create Date: 2026-07-18
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260718_0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _id_column() -> sa.Column[str]:
    return sa.Column("id", sa.String(length=64), primary_key=True)


def _correlation_column() -> sa.Column[str]:
    return sa.Column("correlation_id", sa.String(length=64), nullable=False)


def upgrade() -> None:
    op.create_table(
        "symbols",
        _id_column(),
        sa.Column("display_symbol", sa.String(length=40), nullable=False),
        sa.Column("instrument_type", sa.String(length=40), nullable=False),
        sa.Column("exchange", sa.String(length=80), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("first_observed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_observed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("metadata_payload", sa.JSON(), nullable=False),
        sa.Column("metadata_schema_version", sa.Integer(), nullable=False),
        _correlation_column(),
    )
    op.create_index("ix_symbols_display_symbol", "symbols", ["display_symbol"], unique=True)
    op.create_index("ix_symbols_correlation_id", "symbols", ["correlation_id"])

    op.create_table(
        "journal_events",
        _id_column(),
        _correlation_column(),
        sa.Column("event_type", sa.String(length=80), nullable=False),
        sa.Column("actor_type", sa.String(length=40), nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("recorded_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("subject_type", sa.String(length=80), nullable=False),
        sa.Column("subject_id", sa.String(length=64), nullable=False),
        sa.Column("causation_event_id", sa.String(length=64), nullable=True),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("schema_version", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(["causation_event_id"], ["journal_events.id"]),
    )
    op.create_index("ix_journal_events_correlation_id", "journal_events", ["correlation_id"])
    op.create_index("ix_journal_events_event_type", "journal_events", ["event_type"])
    op.create_index("ix_journal_events_occurred_at", "journal_events", ["occurred_at"])
    op.create_index("ix_journal_events_recorded_at", "journal_events", ["recorded_at"])
    op.create_index(
        "ix_journal_events_subject", "journal_events", ["subject_type", "subject_id"]
    )

    op.create_table(
        "configuration_versions",
        _id_column(),
        sa.Column("configuration_key", sa.String(length=120), nullable=False),
        sa.Column("version", sa.String(length=40), nullable=False),
        sa.Column("effective_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("retired_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("content_hash", sa.String(length=128), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("schema_version", sa.Integer(), nullable=False),
        sa.Column("creation_event_id", sa.String(length=64), nullable=False),
        _correlation_column(),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["creation_event_id"], ["journal_events.id"]),
        sa.UniqueConstraint(
            "configuration_key", "version", name="uq_configuration_key_version"
        ),
    )
    op.create_index(
        "ix_configuration_versions_configuration_key",
        "configuration_versions",
        ["configuration_key"],
    )
    op.create_index(
        "ix_configuration_versions_effective_at", "configuration_versions", ["effective_at"]
    )
    op.create_index(
        "ix_configuration_versions_correlation_id",
        "configuration_versions",
        ["correlation_id"],
    )
    op.create_index(
        "ix_configuration_versions_active",
        "configuration_versions",
        ["configuration_key", "retired_at"],
    )

    op.create_table(
        "instruments",
        _id_column(),
        sa.Column("symbol_id", sa.String(length=64), nullable=False),
        sa.Column("instrument_type", sa.String(length=40), nullable=False),
        sa.Column("exchange", sa.String(length=80), nullable=True),
        sa.Column("external_reference", sa.String(length=120), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("first_observed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_observed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("metadata_payload", sa.JSON(), nullable=False),
        sa.Column("metadata_schema_version", sa.Integer(), nullable=False),
        _correlation_column(),
        sa.ForeignKeyConstraint(["symbol_id"], ["symbols.id"]),
    )
    op.create_index("ix_instruments_symbol_id", "instruments", ["symbol_id"])
    op.create_index("ix_instruments_correlation_id", "instruments", ["correlation_id"])

    op.create_table(
        "market_data_snapshots",
        _id_column(),
        sa.Column("source", sa.String(length=80), nullable=False),
        sa.Column("symbol_id", sa.String(length=64), nullable=False),
        sa.Column("instrument_id", sa.String(length=64), nullable=True),
        sa.Column("observed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("ingested_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("session_date", sa.Date(), nullable=True),
        sa.Column("quality_state", sa.String(length=40), nullable=False),
        sa.Column("configuration_version_id", sa.String(length=64), nullable=True),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("payload_schema_version", sa.Integer(), nullable=False),
        _correlation_column(),
        sa.ForeignKeyConstraint(["symbol_id"], ["symbols.id"]),
        sa.ForeignKeyConstraint(["instrument_id"], ["instruments.id"]),
        sa.ForeignKeyConstraint(
            ["configuration_version_id"], ["configuration_versions.id"]
        ),
    )
    op.create_index(
        "ix_market_data_snapshots_observed_at", "market_data_snapshots", ["observed_at"]
    )
    op.create_index(
        "ix_market_data_snapshots_correlation_id",
        "market_data_snapshots",
        ["correlation_id"],
    )
    op.create_index(
        "ix_market_data_symbol_source_observed",
        "market_data_snapshots",
        ["symbol_id", "source", "observed_at"],
    )

    op.create_table(
        "signals",
        _id_column(),
        sa.Column("strategy_version", sa.String(length=80), nullable=False),
        sa.Column("symbol_id", sa.String(length=64), nullable=False),
        sa.Column("instrument_id", sa.String(length=64), nullable=True),
        sa.Column("direction", sa.String(length=20), nullable=True),
        sa.Column("score", sa.Numeric(12, 6), nullable=True),
        sa.Column("status", sa.String(length=40), nullable=True),
        sa.Column("input_snapshot_id", sa.String(length=64), nullable=False),
        sa.Column("explanation_payload", sa.JSON(), nullable=False),
        sa.Column("explanation_schema_version", sa.Integer(), nullable=False),
        _correlation_column(),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["symbol_id"], ["symbols.id"]),
        sa.ForeignKeyConstraint(["instrument_id"], ["instruments.id"]),
        sa.ForeignKeyConstraint(["input_snapshot_id"], ["market_data_snapshots.id"]),
    )
    op.create_index("ix_signals_symbol_id", "signals", ["symbol_id"])
    op.create_index("ix_signals_correlation_id", "signals", ["correlation_id"])

    op.create_table(
        "candidates",
        _id_column(),
        sa.Column("signal_id", sa.String(length=64), nullable=False),
        sa.Column("symbol_id", sa.String(length=64), nullable=False),
        sa.Column("instrument_id", sa.String(length=64), nullable=True),
        sa.Column("status", sa.String(length=40), nullable=False),
        sa.Column("score", sa.Numeric(12, 6), nullable=True),
        sa.Column("explanation_payload", sa.JSON(), nullable=False),
        sa.Column("explanation_schema_version", sa.Integer(), nullable=False),
        _correlation_column(),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["signal_id"], ["signals.id"]),
        sa.ForeignKeyConstraint(["symbol_id"], ["symbols.id"]),
        sa.ForeignKeyConstraint(["instrument_id"], ["instruments.id"]),
    )
    op.create_index("ix_candidates_signal_id", "candidates", ["signal_id"])
    op.create_index("ix_candidates_symbol_id", "candidates", ["symbol_id"])
    op.create_index("ix_candidates_correlation_id", "candidates", ["correlation_id"])

    op.create_table(
        "proposed_trades",
        _id_column(),
        sa.Column("candidate_id", sa.String(length=64), nullable=True),
        sa.Column("status", sa.String(length=40), nullable=False),
        sa.Column("order_intent_payload", sa.JSON(), nullable=False),
        sa.Column("payload_schema_version", sa.Integer(), nullable=False),
        sa.Column("broker_reference", sa.String(length=120), nullable=True),
        sa.Column("simulated_broker_reference", sa.String(length=120), nullable=True),
        _correlation_column(),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("terminal_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["candidate_id"], ["candidates.id"]),
    )
    op.create_index("ix_proposed_trades_candidate_id", "proposed_trades", ["candidate_id"])
    op.create_index(
        "ix_proposed_trades_correlation_id", "proposed_trades", ["correlation_id"]
    )

    op.create_table(
        "approvals",
        _id_column(),
        sa.Column("proposed_trade_id", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(length=40), nullable=False),
        sa.Column("actor_type", sa.String(length=40), nullable=False),
        sa.Column("decision_payload", sa.JSON(), nullable=False),
        sa.Column("payload_schema_version", sa.Integer(), nullable=False),
        _correlation_column(),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("terminal_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["proposed_trade_id"], ["proposed_trades.id"]),
    )
    op.create_index("ix_approvals_proposed_trade_id", "approvals", ["proposed_trade_id"])
    op.create_index("ix_approvals_correlation_id", "approvals", ["correlation_id"])

    op.create_table(
        "orders",
        _id_column(),
        sa.Column("proposed_trade_id", sa.String(length=64), nullable=True),
        sa.Column("approval_id", sa.String(length=64), nullable=True),
        sa.Column("status", sa.String(length=40), nullable=False),
        sa.Column("order_intent_payload", sa.JSON(), nullable=False),
        sa.Column("payload_schema_version", sa.Integer(), nullable=False),
        sa.Column("broker_reference", sa.String(length=120), nullable=True),
        sa.Column("simulated_broker_reference", sa.String(length=120), nullable=True),
        _correlation_column(),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("terminal_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["proposed_trade_id"], ["proposed_trades.id"]),
        sa.ForeignKeyConstraint(["approval_id"], ["approvals.id"]),
    )
    op.create_index("ix_orders_proposed_trade_id", "orders", ["proposed_trade_id"])
    op.create_index("ix_orders_correlation_id", "orders", ["correlation_id"])

    op.create_table(
        "fills",
        _id_column(),
        sa.Column("order_id", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(length=40), nullable=False),
        sa.Column("quantity", sa.Numeric(20, 8), nullable=False),
        sa.Column("price", sa.Numeric(20, 8), nullable=False),
        sa.Column("broker_reference", sa.String(length=120), nullable=True),
        sa.Column("simulated_broker_reference", sa.String(length=120), nullable=True),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("payload_schema_version", sa.Integer(), nullable=False),
        _correlation_column(),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["order_id"], ["orders.id"]),
    )
    op.create_index("ix_fills_order_id", "fills", ["order_id"])
    op.create_index("ix_fills_correlation_id", "fills", ["correlation_id"])

    op.create_table(
        "positions",
        _id_column(),
        sa.Column("symbol_id", sa.String(length=64), nullable=False),
        sa.Column("instrument_id", sa.String(length=64), nullable=True),
        sa.Column("status", sa.String(length=40), nullable=False),
        sa.Column("quantity", sa.Numeric(20, 8), nullable=False),
        sa.Column("average_price", sa.Numeric(20, 8), nullable=True),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("payload_schema_version", sa.Integer(), nullable=False),
        _correlation_column(),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("closed_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["symbol_id"], ["symbols.id"]),
        sa.ForeignKeyConstraint(["instrument_id"], ["instruments.id"]),
    )
    op.create_index("ix_positions_symbol_id", "positions", ["symbol_id"])
    op.create_index("ix_positions_correlation_id", "positions", ["correlation_id"])

    op.create_table(
        "risk_locks",
        _id_column(),
        sa.Column("lock_type", sa.String(length=80), nullable=False),
        sa.Column("status", sa.String(length=40), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("source_event_id", sa.String(length=64), nullable=True),
        sa.Column("activated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("cleared_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("clearing_event_id", sa.String(length=64), nullable=True),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("payload_schema_version", sa.Integer(), nullable=False),
        _correlation_column(),
        sa.ForeignKeyConstraint(["source_event_id"], ["journal_events.id"]),
        sa.ForeignKeyConstraint(["clearing_event_id"], ["journal_events.id"]),
    )
    op.create_index("ix_risk_locks_correlation_id", "risk_locks", ["correlation_id"])
    op.create_index("ix_risk_locks_active", "risk_locks", ["lock_type", "status"])

    if op.get_bind().dialect.name == "sqlite":
        op.execute(
            """
            CREATE TRIGGER journal_events_no_update
            BEFORE UPDATE ON journal_events
            BEGIN
              SELECT RAISE(ABORT, 'journal_events are append-only');
            END;
            """
        )
        op.execute(
            """
            CREATE TRIGGER journal_events_no_delete
            BEFORE DELETE ON journal_events
            BEGIN
              SELECT RAISE(ABORT, 'journal_events are append-only');
            END;
            """
        )


def downgrade() -> None:
    if op.get_bind().dialect.name == "sqlite":
        op.execute("DROP TRIGGER IF EXISTS journal_events_no_delete")
        op.execute("DROP TRIGGER IF EXISTS journal_events_no_update")

    op.drop_table("risk_locks")
    op.drop_table("positions")
    op.drop_table("fills")
    op.drop_table("orders")
    op.drop_table("approvals")
    op.drop_table("proposed_trades")
    op.drop_table("candidates")
    op.drop_table("signals")
    op.drop_table("market_data_snapshots")
    op.drop_table("instruments")
    op.drop_table("configuration_versions")
    op.drop_table("journal_events")
    op.drop_table("symbols")
