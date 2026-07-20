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
from market_trader.db.models import RiskCheckORM, RiskDecisionORM, RiskReservationORM


def test_risk_schema_has_stable_keys_payloads_and_child_foreign_keys() -> None:
    decision = cast(Table, RiskDecisionORM.__table__)
    check = cast(Table, RiskCheckORM.__table__)
    reservation = cast(Table, RiskReservationORM.__table__)

    assert _index(decision, "ux_risk_decisions_decision_key").unique
    assert _index(check, "ux_risk_checks_check_key").unique
    assert _index(reservation, "ux_risk_reservations_reservation_key").unique
    assert {
        "decision_key",
        "status",
        "proposal_kind",
        "policy_version",
        "policy_hash",
        "input_digest",
        "result_digest",
        "reason_summary",
        "decision_payload",
    } <= set(decision.c.keys())
    assert _foreign_key(check, "decision_id") == "risk_decisions.id"
    assert _foreign_key(reservation, "decision_id") == "risk_decisions.id"
    assert all(
        cast(String, column.type).length == 512
        for column in (
            decision.c.decision_key,
            check.c.check_key,
            reservation.c.reservation_key,
        )
    )


@pytest.mark.parametrize(
    ("model", "column_name", "index_name"),
    (
        (RiskDecisionORM, "reason_summary", "ix_risk_decisions_reason_summary"),
        (RiskDecisionORM, "decision_payload", "ix_risk_decisions_decision_payload"),
        (RiskCheckORM, "facts", "ix_risk_checks_facts"),
        (RiskCheckORM, "source_keys", "ix_risk_checks_source_keys"),
        (RiskReservationORM, "reservation_payload", "ix_risk_reservations_payload"),
    ),
)
def test_risk_payloads_use_jsonb_and_gin(model: Any, column_name: str, index_name: str) -> None:
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


def test_risk_migration_creates_append_only_tables_at_head(tmp_path: Path) -> None:
    database_url = f"sqlite:///{tmp_path / 'risk.db'}"
    command.upgrade(alembic_config(database_url), "head")
    engine = create_engine(database_url)
    try:
        with engine.connect() as connection:
            tables = set(engine.dialect.get_table_names(connection))
        assert {"risk_decisions", "risk_checks", "risk_reservations"} <= tables
        _seed_risk_rows(engine)
        for table_name, row_id in (
            ("risk_decisions", "decision-row"),
            ("risk_checks", "check-row"),
            ("risk_reservations", "reservation-row"),
        ):
            with pytest.raises(IntegrityError, match="append-only"), engine.begin() as connection:
                connection.execute(
                    text(f"UPDATE {table_name} SET id = id WHERE id = :id"),
                    {"id": row_id},
                )
            with pytest.raises(IntegrityError, match="append-only"), engine.begin() as connection:
                connection.execute(text(f"DELETE FROM {table_name} WHERE id = :id"), {"id": row_id})
    finally:
        engine.dispose()


def test_risk_migration_source_defines_all_append_only_triggers() -> None:
    migration = Path("migrations/versions/20260720_0006_risk_decisions.py").read_text()
    assert "20260720_0006" in migration
    for table in ("risk_decisions", "risk_checks", "risk_reservations"):
        assert table in migration


def _index(table: Table, name: str) -> Index:
    return next(index for index in table.indexes if index.name == name)


def _foreign_key(table: Table, column: str) -> str:
    return str(next(iter(table.c[column].foreign_keys)).target_fullname)


def _seed_risk_rows(engine: Engine) -> None:
    with engine.begin() as connection:
        connection.execute(
            text(
                "INSERT INTO risk_decisions (id, decision_key, status, proposal_kind, policy_version, policy_hash, input_digest, result_digest, as_of, reason_summary, sizing_payload, decision_payload, correlation_id, created_at) VALUES ('decision-row', 'risk-key', 'approved', 'shares', 'risk-policy-v1', :digest, :digest, :digest, '2026-07-20 15:30:00', '[]', '{}', '{}', 'corr', '2026-07-20 15:30:00')"
            ),
            {"digest": "a" * 64},
        )
        connection.execute(
            text(
                "INSERT INTO risk_checks (id, check_key, decision_id, code, severity, state, facts, source_keys, created_at) VALUES ('check-row', 'check-key', 'decision-row', 'cash', 'info', 'passed', '{}', '[]', '2026-07-20 15:30:00')"
            )
        )
        connection.execute(
            text(
                "INSERT INTO risk_reservations (id, reservation_key, decision_id, amount, reservation_payload, created_at) VALUES ('reservation-row', 'reservation-key', 'decision-row', 25.00, '{}', '2026-07-20 15:30:00')"
            )
        )
