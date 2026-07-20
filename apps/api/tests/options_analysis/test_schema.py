# ruff: noqa: E501

from pathlib import Path
from typing import Any, cast

import pytest
from alembic import command
from sqlalchemy import JSON, Engine, Index, String, Table, create_engine, text
from sqlalchemy.dialects import postgresql, sqlite
from sqlalchemy.exc import IntegrityError
from sqlalchemy.schema import CreateIndex, CreateTable

from market_trader.db.migrations import alembic_config
from market_trader.db.models import (
    OptionContractEvaluationORM,
    OptionsAnalysisRunORM,
    OptionSpreadCandidateORM,
    OptionSpreadWarningORM,
)


def test_options_analysis_schema_has_stable_keys_authoritative_lineage_and_payloads() -> None:
    run = cast(Table, OptionsAnalysisRunORM.__table__)
    evaluation = cast(Table, OptionContractEvaluationORM.__table__)
    spread = cast(Table, OptionSpreadCandidateORM.__table__)
    warning = cast(Table, OptionSpreadWarningORM.__table__)

    assert _index(run, "ux_options_analysis_runs_run_key").unique
    assert _index(evaluation, "ux_option_contract_evaluations_evaluation_key").unique
    assert _index(spread, "ux_option_spread_candidates_spread_key").unique
    assert _index(warning, "ux_option_spread_warnings_warning_key").unique
    assert {
        "scanner_run_id",
        "candidate_id",
        "symbol_id",
        "result_digest",
        "policy_version",
        "policy_hash",
        "input_digest",
        "result_counts",
        "reason_summary",
    } <= set(run.c.keys())
    assert _foreign_key(run, "scanner_run_id") == "scanner_runs.id"
    assert _foreign_key(run, "candidate_id") == "candidates.id"
    assert _foreign_key(run, "symbol_id") == "symbols.id"
    assert _foreign_key(evaluation, "run_id") == "options_analysis_runs.id"
    assert _foreign_key(spread, "run_id") == "options_analysis_runs.id"
    assert _foreign_key(warning, "spread_id") == "option_spread_candidates.id"
    assert all(
        cast(String, column.type).length == 512
        for column in (
            run.c.run_key,
            evaluation.c.evaluation_key,
            spread.c.spread_key,
            warning.c.warning_key,
        )
    )


@pytest.mark.parametrize(
    ("model", "column_name", "index_name"),
    (
        (OptionsAnalysisRunORM, "reason_summary", "ix_options_analysis_runs_reason_summary"),
        (OptionContractEvaluationORM, "reasons", "ix_option_contract_evaluations_reasons"),
        (OptionSpreadCandidateORM, "calculations", "ix_option_spread_candidates_calculations"),
        (OptionSpreadWarningORM, "facts", "ix_option_spread_warnings_facts"),
    ),
)
def test_options_analysis_payloads_use_jsonb_and_gin(
    model: Any, column_name: str, index_name: str
) -> None:
    table = cast(Table, model.__table__)

    assert "JSONB" in str(
        CreateTable(table).compile(dialect=postgresql.dialect())  # type: ignore[no-untyped-call]
    )
    assert isinstance(table.c[column_name].type.dialect_impl(sqlite.dialect()), JSON)
    assert "USING gin" in str(
        CreateIndex(_index(table, index_name)).compile(
            dialect=postgresql.dialect()  # type: ignore[no-untyped-call]
        )
    )


def test_options_analysis_migration_creates_append_only_tables_at_head(tmp_path: Path) -> None:
    database_url = f"sqlite:///{tmp_path / 'options-analysis.db'}"
    command.upgrade(alembic_config(database_url), "head")
    engine = create_engine(database_url)
    try:
        with engine.connect() as connection:
            tables = set(engine.dialect.get_table_names(connection))
        assert {
            "options_analysis_runs",
            "option_contract_evaluations",
            "option_spread_candidates",
            "option_spread_warnings",
        } <= tables
        _seed_options_analysis_rows(engine)
        for table_name, row_id in (
            ("options_analysis_runs", "run-row"),
            ("option_contract_evaluations", "evaluation-row"),
            ("option_spread_candidates", "spread-row"),
            ("option_spread_warnings", "warning-row"),
        ):
            with pytest.raises(IntegrityError, match="append-only"), engine.begin() as connection:
                connection.execute(
                    text(f"UPDATE {table_name} SET id = id WHERE id = :id"), {"id": row_id}
                )
            with pytest.raises(IntegrityError, match="append-only"), engine.begin() as connection:
                connection.execute(text(f"DELETE FROM {table_name} WHERE id = :id"), {"id": row_id})
    finally:
        engine.dispose()


def test_options_analysis_migration_source_defines_all_append_only_triggers() -> None:
    migration = Path("migrations/versions/20260719_0005_options_analysis.py").read_text()
    assert "20260719_0005" in migration
    for table in (
        "options_analysis_runs",
        "option_contract_evaluations",
        "option_spread_candidates",
        "option_spread_warnings",
    ):
        assert table in migration


