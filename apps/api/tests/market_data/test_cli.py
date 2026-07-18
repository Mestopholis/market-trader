import json
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path

import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from market_trader.db.engine import create_engine_from_url
from market_trader.db.migrations import upgrade_to_head
from market_trader.db.models import (
    JournalEventORM,
    MarketDataQuarantineORM,
    MarketDataSnapshotORM,
)
from market_trader.market_data.cli import main
from market_trader.repositories.symbols import SymbolCreate, SymbolRepository

API_ROOT = Path(__file__).parents[2]
REGULAR_SESSION = API_ROOT / "fixtures" / "market_data" / "regular-session"
MINIMAL = Path(__file__).parent / "fixtures" / "minimal"
MALFORMED = Path(__file__).parent / "fixtures" / "malformed-json"
OBSERVED = datetime(2026, 7, 20, 14, 30, tzinfo=UTC)


def test_validate_prints_machine_readable_summary(
    capsys: pytest.CaptureFixture[str],
) -> None:
    exit_code = main(["validate", str(REGULAR_SESSION)])

    captured = capsys.readouterr()
    payload = json.loads(captured.out)
    assert exit_code == 0
    assert captured.err == ""
    assert payload["command"] == "validate"
    assert payload["dataset_id"] == "regular-session"
    assert payload["accepted"] == 6
    assert payload["degraded"] == 2
    assert payload["result_digest"]
    assert "database" not in payload


def test_validate_module_entrypoint_prints_one_json_object() -> None:
    completed = subprocess.run(
        [sys.executable, "-m", "market_trader.market_data.cli", "validate", str(MINIMAL)],
        cwd=API_ROOT,
        check=False,
        capture_output=True,
        text=True,
    )

    assert completed.returncode == 0
    assert completed.stderr == ""
    assert len(completed.stdout.splitlines()) == 1
    assert json.loads(completed.stdout)["dataset_id"] == "minimal"


def test_replay_defaults_to_in_memory(capsys: pytest.CaptureFixture[str]) -> None:
    exit_code = main(["replay", str(REGULAR_SESSION)])

    payload = json.loads(capsys.readouterr().out)
    assert exit_code == 0
    assert payload["command"] == "replay"
    assert payload["persistence"] == "memory"
    assert payload["result_digest"]


def test_persistent_replay_rolls_back_for_unknown_symbol(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    database_url = f"sqlite:///{tmp_path / 'unknown.db'}"

    exit_code = main(["replay", str(MINIMAL), "--database-url", database_url])

    captured = capsys.readouterr()
    error = json.loads(captured.err)
    assert exit_code == 3
    assert captured.out == ""
    assert error == {
        "error": "infrastructure_error",
        "message": "unknown symbol: SPY",
    }
    assert table_counts(database_url) == (0, 0, 0)


def test_persistent_replay_is_idempotent(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    database_url = f"sqlite:///{tmp_path / 'replay.db'}"
    seed_symbols(database_url, "SPY", "QQQ", "IWM")

    first_code = main(
        ["replay", str(REGULAR_SESSION), "--database-url", database_url]
    )
    first_output = json.loads(capsys.readouterr().out)
    first_counts = table_counts(database_url)
    second_code = main(
        ["replay", str(REGULAR_SESSION), "--database-url", database_url]
    )
    second_output = json.loads(capsys.readouterr().out)

    assert first_code == second_code == 0
    assert first_output == second_output
    assert first_output["persistence"] == "database"
    assert first_counts == (8, 0, 11)
    assert table_counts(database_url) == first_counts


def test_dataset_error_is_sanitized_json(
    capsys: pytest.CaptureFixture[str],
) -> None:
    exit_code = main(["validate", str(MALFORMED)])

    captured = capsys.readouterr()
    error = json.loads(captured.err)
    assert exit_code == 2
    assert captured.out == ""
    assert error["error"] == "dataset_error"
    assert "malformed JSON" in error["message"]
    assert "must-not-leak" not in captured.err


def seed_symbols(database_url: str, *symbols: str) -> None:
    upgrade_to_head(database_url)
    engine = create_engine_from_url(database_url)
    try:
        with Session(engine) as session:
            repository = SymbolRepository(session)
            for symbol in symbols:
                repository.create_symbol(
                    SymbolCreate(
                        display_symbol=symbol,
                        instrument_type="equity",
                        exchange="ARCX",
                        is_active=True,
                        first_observed_at=OBSERVED,
                        last_observed_at=OBSERVED,
                        metadata_payload={"schema_version": 1},
                        metadata_schema_version=1,
                        correlation_id=f"fixture-symbol-{symbol}",
                    )
                )
            session.commit()
    finally:
        engine.dispose()


def table_counts(database_url: str) -> tuple[int, int, int]:
    engine = create_engine_from_url(database_url)
    try:
        with Session(engine) as session:
            snapshots = session.scalar(
                select(func.count()).select_from(MarketDataSnapshotORM)
            )
            quarantine = session.scalar(
                select(func.count()).select_from(MarketDataQuarantineORM)
            )
            audits = session.scalar(select(func.count()).select_from(JournalEventORM))
            assert snapshots is not None
            assert quarantine is not None
            assert audits is not None
            return snapshots, quarantine, audits
    finally:
        engine.dispose()
