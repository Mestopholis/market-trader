from pathlib import Path

import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from tests.db_helpers import migrated_engine


def test_quarantine_rows_cannot_be_updated_or_deleted(tmp_path: Path) -> None:
    engine = migrated_engine(tmp_path)
    try:
        with engine.begin() as connection:
            connection.execute(
                text(
                    """
                    INSERT INTO market_data_quarantine (
                        id, ingestion_key, source, event_id, data_kind,
                        observed_at, ingested_at, symbol_identity, instrument_identity,
                        sanitized_payload, payload_digest, reason_codes,
                        fixture_schema_version, normalized_schema_version,
                        configuration_version, correlation_id, created_at
                    ) VALUES (
                        'mdq_test', 'ing_test', 'fixture', 'event-1', 'quote',
                        '2026-07-17 14:30:00', '2026-07-17 14:30:01', 'SPY', NULL,
                        '{}', 'abc123', '[\"missing_field\"]', 1, 1,
                        'fixture-v1', 'corr-1', '2026-07-17 14:30:01'
                    )
                    """
                )
            )

        with pytest.raises(IntegrityError, match="append-only"), engine.begin() as connection:
            connection.execute(
                text("UPDATE market_data_quarantine SET source = 'changed' WHERE id = 'mdq_test'")
            )

        with pytest.raises(IntegrityError, match="append-only"), engine.begin() as connection:
            connection.execute(text("DELETE FROM market_data_quarantine WHERE id = 'mdq_test'"))
    finally:
        engine.dispose()
