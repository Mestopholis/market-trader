from datetime import date, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import (
    JSON,
    Boolean,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Numeric,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from market_trader.db.base import Base


class SymbolORM(Base):
    __tablename__ = "symbols"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    display_symbol: Mapped[str] = mapped_column(String(40), unique=True, index=True)
    instrument_type: Mapped[str] = mapped_column(String(40))
    exchange: Mapped[str | None] = mapped_column(String(80))
    is_active: Mapped[bool] = mapped_column(Boolean)
    first_observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    last_observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    metadata_payload: Mapped[dict[str, Any]] = mapped_column(JSON)
    metadata_schema_version: Mapped[int]
    correlation_id: Mapped[str] = mapped_column(String(64), index=True)


class JournalEventORM(Base):
    __tablename__ = "journal_events"
    __table_args__ = (Index("ix_journal_events_subject", "subject_type", "subject_id"),)

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    correlation_id: Mapped[str] = mapped_column(String(64), index=True)
    event_type: Mapped[str] = mapped_column(String(80), index=True)
    actor_type: Mapped[str] = mapped_column(String(40))
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    recorded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    subject_type: Mapped[str] = mapped_column(String(80))
    subject_id: Mapped[str] = mapped_column(String(64))
    causation_event_id: Mapped[str | None] = mapped_column(
        ForeignKey("journal_events.id"), nullable=True
    )
    payload: Mapped[dict[str, Any]] = mapped_column(JSON)
    schema_version: Mapped[int]


class ConfigurationVersionORM(Base):
    __tablename__ = "configuration_versions"
    __table_args__ = (
        UniqueConstraint("configuration_key", "version", name="uq_configuration_key_version"),
        Index("ix_configuration_versions_active", "configuration_key", "retired_at"),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    configuration_key: Mapped[str] = mapped_column(String(120), index=True)
    version: Mapped[str] = mapped_column(String(40))
    effective_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    retired_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    content_hash: Mapped[str] = mapped_column(String(128))
    payload: Mapped[dict[str, Any]] = mapped_column(JSON)
    schema_version: Mapped[int]
    creation_event_id: Mapped[str] = mapped_column(ForeignKey("journal_events.id"))
    correlation_id: Mapped[str] = mapped_column(String(64), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class InstrumentORM(Base):
    __tablename__ = "instruments"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    symbol_id: Mapped[str] = mapped_column(ForeignKey("symbols.id"), index=True)
    instrument_type: Mapped[str] = mapped_column(String(40))
    exchange: Mapped[str | None] = mapped_column(String(80))
    external_reference: Mapped[str | None] = mapped_column(String(120))
    is_active: Mapped[bool] = mapped_column(Boolean)
    first_observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    last_observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    metadata_payload: Mapped[dict[str, Any]] = mapped_column(JSON)
    metadata_schema_version: Mapped[int]
    correlation_id: Mapped[str] = mapped_column(String(64), index=True)


class MarketDataSnapshotORM(Base):
    __tablename__ = "market_data_snapshots"
    __table_args__ = (
        Index(
            "ix_market_data_symbol_source_observed",
            "symbol_id",
            "source",
            "observed_at",
        ),
        Index("ux_market_data_snapshot_ingestion_key", "ingestion_key", unique=True),
        Index(
            "ix_market_data_source_kind_ingested",
            "source",
            "data_kind",
            "ingested_at",
        ),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    ingestion_key: Mapped[str] = mapped_column(String(80))
    payload_digest: Mapped[str] = mapped_column(String(64))
    source: Mapped[str] = mapped_column(String(80))
    data_kind: Mapped[str] = mapped_column(String(40))
    symbol_id: Mapped[str] = mapped_column(ForeignKey("symbols.id"))
    instrument_id: Mapped[str | None] = mapped_column(ForeignKey("instruments.id"))
    observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    ingested_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    session_date: Mapped[date | None] = mapped_column(Date)
    quality_state: Mapped[str] = mapped_column(String(40))
    configuration_version_id: Mapped[str | None] = mapped_column(
        ForeignKey("configuration_versions.id")
    )
    payload: Mapped[dict[str, Any]] = mapped_column(JSON)
    payload_schema_version: Mapped[int]
    correlation_id: Mapped[str] = mapped_column(String(64), index=True)


class MarketDataQuarantineORM(Base):
    __tablename__ = "market_data_quarantine"
    __table_args__ = (
        Index("ux_market_data_quarantine_ingestion_key", "ingestion_key", unique=True),
        Index(
            "ix_market_data_quarantine_identity_ingested",
            "source",
            "data_kind",
            "symbol_identity",
            "ingested_at",
        ),
        Index(
            "ix_market_data_quarantine_reason_codes",
            "reason_codes",
            postgresql_using="gin",
        ),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    ingestion_key: Mapped[str] = mapped_column(String(80))
    source: Mapped[str] = mapped_column(String(80))
    event_id: Mapped[str] = mapped_column(String(120))
    data_kind: Mapped[str] = mapped_column(String(40))
    observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    ingested_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    symbol_identity: Mapped[str | None] = mapped_column(String(80), nullable=True)
    instrument_identity: Mapped[str | None] = mapped_column(String(160), nullable=True)
    sanitized_payload: Mapped[dict[str, Any]] = mapped_column(JSON)
    payload_digest: Mapped[str] = mapped_column(String(64))
    reason_codes: Mapped[list[str]] = mapped_column(JSON().with_variant(JSONB(), "postgresql"))
    fixture_schema_version: Mapped[int]
    normalized_schema_version: Mapped[int | None] = mapped_column(nullable=True)
    configuration_version: Mapped[str] = mapped_column(String(80))
    correlation_id: Mapped[str] = mapped_column(String(64), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class CatalystSourceRunORM(Base):
    __tablename__ = "catalyst_source_runs"
    __table_args__ = (
        Index("ux_catalyst_source_runs_run_key", "run_key", unique=True),
        Index("ix_catalyst_source_runs_source_as_of", "source_id", "as_of"),
        Index("ix_catalyst_source_runs_state", "state"),
        Index(
            "ix_catalyst_source_runs_reasons",
            "reasons",
            postgresql_using="gin",
        ),
        Index("ix_catalyst_source_runs_correlation_id", "correlation_id"),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    run_key: Mapped[str] = mapped_column(String(512))
    source_id: Mapped[str] = mapped_column(String(128))
    as_of: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    state: Mapped[str] = mapped_column(String(40))
    policy_versions: Mapped[dict[str, Any]] = mapped_column(JSON)
    policy_hashes: Mapped[dict[str, Any]] = mapped_column(JSON)
    result_counts: Mapped[dict[str, Any]] = mapped_column(JSON)
    reasons: Mapped[list[str]] = mapped_column(JSON().with_variant(JSONB(), "postgresql"))
    result_digest: Mapped[str] = mapped_column(String(64))
    correlation_id: Mapped[str] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class CatalystObservationORM(Base):
    __tablename__ = "catalyst_observations"
    __table_args__ = (
        Index("ux_catalyst_observations_observation_key", "observation_key", unique=True),
        Index("ux_catalyst_observations_ingestion_key", "ingestion_key", unique=True),
        Index(
            "ix_catalyst_observations_source_published",
            "source_id",
            "published_at",
        ),
        Index(
            "ix_catalyst_observations_symbol_published",
            "symbol_id",
            "published_at",
        ),
        Index(
            "ix_catalyst_observations_family_category",
            "event_family",
            "event_category",
        ),
        Index("ix_catalyst_observations_correlation_id", "correlation_id"),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    observation_key: Mapped[str] = mapped_column(String(512))
    source_run_id: Mapped[str] = mapped_column(ForeignKey("catalyst_source_runs.id"))
    ingestion_key: Mapped[str] = mapped_column(String(512))
    authoritative_digest: Mapped[str] = mapped_column(String(64))
    external_text_digest: Mapped[str] = mapped_column(String(64))
    source_id: Mapped[str] = mapped_column(String(128))
    authority_class: Mapped[str] = mapped_column(String(40))
    event_family: Mapped[str] = mapped_column(String(40))
    event_category: Mapped[str] = mapped_column(String(128))
    provider_event_id: Mapped[str] = mapped_column(String(512))
    source_reference: Mapped[str] = mapped_column(String(2048))
    symbol_id: Mapped[str | None] = mapped_column(ForeignKey("symbols.id"), nullable=True)
    published_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    ingested_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    scheduled_for: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    valid_until: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    structured_facts: Mapped[dict[str, Any]] = mapped_column(JSON)
    external_text: Mapped[dict[str, Any]] = mapped_column(JSON)
    source_schema_version: Mapped[int]
    normalization_schema_version: Mapped[int]
    configuration_version: Mapped[str] = mapped_column(String(128))
    correlation_id: Mapped[str] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class CatalystQuarantineORM(Base):
    __tablename__ = "catalyst_quarantine"
    __table_args__ = (
        Index("ux_catalyst_quarantine_ingestion_key", "ingestion_key", unique=True),
        Index("ix_catalyst_quarantine_source_ingested", "source_id", "ingested_at"),
        Index(
            "ix_catalyst_quarantine_reasons",
            "reasons",
            postgresql_using="gin",
        ),
        Index("ix_catalyst_quarantine_correlation_id", "correlation_id"),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    source_run_id: Mapped[str] = mapped_column(ForeignKey("catalyst_source_runs.id"))
    ingestion_key: Mapped[str] = mapped_column(String(512))
    sanitized_payload_digest: Mapped[str] = mapped_column(String(64))
    source_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    provider_event_id: Mapped[str | None] = mapped_column(String(512), nullable=True)
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    ingested_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    reasons: Mapped[list[str]] = mapped_column(JSON().with_variant(JSONB(), "postgresql"))
    sanitized_payload: Mapped[dict[str, Any]] = mapped_column(JSON)
    source_schema_version: Mapped[int | None] = mapped_column(nullable=True)
    normalization_schema_version: Mapped[int | None] = mapped_column(nullable=True)
    correlation_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class CatalystDecisionORM(Base):
    __tablename__ = "catalyst_decisions"
    __table_args__ = (
        Index("ux_catalyst_decisions_decision_key", "decision_key", unique=True),
        Index("ix_catalyst_decisions_source_run_id", "source_run_id"),
        Index("ix_catalyst_decisions_symbol_as_of", "symbol_id", "as_of"),
        Index("ix_catalyst_decisions_as_of", "as_of"),
        Index(
            "ix_catalyst_decisions_reasons",
            "reasons",
            postgresql_using="gin",
        ),
        Index(
            "ix_catalyst_decisions_observation_keys",
            "observation_keys",
            postgresql_using="gin",
        ),
        Index("ix_catalyst_decisions_correlation_id", "correlation_id"),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    decision_key: Mapped[str] = mapped_column(String(512))
    source_run_id: Mapped[str] = mapped_column(ForeignKey("catalyst_source_runs.id"))
    scope: Mapped[str] = mapped_column(String(40))
    symbol_id: Mapped[str | None] = mapped_column(ForeignKey("symbols.id"), nullable=True)
    as_of: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    materiality: Mapped[str] = mapped_column(String(40))
    direction: Mapped[str] = mapped_column(String(40))
    confirmation: Mapped[str] = mapped_column(String(40))
    risk_state: Mapped[str] = mapped_column(String(40))
    reasons: Mapped[list[str]] = mapped_column(JSON().with_variant(JSONB(), "postgresql"))
    observation_keys: Mapped[list[str]] = mapped_column(
        JSON().with_variant(JSONB(), "postgresql")
    )
    policy_versions: Mapped[dict[str, Any]] = mapped_column(JSON)
    input_digest: Mapped[str] = mapped_column(String(64))
    explanation: Mapped[dict[str, Any]] = mapped_column(JSON)
    correlation_id: Mapped[str] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class CatalystSummaryORM(Base):
    __tablename__ = "catalyst_summaries"
    __table_args__ = (
        Index("ux_catalyst_summaries_summary_key", "summary_key", unique=True),
        Index("ix_catalyst_summaries_source_run_id", "source_run_id"),
        Index("ix_catalyst_summaries_generated_at", "generated_at"),
        Index(
            "ix_catalyst_summaries_segments",
            "segments",
            postgresql_using="gin",
        ),
        Index("ix_catalyst_summaries_correlation_id", "correlation_id"),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    summary_key: Mapped[str] = mapped_column(String(512))
    source_run_id: Mapped[str] = mapped_column(ForeignKey("catalyst_source_runs.id"))
    provider_id: Mapped[str] = mapped_column(String(128))
    generated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    segments: Mapped[list[dict[str, Any]]] = mapped_column(
        JSON().with_variant(JSONB(), "postgresql")
    )
    policy_version: Mapped[str] = mapped_column(String(128))
    content_digest: Mapped[str] = mapped_column(String(64))
    correlation_id: Mapped[str] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class ScannerRunORM(Base):
    __tablename__ = "scanner_runs"
    __table_args__ = (
        Index("ux_scanner_runs_run_key", "run_key", unique=True),
        Index("ix_scanner_runs_session_date", "session_date"),
        Index("ix_scanner_runs_status", "status"),
        Index("ix_scanner_runs_correlation_id", "correlation_id"),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    run_key: Mapped[str] = mapped_column(String(512))
    as_of: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    session_date: Mapped[date] = mapped_column(Date)
    input_digest: Mapped[str] = mapped_column(String(64))
    universe_version: Mapped[str] = mapped_column(String(80))
    universe_content_hash: Mapped[str] = mapped_column(String(64))
    policy_versions: Mapped[dict[str, Any]] = mapped_column(JSON)
    regime_state: Mapped[str] = mapped_column(String(40))
    regime_score: Mapped[Decimal] = mapped_column(Numeric(12, 6))
    regime_explanation: Mapped[dict[str, Any]] = mapped_column(JSON)
    result_counts: Mapped[dict[str, Any]] = mapped_column(JSON)
    result_digest: Mapped[str] = mapped_column(String(64))
    status: Mapped[str] = mapped_column(String(40))
    correlation_id: Mapped[str] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class EligibilityDecisionORM(Base):
    __tablename__ = "eligibility_decisions"
    __table_args__ = (
        UniqueConstraint(
            "scanner_run_id",
            "symbol_id",
            name="uq_eligibility_decisions_run_symbol",
        ),
        Index("ux_eligibility_decisions_decision_key", "decision_key", unique=True),
        Index("ix_eligibility_decisions_scanner_run_id", "scanner_run_id"),
        Index("ix_eligibility_decisions_symbol_id", "symbol_id"),
        Index("ix_eligibility_decisions_status", "status"),
        Index(
            "ix_eligibility_decisions_reason_codes",
            "reason_codes",
            postgresql_using="gin",
        ),
        Index("ix_eligibility_decisions_correlation_id", "correlation_id"),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    decision_key: Mapped[str] = mapped_column(String(512))
    scanner_run_id: Mapped[str] = mapped_column(ForeignKey("scanner_runs.id"))
    symbol_id: Mapped[str] = mapped_column(ForeignKey("symbols.id"))
    status: Mapped[str] = mapped_column(String(40))
    reason_codes: Mapped[list[str]] = mapped_column(JSON().with_variant(JSONB(), "postgresql"))
    observed_payload: Mapped[dict[str, Any]] = mapped_column(JSON)
    input_digest: Mapped[str] = mapped_column(String(64))
    policy_version: Mapped[str] = mapped_column(String(80))
    correlation_id: Mapped[str] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class SignalORM(Base):
    __tablename__ = "signals"
    __table_args__ = (
        Index("ux_signals_signal_key", "signal_key", unique=True),
        Index("ix_signals_scanner_run_id", "scanner_run_id"),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    signal_key: Mapped[str | None] = mapped_column(String(512), nullable=True)
    scanner_run_id: Mapped[str | None] = mapped_column(
        ForeignKey("scanner_runs.id", name="fk_signals_scanner_run_id"), nullable=True
    )
    strategy_id: Mapped[str | None] = mapped_column(String(80), nullable=True)
    strategy_version: Mapped[str] = mapped_column(String(80))
    symbol_id: Mapped[str] = mapped_column(ForeignKey("symbols.id"), index=True)
    instrument_id: Mapped[str | None] = mapped_column(ForeignKey("instruments.id"))
    direction: Mapped[str | None] = mapped_column(String(20))
    score: Mapped[Decimal | None] = mapped_column(Numeric(12, 6))
    status: Mapped[str | None] = mapped_column(String(40))
    input_snapshot_id: Mapped[str] = mapped_column(ForeignKey("market_data_snapshots.id"))
    input_digest: Mapped[str | None] = mapped_column(String(64), nullable=True)
    reason_codes: Mapped[list[str] | None] = mapped_column(
        JSON().with_variant(JSONB(), "postgresql"), nullable=True
    )
    gate_payload: Mapped[list[dict[str, Any]] | None] = mapped_column(JSON, nullable=True)
    component_score_payload: Mapped[list[dict[str, Any]] | None] = mapped_column(
        JSON, nullable=True
    )
    scoring_policy_version: Mapped[str | None] = mapped_column(String(80), nullable=True)
    explanation_payload: Mapped[dict[str, Any]] = mapped_column(JSON)
    explanation_schema_version: Mapped[int]
    correlation_id: Mapped[str] = mapped_column(String(64), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class CandidateORM(Base):
    __tablename__ = "candidates"
    __table_args__ = (
        Index("ux_candidates_candidate_key", "candidate_key", unique=True),
        Index("ix_candidates_scanner_run_id", "scanner_run_id"),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    candidate_key: Mapped[str | None] = mapped_column(String(512), nullable=True)
    scanner_run_id: Mapped[str | None] = mapped_column(
        ForeignKey("scanner_runs.id", name="fk_candidates_scanner_run_id"), nullable=True
    )
    strategy_id: Mapped[str | None] = mapped_column(String(80), nullable=True)
    signal_id: Mapped[str] = mapped_column(ForeignKey("signals.id"), index=True)
    symbol_id: Mapped[str] = mapped_column(ForeignKey("symbols.id"), index=True)
    instrument_id: Mapped[str | None] = mapped_column(ForeignKey("instruments.id"))
    direction: Mapped[str | None] = mapped_column(String(20), nullable=True)
    status: Mapped[str] = mapped_column(String(40))
    score: Mapped[Decimal | None] = mapped_column(Numeric(12, 6))
    input_digest: Mapped[str | None] = mapped_column(String(64), nullable=True)
    scoring_policy_version: Mapped[str | None] = mapped_column(String(80), nullable=True)
    explanation_payload: Mapped[dict[str, Any]] = mapped_column(JSON)
    explanation_schema_version: Mapped[int]
    correlation_id: Mapped[str] = mapped_column(String(64), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class ProposedTradeORM(Base):
    __tablename__ = "proposed_trades"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    candidate_id: Mapped[str | None] = mapped_column(ForeignKey("candidates.id"), index=True)
    status: Mapped[str] = mapped_column(String(40))
    order_intent_payload: Mapped[dict[str, Any]] = mapped_column(JSON)
    payload_schema_version: Mapped[int]
    broker_reference: Mapped[str | None] = mapped_column(String(120))
    simulated_broker_reference: Mapped[str | None] = mapped_column(String(120))
    correlation_id: Mapped[str] = mapped_column(String(64), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    terminal_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class ApprovalORM(Base):
    __tablename__ = "approvals"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    proposed_trade_id: Mapped[str] = mapped_column(ForeignKey("proposed_trades.id"), index=True)
    status: Mapped[str] = mapped_column(String(40))
    actor_type: Mapped[str] = mapped_column(String(40))
    decision_payload: Mapped[dict[str, Any]] = mapped_column(JSON)
    payload_schema_version: Mapped[int]
    correlation_id: Mapped[str] = mapped_column(String(64), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    terminal_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class OrderORM(Base):
    __tablename__ = "orders"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    proposed_trade_id: Mapped[str | None] = mapped_column(
        ForeignKey("proposed_trades.id"), index=True
    )
    approval_id: Mapped[str | None] = mapped_column(ForeignKey("approvals.id"))
    status: Mapped[str] = mapped_column(String(40))
    order_intent_payload: Mapped[dict[str, Any]] = mapped_column(JSON)
    payload_schema_version: Mapped[int]
    broker_reference: Mapped[str | None] = mapped_column(String(120))
    simulated_broker_reference: Mapped[str | None] = mapped_column(String(120))
    correlation_id: Mapped[str] = mapped_column(String(64), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    terminal_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class FillORM(Base):
    __tablename__ = "fills"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    order_id: Mapped[str] = mapped_column(ForeignKey("orders.id"), index=True)
    status: Mapped[str] = mapped_column(String(40))
    quantity: Mapped[Decimal] = mapped_column(Numeric(20, 8))
    price: Mapped[Decimal] = mapped_column(Numeric(20, 8))
    broker_reference: Mapped[str | None] = mapped_column(String(120))
    simulated_broker_reference: Mapped[str | None] = mapped_column(String(120))
    payload: Mapped[dict[str, Any]] = mapped_column(JSON)
    payload_schema_version: Mapped[int]
    correlation_id: Mapped[str] = mapped_column(String(64), index=True)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class PositionORM(Base):
    __tablename__ = "positions"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    symbol_id: Mapped[str] = mapped_column(ForeignKey("symbols.id"), index=True)
    instrument_id: Mapped[str | None] = mapped_column(ForeignKey("instruments.id"))
    status: Mapped[str] = mapped_column(String(40))
    quantity: Mapped[Decimal] = mapped_column(Numeric(20, 8))
    average_price: Mapped[Decimal | None] = mapped_column(Numeric(20, 8))
    payload: Mapped[dict[str, Any]] = mapped_column(JSON)
    payload_schema_version: Mapped[int]
    correlation_id: Mapped[str] = mapped_column(String(64), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class RiskLockORM(Base):
    __tablename__ = "risk_locks"
    __table_args__ = (Index("ix_risk_locks_active", "lock_type", "status"),)

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    lock_type: Mapped[str] = mapped_column(String(80))
    status: Mapped[str] = mapped_column(String(40))
    reason: Mapped[str] = mapped_column(Text)
    source_event_id: Mapped[str | None] = mapped_column(ForeignKey("journal_events.id"))
    activated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    cleared_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    clearing_event_id: Mapped[str | None] = mapped_column(ForeignKey("journal_events.id"))
    payload: Mapped[dict[str, Any]] = mapped_column(JSON)
    payload_schema_version: Mapped[int]
    correlation_id: Mapped[str] = mapped_column(String(64), index=True)
