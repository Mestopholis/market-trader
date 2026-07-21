from pathlib import Path

from alembic import command
from sqlalchemy import create_engine, text

from market_trader.db.migrations import alembic_config
from market_trader.system_state.service import collect_system_state


def test_system_state_reports_required_components_for_clean_database(tmp_path: Path) -> None:
    database_url = _migrated_database(tmp_path / "clean.db")

    readiness = collect_system_state(database_url)

    components = {component.name: component for component in readiness.components}
    assert readiness.status == "ok"
    assert readiness.blocking is False
    assert components["database"].status == "ok"
    assert components["migrations"].status == "ok"
    assert components["risk_locks"].status == "ok"
    assert components["backup"].status == "unknown"
    assert components["market_data_freshness"].status == "unknown"
    assert components["scheduler_jobs"].status == "unknown"
    assert components["paper_reconciliation"].status == "unknown"
    assert components["auth_config"].status == "unknown"
    assert components["security_scan"].status == "unknown"
    assert database_url not in readiness.model_dump_json()


def test_system_state_reports_active_required_risk_lock_as_blocking(tmp_path: Path) -> None:
    database_url = _migrated_database(tmp_path / "locked.db")
    engine = create_engine(database_url)
    try:
        with engine.begin() as connection:
            connection.execute(
                text(
                    """
                    INSERT INTO risk_locks (
                        id, lock_type, status, reason, source_event_id, activated_at,
                        cleared_at, clearing_event_id, payload, payload_schema_version,
                        correlation_id
                    ) VALUES (
                        'lock_required', 'required:risk', 'active', 'risk breached',
                        NULL, '2026-07-21 01:00:00', NULL, NULL,
                        '{"required": true}', 1, 'corr-lock'
                    )
                    """
                )
            )
    finally:
        engine.dispose()

    readiness = collect_system_state(database_url)

    risk_locks = {component.name: component for component in readiness.components}["risk_locks"]
    assert readiness.status == "blocking"
    assert readiness.blocking is True
    assert risk_locks.status == "blocking"
    assert risk_locks.code == "required_risk_lock_active"
    assert risk_locks.blocking is True


def _migrated_database(path: Path) -> str:
    database_url = f"sqlite:///{path}"
    command.upgrade(alembic_config(database_url), "head")
    return database_url
