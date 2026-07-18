from pathlib import Path

from alembic import command
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.dialects import postgresql
from sqlalchemy.schema import CreateIndex

from market_trader.db.migrations import alembic_config
from market_trader.db.models import MarketDataQuarantineORM


def test_initial_migration_creates_domain_tables(tmp_path: Path) -> None:
    database_url = f"sqlite:///{tmp_path / 'migration.db'}"

    command.upgrade(alembic_config(database_url), "head")

    engine = create_engine(database_url)
    try:
        inspector = inspect(engine)
        assert {
            "symbols",
            "instruments",
            "market_data_snapshots",
            "signals",
            "candidates",
            "proposed_trades",
            "approvals",
            "orders",
            "fills",
            "positions",
            "risk_locks",
            "journal_events",
            "configuration_versions",
            "market_data_quarantine",
        }.issubset(set(inspector.get_table_names()))
        snapshot_columns = {
            column["name"] for column in inspector.get_columns("market_data_snapshots")
        }
        assert {"data_kind", "ingestion_key", "payload_digest"}.issubset(snapshot_columns)
    finally:
        engine.dispose()


def test_initial_migration_matches_orm_metadata(tmp_path: Path) -> None:
    database_url = f"sqlite:///{tmp_path / 'metadata.db'}"
    config = alembic_config(database_url)

    command.upgrade(config, "head")

    command.check(config)


def test_market_data_migration_upgrades_existing_snapshot(tmp_path: Path) -> None:
    database_url = f"sqlite:///{tmp_path / 'upgrade.db'}"
    config = alembic_config(database_url)
    command.upgrade(config, "20260718_0001")

    engine = create_engine(database_url)
    try:
        with engine.begin() as connection:
            connection.execute(
                text(
                    """
                    INSERT INTO symbols (
                        id, display_symbol, instrument_type, exchange, is_active,
                        first_observed_at, last_observed_at, metadata_payload,
                        metadata_schema_version, correlation_id
                    ) VALUES (
                        'sym_existing', 'SPY', 'equity', 'ARCX', 1,
                        '2026-07-17 14:30:00', '2026-07-17 14:30:00', '{}', 1, 'corr-setup'
                    )
                    """
                )
            )
            connection.execute(
                text(
                    """
                    INSERT INTO market_data_snapshots (
                        id, source, symbol_id, instrument_id, observed_at, ingested_at,
                        session_date, quality_state, configuration_version_id, payload,
                        payload_schema_version, correlation_id
                    ) VALUES (
                        'mds_existing', 'fixture', 'sym_existing', NULL,
                        '2026-07-17 14:30:00', '2026-07-17 14:30:00', '2026-07-17',
                        'valid', NULL, '{}', 1, 'corr-existing'
                    )
                    """
                )
            )
    finally:
        engine.dispose()
    command.upgrade(config, "head")

    engine = create_engine(database_url)
    try:
        with engine.connect() as connection:
            row = connection.execute(
                text(
                    "SELECT data_kind, ingestion_key, payload_digest FROM market_data_snapshots "
                    "WHERE id = 'mds_existing'"
                )
            ).one()
        assert row == ("legacy", "legacy:mds_existing", "legacy:mds_existing")
    finally:
        engine.dispose()


def test_quarantine_reason_index_uses_postgresql_gin() -> None:
    index = next(
        index
        for index in MarketDataQuarantineORM.__table__.indexes
        if index.name == "ix_market_data_quarantine_reason_codes"
    )

    statement = str(CreateIndex(index).compile(dialect=postgresql.dialect()))

    assert "USING gin" in statement
