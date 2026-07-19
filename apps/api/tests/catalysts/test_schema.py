from pathlib import Path
from typing import Any, cast

import pytest
from alembic import command
from sqlalchemy import JSON, DateTime, Engine, Index, String, Table, create_engine, text
from sqlalchemy.dialects import postgresql, sqlite
from sqlalchemy.exc import IntegrityError
from sqlalchemy.schema import CreateIndex, CreateTable

from market_trader.db.migrations import alembic_config
from market_trader.db.models import (
    CatalystDecisionORM,
    CatalystObservationORM,
    CatalystQuarantineORM,
    CatalystSourceRunORM,
    CatalystSummaryORM,
)


def test_catalyst_tables_have_stable_keys_and_required_relationships() -> None:
    source_run = cast(Table, CatalystSourceRunORM.__table__)
    observation = cast(Table, CatalystObservationORM.__table__)
    quarantine = cast(Table, CatalystQuarantineORM.__table__)
    decision = cast(Table, CatalystDecisionORM.__table__)
    summary = cast(Table, CatalystSummaryORM.__table__)

    assert _index(source_run, "ux_catalyst_source_runs_run_key").unique
    assert _index(observation, "ux_catalyst_observations_observation_key").unique
    assert _index(observation, "ux_catalyst_observations_ingestion_key").unique
    assert _index(quarantine, "ux_catalyst_quarantine_ingestion_key").unique
    assert _index(decision, "ux_catalyst_decisions_decision_key").unique
    assert _index(summary, "ux_catalyst_summaries_summary_key").unique
    assert _foreign_key(observation, "source_run_id") == "catalyst_source_runs.id"
    assert _foreign_key(observation, "symbol_id") == "symbols.id"
    assert _foreign_key(quarantine, "source_run_id") == "catalyst_source_runs.id"
    assert _foreign_key(decision, "source_run_id") == "catalyst_source_runs.id"
    assert _foreign_key(decision, "symbol_id") == "symbols.id"
    assert _foreign_key(summary, "source_run_id") == "catalyst_source_runs.id"

    stable_keys = (
        source_run.c.run_key,
        observation.c.observation_key,
        observation.c.ingestion_key,
        observation.c.provider_event_id,
        quarantine.c.ingestion_key,
        decision.c.decision_key,
        summary.c.summary_key,
    )
    assert all(cast(String, column.type).length == 512 for column in stable_keys)
    assert {
        "capability",
        "request_digest",
        "source_policy_version",
    } <= set(source_run.c.keys())
    assert "quality_reasons" in observation.c


def test_catalyst_tables_index_source_symbol_and_as_of_access_paths() -> None:
    source_run = cast(Table, CatalystSourceRunORM.__table__)
    observation = cast(Table, CatalystObservationORM.__table__)
    quarantine = cast(Table, CatalystQuarantineORM.__table__)
    decision = cast(Table, CatalystDecisionORM.__table__)
    summary = cast(Table, CatalystSummaryORM.__table__)

    assert _index(source_run, "ix_catalyst_source_runs_source_as_of").columns.keys() == [
        "source_id",
        "as_of",
    ]
    assert _index(observation, "ix_catalyst_observations_source_published").columns.keys() == [
        "source_id",
        "published_at",
    ]
    assert _index(observation, "ix_catalyst_observations_symbol_published").columns.keys() == [
        "symbol_id",
        "published_at",
    ]
    assert _index(quarantine, "ix_catalyst_quarantine_source_ingested").columns.keys() == [
        "source_id",
        "ingested_at",
    ]
    assert _index(decision, "ix_catalyst_decisions_symbol_as_of").columns.keys() == [
        "symbol_id",
        "as_of",
    ]
    assert _index(summary, "ix_catalyst_summaries_generated_at").columns.keys() == [
        "generated_at"
    ]


def test_catalyst_temporal_columns_are_timezone_aware() -> None:
    tables = (
        cast(Table, CatalystSourceRunORM.__table__),
        cast(Table, CatalystObservationORM.__table__),
        cast(Table, CatalystQuarantineORM.__table__),
        cast(Table, CatalystDecisionORM.__table__),
        cast(Table, CatalystSummaryORM.__table__),
    )

    temporal_columns = (
        (tables[0], "as_of", "created_at"),
        (tables[1], "published_at", "ingested_at", "scheduled_for", "valid_until", "created_at"),
        (tables[2], "published_at", "ingested_at", "created_at"),
        (tables[3], "as_of", "created_at"),
        (tables[4], "generated_at", "created_at"),
    )
    assert all(
        isinstance(table.c[name].type, DateTime)
        and cast(DateTime, table.c[name].type).timezone
        for table, *names in temporal_columns
        for name in names
    )


@pytest.mark.parametrize(
    ("model", "column_name", "index_name"),
    (
        (CatalystSourceRunORM, "reasons", "ix_catalyst_source_runs_reasons"),
        (
            CatalystObservationORM,
            "quality_reasons",
            "ix_catalyst_observations_quality_reasons",
        ),
        (CatalystQuarantineORM, "reasons", "ix_catalyst_quarantine_reasons"),
        (CatalystDecisionORM, "reasons", "ix_catalyst_decisions_reasons"),
        (
            CatalystDecisionORM,
            "observation_keys",
            "ix_catalyst_decisions_observation_keys",
        ),
        (CatalystSummaryORM, "segments", "ix_catalyst_summaries_segments"),
    ),
)
def test_reason_and_lineage_payloads_use_jsonb_and_gin(
    model: Any, column_name: str, index_name: str
) -> None:
    table = cast(Table, model.__table__)

    assert isinstance(table.c[column_name].type.dialect_impl(sqlite.dialect()), JSON)
    assert "JSONB" in str(
        CreateTable(table).compile(dialect=postgresql.dialect())  # type: ignore[no-untyped-call]
    )
    assert "USING gin" in str(
        CreateIndex(_index(table, index_name)).compile(
            dialect=postgresql.dialect()  # type: ignore[no-untyped-call]
        )
    )


