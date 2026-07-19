from typing import cast

from sqlalchemy import JSON, Index, String, Table, UniqueConstraint
from sqlalchemy.dialects import postgresql, sqlite
from sqlalchemy.schema import CreateIndex, CreateTable

from market_trader.db.models import (
    CandidateORM,
    EligibilityDecisionORM,
    ScannerRunORM,
    SignalORM,
)


def test_scanner_run_schema_records_deterministic_result_lineage() -> None:
    table = cast(Table, ScannerRunORM.__table__)

    assert {
        "id",
        "run_key",
        "as_of",
        "session_date",
        "input_digest",
        "universe_version",
        "universe_content_hash",
        "policy_versions",
        "regime_state",
        "regime_score",
        "regime_explanation",
        "result_counts",
        "result_digest",
        "status",
        "correlation_id",
        "created_at",
    } == set(table.columns.keys())
    assert _index(table, "ux_scanner_runs_run_key").unique
    assert _index(table, "ix_scanner_runs_session_date").columns.keys() == ["session_date"]
    assert _index(table, "ix_scanner_runs_status").columns.keys() == ["status"]
    assert _index(table, "ix_scanner_runs_correlation_id").columns.keys() == ["correlation_id"]


def test_eligibility_schema_has_unique_symbol_decision_per_run() -> None:
    table = cast(Table, EligibilityDecisionORM.__table__)

    assert {
        "id",
        "decision_key",
        "scanner_run_id",
        "symbol_id",
        "status",
        "reason_codes",
        "observed_payload",
        "input_digest",
        "policy_version",
        "correlation_id",
        "created_at",
    } == set(table.columns.keys())
    assert _foreign_key(table, "scanner_run_id") == "scanner_runs.id"
    assert _foreign_key(table, "symbol_id") == "symbols.id"
    assert _index(table, "ux_eligibility_decisions_decision_key").unique
    assert any(
        isinstance(constraint, UniqueConstraint)
        and constraint.name == "uq_eligibility_decisions_run_symbol"
        and constraint.columns.keys() == ["scanner_run_id", "symbol_id"]
        for constraint in table.constraints
    )


def test_existing_decisions_gain_nullable_scanner_lineage() -> None:
    signal = cast(Table, SignalORM.__table__)
    candidate = cast(Table, CandidateORM.__table__)

    assert {
        "signal_key",
        "scanner_run_id",
        "strategy_id",
        "input_digest",
        "reason_codes",
        "gate_payload",
        "component_score_payload",
        "scoring_policy_version",
    }.issubset(signal.columns.keys())
    assert {
        "candidate_key",
        "scanner_run_id",
        "strategy_id",
        "direction",
        "input_digest",
        "scoring_policy_version",
    }.issubset(candidate.columns.keys())
    assert all(
        signal.columns[name].nullable
        for name in (
            "signal_key",
            "scanner_run_id",
            "strategy_id",
            "input_digest",
            "reason_codes",
            "gate_payload",
            "component_score_payload",
            "scoring_policy_version",
        )
    )
    assert all(
        candidate.columns[name].nullable
        for name in (
            "candidate_key",
            "scanner_run_id",
            "strategy_id",
            "direction",
            "input_digest",
            "scoring_policy_version",
        )
    )
    assert _foreign_key(signal, "scanner_run_id") == "scanner_runs.id"
    assert _foreign_key(candidate, "scanner_run_id") == "scanner_runs.id"
    assert _index(signal, "ux_signals_signal_key").unique
    assert _index(candidate, "ux_candidates_candidate_key").unique


def test_stable_key_columns_fit_versioned_scanner_identities() -> None:
    columns = (
        cast(Table, ScannerRunORM.__table__).c.run_key,
        cast(Table, EligibilityDecisionORM.__table__).c.decision_key,
        cast(Table, SignalORM.__table__).c.signal_key,
        cast(Table, CandidateORM.__table__).c.candidate_key,
    )

    assert all(cast(String, column.type).length == 512 for column in columns)


def test_reason_codes_use_sqlite_json_and_postgresql_jsonb_with_gin() -> None:
    table = cast(Table, EligibilityDecisionORM.__table__)
    column = table.c.reason_codes
    index = _index(
        table,
        "ix_eligibility_decisions_reason_codes",
    )

    assert isinstance(column.type.dialect_impl(sqlite.dialect()), JSON)
    assert "JSONB" in str(
        CreateTable(table).compile(
            dialect=postgresql.dialect()  # type: ignore[no-untyped-call]
        )
    )
    assert "USING gin" in str(
        CreateIndex(index).compile(
            dialect=postgresql.dialect()  # type: ignore[no-untyped-call]
        )
    )


def _index(table: Table, name: str) -> Index:
    return next(index for index in table.indexes if index.name == name)


def _foreign_key(table: Table, column_name: str) -> str:
    column = table.columns[column_name]
    return str(next(iter(column.foreign_keys)).target_fullname)
