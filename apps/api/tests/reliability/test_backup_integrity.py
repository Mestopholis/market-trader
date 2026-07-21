from pathlib import Path

import pytest
from sqlalchemy import create_engine, text

from market_trader.db.backup import backup_sqlite_database
from market_trader.db.migrations import upgrade_to_head
from market_trader.recovery.backup import collect_backup_metadata
from market_trader.recovery.integrity import IntegrityError, validate_sqlite_integrity


def test_backup_returns_metadata_with_schema_counts_checksum_and_correlation_id(
    tmp_path: Path,
) -> None:
    source = tmp_path / "source.db"
    destination = tmp_path / "backup.db"
    upgrade_to_head(f"sqlite:///{source}")
    _insert_audit_and_paper_rows(source)

    metadata = backup_sqlite_database(
        source,
        destination,
        correlation_id="corr-backup",
    )

    assert destination.exists()
    assert metadata.source_path == str(source)
    assert metadata.destination_path == str(destination)
    assert metadata.correlation_id == "corr-backup"
    assert metadata.schema_revision
    assert metadata.row_counts["journal_events"] == 1
    assert metadata.row_counts["proposed_trades"] == 1
    assert metadata.row_counts["approvals"] == 1
    assert metadata.row_counts["orders"] == 1
    assert len(metadata.sha256) == 64
    assert metadata.integrity_ok is True


def test_integrity_validation_rejects_missing_audit_for_paper_order(tmp_path: Path) -> None:
    database = tmp_path / "broken.db"
    upgrade_to_head(f"sqlite:///{database}")
    engine = create_engine(f"sqlite:///{database}")
    try:
        with engine.begin() as connection:
            connection.execute(
                text(
                    """
                    INSERT INTO orders (
                        id, proposed_trade_id, approval_id, status, order_intent_payload,
                        payload_schema_version, broker_reference, simulated_broker_reference,
                        correlation_id, created_at, updated_at, terminal_at
                    ) VALUES (
                        'order-broken', NULL, NULL, 'working', '{}', 1, NULL,
                        'sim-paper-order-broken', 'corr-broken',
                        '2026-07-21 01:00:00', '2026-07-21 01:00:00', NULL
                    )
                    """
                )
            )
    finally:
        engine.dispose()

    with pytest.raises(IntegrityError, match="missing audit events"):
        validate_sqlite_integrity(database)


def test_backup_refuses_to_overwrite_existing_destination_without_force(tmp_path: Path) -> None:
    source = tmp_path / "source.db"
    destination = tmp_path / "backup.db"
    upgrade_to_head(f"sqlite:///{source}")
    destination.write_text("existing", encoding="utf-8")

    with pytest.raises(FileExistsError):
        backup_sqlite_database(source, destination)


def test_collect_backup_metadata_runs_integrity_without_exposing_database_url(
    tmp_path: Path,
) -> None:
    database = tmp_path / "source.db"
    upgrade_to_head(f"sqlite:///{database}")

    metadata = collect_backup_metadata(
        source=database,
        destination=tmp_path / "backup.db",
        correlation_id="corr-meta",
    )

    assert metadata.integrity_ok is True
    assert "sqlite:///" not in metadata.model_dump_json()


def _insert_audit_and_paper_rows(database: Path) -> None:
    engine = create_engine(f"sqlite:///{database}")
    try:
        with engine.begin() as connection:
            connection.execute(
                text(
                    """
                    INSERT INTO journal_events (
                        id, correlation_id, event_type, actor_type, occurred_at, recorded_at,
                        subject_type, subject_id, causation_event_id, payload, schema_version
                    ) VALUES (
                        'evt-backup', 'corr-backup', 'paper_order.created', 'system',
                        '2026-07-21 01:00:00', '2026-07-21 01:00:01',
                        'order', 'order-a', NULL, '{}', 1
                    )
                    """
                )
            )
            connection.execute(
                text(
                    """
                    INSERT INTO proposed_trades (
                        id, candidate_id, status, order_intent_payload, payload_schema_version,
                        correlation_id, created_at, updated_at, terminal_at
                    ) VALUES (
                        'proposal-a', NULL, 'approved', '{}', 1, 'corr-backup',
                        '2026-07-21 01:00:00', '2026-07-21 01:00:00', NULL
                    )
                    """
                )
            )
            connection.execute(
                text(
                    """
                    INSERT INTO approvals (
                        id, proposed_trade_id, status, actor_type, decision_payload,
                        payload_schema_version, correlation_id, created_at, updated_at,
                        terminal_at
                    ) VALUES (
                        'approval-a', 'proposal-a', 'approved', 'system', '{}', 1,
                        'corr-backup', '2026-07-21 01:00:00',
                        '2026-07-21 01:00:00', NULL
                    )
                    """
                )
            )
            connection.execute(
                text(
                    """
                    INSERT INTO orders (
                        id, proposed_trade_id, approval_id, status, order_intent_payload,
                        payload_schema_version, broker_reference, simulated_broker_reference,
                        correlation_id, created_at, updated_at, terminal_at
                    ) VALUES (
                        'order-a', 'proposal-a', 'approval-a', 'working', '{}', 1, NULL,
                        'sim-paper-order-a', 'corr-backup',
                        '2026-07-21 01:00:00', '2026-07-21 01:00:00', NULL
                    )
                    """
                )
            )
    finally:
        engine.dispose()
