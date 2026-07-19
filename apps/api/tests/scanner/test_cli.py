import json
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path

import pytest
from alembic.util.exc import CommandError
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from market_trader.db.engine import create_engine_from_url
from market_trader.db.migrations import upgrade_to_head
from market_trader.db.models import (
    EligibilityDecisionORM,
    JournalEventORM,
    ScannerRunORM,
    SignalORM,
)
from market_trader.repositories.symbols import SymbolCreate, SymbolRepository
from market_trader.scanner.cli import main
from market_trader.scanner.configuration import load_scanner_configuration

API_ROOT = Path(__file__).parents[2]
FIXTURES = API_ROOT / "fixtures" / "scanner"
BULLISH = FIXTURES / "bullish"
CONFIGURATION = API_ROOT / "config" / "scanner"
OBSERVED = datetime(2026, 7, 17, 15, 35, tzinfo=UTC)


def test_validate_prints_deterministic_expected_summary(
    capsys: pytest.CaptureFixture[str],
) -> None:
    first_code = main(["validate", str(BULLISH)])
    first = capsys.readouterr()
    second_code = main(["validate", str(BULLISH)])
    second = capsys.readouterr()

    payload = json.loads(first.out)
    assert first_code == second_code == 0
    assert first.err == second.err == ""
    assert first.out == second.out
    assert payload["command"] == "validate"
    assert payload["dataset_id"] == "bullish"
    assert payload["persistence"] == "memory"
    assert payload["regime"]["state"] == "bullish"
    assert payload["counts"]["signals"] == 5
    assert payload["result_digest"]
    assert "database" not in payload


def test_scan_defaults_to_memory_and_module_entrypoint_is_one_json_line(
    capsys: pytest.CaptureFixture[str],
) -> None:
    code = main(["scan", str(BULLISH)])
    captured = capsys.readouterr()
    completed = subprocess.run(
        [sys.executable, "-m", "market_trader.scanner.cli", "scan", str(BULLISH)],
        cwd=API_ROOT,
        check=False,
        capture_output=True,
        text=True,
    )

    payload = json.loads(captured.out)
    assert code == completed.returncode == 0
    assert captured.err == completed.stderr == ""
    assert payload["command"] == "scan"
    assert payload["persistence"] == "memory"
    assert len(completed.stdout.splitlines()) == 1
    assert json.loads(completed.stdout)["result_digest"] == payload["result_digest"]


def test_persistent_scan_matches_memory_and_exact_rerun_is_idempotent(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    database_url = f"sqlite:///{tmp_path / 'scanner.db'}"
    _seed_universe(database_url)
    assert main(["scan", str(BULLISH)]) == 0
    memory = json.loads(capsys.readouterr().out)

    assert main(["scan", str(BULLISH), "--database-url", database_url]) == 0
    first = json.loads(capsys.readouterr().out)
    first_counts = _scanner_counts(database_url)
    assert main(["scan", str(BULLISH), "--database-url", database_url]) == 0
    second = json.loads(capsys.readouterr().out)

    assert first["persistence"] == second["persistence"] == "database"
    assert first["result_digest"] == second["result_digest"] == memory["result_digest"]
    assert first["run_key"] == second["run_key"] == memory["run_key"]
    assert first_counts == _scanner_counts(database_url)
    assert first_counts[:3] == (1, 30, 5)


def test_expected_mismatch_is_a_sanitized_dataset_error(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    path = tmp_path / "fixture"
    _copy_fixture(BULLISH, path)
    manifest_path = path / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["expected"]["eligible"] += 1
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

    code = main(["validate", str(path)])

    captured = capsys.readouterr()
    assert code == 2
    assert captured.out == ""
    assert json.loads(captured.err) == {
        "error": "dataset_error",
        "message": "scanner result does not match fixture expectations",
    }


def test_database_failure_does_not_leak_url_or_internal_error(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    secret_url = "postgresql://user:must-not-leak@example.test/database"

    def fail_migration(_database_url: str) -> None:
        raise CommandError(f"failed for {secret_url}")

    monkeypatch.setattr("market_trader.scanner.cli.upgrade_to_head", fail_migration)

    code = main(["scan", str(BULLISH), "--database-url", secret_url])

    captured = capsys.readouterr()
    assert code == 3
    assert captured.out == ""
    assert json.loads(captured.err) == {
        "error": "infrastructure_error",
        "message": "database operation failed",
    }
    assert "must-not-leak" not in captured.err


def test_unexpected_scanner_exception_is_sanitized(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    def fail_scan(*_args: object) -> None:
        raise RuntimeError("must-not-leak")

    monkeypatch.setattr("market_trader.scanner.cli._scan", fail_scan)

    code = main(["validate", str(BULLISH)])

    captured = capsys.readouterr()
    assert code == 3
    assert captured.out == ""
    assert json.loads(captured.err) == {
        "error": "infrastructure_error",
        "message": "scanner operation failed",
    }
    assert "must-not-leak" not in captured.err


def _seed_universe(database_url: str) -> None:
    upgrade_to_head(database_url)
    configuration = load_scanner_configuration(CONFIGURATION)
    engine = create_engine_from_url(database_url)
    try:
        with Session(engine) as session, session.begin():
            repository = SymbolRepository(session)
            for entry in configuration.universe.entries:
                repository.create_symbol(
                    SymbolCreate(
                        display_symbol=entry.display_symbol,
                        instrument_type=entry.security_type,
                        exchange=entry.exchange_family,
                        is_active=True,
                        first_observed_at=OBSERVED,
                        last_observed_at=OBSERVED,
                        metadata_payload={"schema_version": 1},
                        metadata_schema_version=1,
                        correlation_id="scanner-cli-seed",
                    )
                )
    finally:
        engine.dispose()


def _scanner_counts(database_url: str) -> tuple[int, int, int, int]:
    engine = create_engine_from_url(database_url)
    try:
        with Session(engine) as session:
            return (
                session.scalar(select(func.count()).select_from(ScannerRunORM)) or 0,
                session.scalar(select(func.count()).select_from(EligibilityDecisionORM)) or 0,
                session.scalar(select(func.count()).select_from(SignalORM)) or 0,
                session.scalar(select(func.count()).select_from(JournalEventORM)) or 0,
            )
    finally:
        engine.dispose()


def _copy_fixture(source: Path, destination: Path) -> None:
    import shutil

    shutil.copytree(source, destination)