@pytest.mark.parametrize(
    ("table_name", "row_id"),
    (
        ("catalyst_observations", "obs-row"),
        ("catalyst_quarantine", "qua-row"),
        ("catalyst_decisions", "dec-row"),
        ("catalyst_summaries", "sum-row"),
    ),
)
def test_catalyst_outcomes_are_append_only(
    tmp_path: Path, table_name: str, row_id: str
) -> None:
    database_url = f"sqlite:///{tmp_path / f'{table_name}.db'}"
    command.upgrade(alembic_config(database_url), "head")
    engine = create_engine(database_url)
    try:
        _seed_catalyst_rows(engine)
        with pytest.raises(IntegrityError, match="append-only"), engine.begin() as connection:
            connection.execute(
                text(f"UPDATE {table_name} SET id = id WHERE id = :id"),
                {"id": row_id},
            )
        with pytest.raises(IntegrityError, match="append-only"), engine.begin() as connection:
            connection.execute(text(f"DELETE FROM {table_name} WHERE id = :id"), {"id": row_id})
    finally:
        engine.dispose()


def _seed_catalyst_rows(engine: Engine) -> None:
    with engine.begin() as connection:
        connection.execute(
            text(
                "INSERT INTO catalyst_source_runs "
                "(id, run_key, source_id, capability, request_digest, "
                "source_policy_version, as_of, state, policy_versions, policy_hashes, "
                "result_counts, reasons, result_digest, correlation_id, created_at) VALUES "
                "('run-row', 'run-key', 'fixture', 'fixture_replay', :digest, "
                "'catalyst-source-policy-v1', '2026-07-17 15:30:00', 'available', "
                "'{}', '{}', '{}', '[]', :digest, 'corr', '2026-07-17 15:30:00')"
            ),
            {"digest": "a" * 64},
        )
        connection.execute(
            text(
                "INSERT INTO catalyst_observations "
                "(id, observation_key, source_run_id, ingestion_key, authoritative_digest, "
                "external_text_digest, source_id, authority_class, event_family, event_category, "
                "provider_event_id, source_reference, symbol_id, published_at, ingested_at, "
                "scheduled_for, valid_until, structured_facts, external_text, "
                "quality_reasons, "
                "source_schema_version, "
                "normalization_schema_version, configuration_version, correlation_id, created_at) "
                "VALUES ('obs-row', 'obs-key', 'run-row', 'ing-key', :digest, :digest, 'fixture', "
                "'authorized_structured', 'company_news', 'regulatory_approval', 'event-key', "
                "'fixture://event', NULL, '2026-07-17 15:30:00', '2026-07-17 15:30:00', NULL, "
                "'2026-07-18 15:30:00', '{}', '{}', '[]', 1, 1, 'source-v1', 'corr', "
                "'2026-07-17 15:30:00')"
            ),
            {"digest": "b" * 64},
        )
        connection.execute(
            text(
                "INSERT INTO catalyst_quarantine "
                "(id, source_run_id, ingestion_key, sanitized_payload_digest, source_id, "
                "provider_event_id, published_at, ingested_at, reasons, sanitized_payload, "
                "source_schema_version, normalization_schema_version, correlation_id, created_at) "
                "VALUES ('qua-row', 'run-row', 'qua-key', :digest, 'fixture', 'bad-event', NULL, "
                "'2026-07-17 15:30:00', '[]', '{}', 1, 1, 'corr', '2026-07-17 15:30:00')"
            ),
            {"digest": "c" * 64},
        )
        connection.execute(
            text(
                "INSERT INTO catalyst_decisions "
                "(id, decision_key, source_run_id, scope, symbol_id, as_of, materiality, "
                "direction, confirmation, risk_state, reasons, observation_keys, policy_versions, "
                "input_digest, "
                "explanation, correlation_id, created_at) VALUES "
                "('dec-row', 'dec-key', 'run-row', 'market', NULL, '2026-07-17 15:30:00', "
                "'material', 'positive', 'confirmed', 'clear', '[]', '[]', '{}', :digest, '{}', "
                "'corr', '2026-07-17 15:30:00')"
            ),
            {"digest": "d" * 64},
        )
        connection.execute(
            text(
                "INSERT INTO catalyst_summaries "
                "(id, summary_key, source_run_id, provider_id, generated_at, segments, "
                "policy_version, content_digest, correlation_id, created_at) VALUES "
                "('sum-row', 'sum-key', 'run-row', 'recorded-summary-v1', "
                "'2026-07-17 15:30:00', '[]', 'summary-v1', :digest, 'corr', "
                "'2026-07-17 15:30:00')"
            ),
            {"digest": "e" * 64},
        )


def _index(table: Table, name: str) -> Index:
    return next(index for index in table.indexes if index.name == name)


def _foreign_key(table: Table, column_name: str) -> str:
    return str(next(iter(table.c[column_name].foreign_keys)).target_fullname)