def _index(table: Table, name: str) -> Index:
    return next(index for index in table.indexes if index.name == name)


def _foreign_key(table: Table, column: str) -> str:
    return str(next(iter(table.c[column].foreign_keys)).target_fullname)


def _seed_options_analysis_rows(engine: Engine) -> None:
    with engine.begin() as connection:
        connection.execute(
            text(
                "INSERT INTO symbols (id, display_symbol, instrument_type, exchange, is_active, first_observed_at, last_observed_at, metadata_payload, metadata_schema_version, correlation_id) VALUES ('symbol-row', 'SPY', 'equity', 'ARCX', 1, '2026-07-19 15:30:00', '2026-07-19 15:30:00', '{}', 1, 'corr')"
            )
        )
        connection.execute(
            text(
                "INSERT INTO scanner_runs (id, run_key, as_of, session_date, input_digest, universe_version, universe_content_hash, policy_versions, regime_state, regime_score, regime_explanation, result_counts, result_digest, status, correlation_id, created_at) VALUES ('scanner-row', 'scanner-key', '2026-07-19 15:30:00', '2026-07-19', :digest, 'v1', :digest, '{}', 'neutral', 0, '{}', '{}', :digest, 'complete', 'corr', '2026-07-19 15:30:00')"
            ),
            {"digest": "a" * 64},
        )
        connection.execute(
            text(
                "INSERT INTO market_data_snapshots (id, ingestion_key, payload_digest, source, data_kind, symbol_id, instrument_id, observed_at, ingested_at, session_date, quality_state, configuration_version_id, payload, payload_schema_version, correlation_id) VALUES ('snapshot-row', 'fixture:SPY', :digest, 'fixture', 'quote', 'symbol-row', NULL, '2026-07-19 15:30:00', '2026-07-19 15:30:00', '2026-07-19', 'valid', NULL, '{}', 1, 'corr')"
            ),
            {"digest": "a" * 64},
        )
        connection.execute(
            text(
                "INSERT INTO signals (id, signal_key, scanner_run_id, strategy_id, strategy_version, symbol_id, instrument_id, direction, score, status, input_snapshot_id, input_digest, reason_codes, gate_payload, component_score_payload, scoring_policy_version, explanation_payload, explanation_schema_version, correlation_id, created_at) VALUES ('signal-row', 'signal-key', 'scanner-row', 'strategy', 'v1', 'symbol-row', NULL, 'bullish', 1, 'qualified', 'snapshot-row', :digest, '[]', '[]', '[]', 'v1', '{}', 1, 'corr', '2026-07-19 15:30:00')"
            ),
            {"digest": "a" * 64},
        )
        connection.execute(
            text(
                "INSERT INTO candidates (id, candidate_key, scanner_run_id, strategy_id, signal_id, symbol_id, instrument_id, direction, status, score, input_digest, scoring_policy_version, explanation_payload, explanation_schema_version, correlation_id, created_at) VALUES ('candidate-row', 'candidate-key', 'scanner-row', 'strategy', 'signal-row', 'symbol-row', NULL, 'bullish', 'qualified', 1, :digest, 'v1', '{}', 1, 'corr', '2026-07-19 15:30:00')"
            ),
            {"digest": "a" * 64},
        )
        connection.execute(
            text(
                "INSERT INTO options_analysis_runs (id, run_key, scanner_run_id, candidate_id, symbol_id, input_digest, result_digest, policy_version, policy_hash, as_of, result_counts, reason_summary, created_at) VALUES ('run-row', 'run-key', 'scanner-row', 'candidate-row', 'symbol-row', :digest, :digest, 'v1', :digest, '2026-07-19 15:30:00', '{}', '{}', '2026-07-19 15:30:00')"
            ),
            {"digest": "a" * 64},
        )
        connection.execute(
            text(
                "INSERT INTO option_contract_evaluations (id, evaluation_key, run_id, contract_id, state, reasons, created_at) VALUES ('evaluation-row', 'evaluation-key', 'run-row', 'contract', 'accepted', '[]', '2026-07-19 15:30:00')"
            )
        )
        connection.execute(
            text(
                "INSERT INTO option_spread_candidates (id, spread_key, run_id, strategy, long_contract_id, short_contract_id, expiration, blocked, calculations, warning_keys, created_at) VALUES ('spread-row', 'spread-key', 'run-row', 'bull_call', 'long', 'short', '2026-08-21', 0, '{}', '[]', '2026-07-19 15:30:00')"
            )
        )
        connection.execute(
            text(
                "INSERT INTO option_spread_warnings (id, warning_key, spread_id, code, severity, facts, source_keys, created_at) VALUES ('warning-row', 'warning-key', 'spread-row', 'pin_risk', 'warning', '{}', '[]', '2026-07-19 15:30:00')"
            )
        )
