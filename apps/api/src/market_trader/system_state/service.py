from collections.abc import Sequence

from alembic.runtime.migration import MigrationContext
from alembic.script import ScriptDirectory
from sqlalchemy import Engine, text
from sqlalchemy.exc import SQLAlchemyError

from market_trader.db.engine import create_engine_from_url
from market_trader.db.migrations import alembic_config
from market_trader.system_state.models import ComponentState, ReadinessStatus, SystemReadiness


def collect_system_state(database_url: str) -> SystemReadiness:
    engine: Engine | None = None
    components: list[ComponentState] = []
    try:
        engine = create_engine_from_url(database_url)
        components.append(_database_state(engine))
        components.append(_migration_state(engine, database_url))
        components.extend(_placeholder_components())
        components.append(_risk_lock_state(engine))
        components.extend(_post_risk_placeholder_components())
    except SQLAlchemyError:
        components = [
            ComponentState(
                name="database",
                status="unavailable",
                code="database_unavailable",
                summary="Database connection is unavailable.",
                blocking=True,
            ),
            ComponentState(
                name="migrations",
                status="unavailable",
                code="migration_state_unavailable",
                summary="Migration state cannot be checked while the database is unavailable.",
                blocking=True,
            ),
            *_placeholder_components(),
            ComponentState(
                name="risk_locks",
                status="unavailable",
                code="risk_lock_state_unavailable",
                summary="Risk lock state cannot be checked while the database is unavailable.",
                blocking=True,
            ),
            *_post_risk_placeholder_components(),
        ]
    finally:
        if engine is not None:
            engine.dispose()
    return _readiness_from_components(components)


def _database_state(engine: Engine) -> ComponentState:
    with engine.connect() as connection:
        connection.execute(text("SELECT 1")).scalar_one()
    return ComponentState(
        name="database",
        status="ok",
        code="database_ok",
        summary="Database connection is available.",
    )


def _migration_state(engine: Engine, database_url: str) -> ComponentState:
    config = alembic_config(database_url)
    script = ScriptDirectory.from_config(config)
    expected_head = script.get_current_head()
    with engine.connect() as connection:
        context = MigrationContext.configure(connection)
        current_revision = context.get_current_revision()
    if current_revision == expected_head:
        return ComponentState(
            name="migrations",
            status="ok",
            code="migrations_at_head",
            summary="Database schema is at the Alembic head revision.",
        )
    return ComponentState(
        name="migrations",
        status="blocking",
        code="migrations_not_at_head",
        summary="Database schema is not at the Alembic head revision.",
        blocking=True,
        details={"current_revision": current_revision or "none"},
    )


def _risk_lock_state(engine: Engine) -> ComponentState:
    with engine.connect() as connection:
        active_required_count = connection.execute(
            text(
                """
                SELECT COUNT(*)
                FROM risk_locks
                WHERE status = 'active'
                  AND (
                    lock_type LIKE 'required%'
                    OR json_extract(payload, '$.required') = 1
                  )
                """
            )
        ).scalar_one()
    count = int(active_required_count)
    if count > 0:
        return ComponentState(
            name="risk_locks",
            status="blocking",
            code="required_risk_lock_active",
            summary="One or more required risk locks are active.",
            blocking=True,
            details={"active_required_count": count},
        )
    return ComponentState(
        name="risk_locks",
        status="ok",
        code="no_required_risk_locks",
        summary="No required risk locks are active.",
        details={"active_required_count": 0},
    )


def _placeholder_components() -> list[ComponentState]:
    return [
        _unknown_component(
            "backup",
            "backup_state_unknown",
            "Backup freshness has not been recorded yet.",
        ),
        _unknown_component(
            "market_data_freshness",
            "market_data_freshness_unknown",
            "Market data freshness state has not been recorded yet.",
        ),
        _unknown_component(
            "scheduler_jobs",
            "scheduler_jobs_unknown",
            "Scheduler job health has not been recorded yet.",
        ),
    ]


def _post_risk_placeholder_components() -> list[ComponentState]:
    return [
        _unknown_component(
            "paper_reconciliation",
            "paper_reconciliation_unknown",
            "Paper reconciliation state has not been recorded yet.",
        ),
        _unknown_component(
            "auth_config",
            "auth_config_unknown",
            "Authentication configuration checks are not implemented yet.",
        ),
        _unknown_component(
            "security_scan",
            "security_scan_unknown",
            "Security scan metadata has not been recorded yet.",
        ),
    ]


def _unknown_component(name: str, code: str, summary: str) -> ComponentState:
    return ComponentState(name=name, status="unknown", code=code, summary=summary)


def _readiness_from_components(components: Sequence[ComponentState]) -> SystemReadiness:
    blocking = any(component.blocking for component in components)
    unavailable = any(component.status == "unavailable" for component in components)
    status: ReadinessStatus = "blocking" if blocking else "unavailable" if unavailable else "ok"
    return SystemReadiness(status=status, blocking=blocking, components=list(components))
