import json
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path

import pytest
from alembic.util.exc import CommandError
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from market_trader.catalysts.cli import main
from market_trader.catalysts.models import SourceFailure, SourceFailureKind
from market_trader.db.engine import create_engine_from_url
from market_trader.db.migrations import upgrade_to_head
from market_trader.db.models import CatalystSourceRunORM
from market_trader.repositories.symbols import SymbolCreate, SymbolRepository

API_ROOT = Path(__file__).parents[2]
MINIMAL = Path(__file__).parent / "fixtures" / "minimal"
AS_OF = datetime(2026, 7, 17, 15, 0, tzinfo=UTC)


def test_validate_and_replay_default_to_database_free_canonical_output(
    capsys: pytest.CaptureFixture[str],
) -> None:
    assert main(["validate", str(MINIMAL)]) == 0
    validated = json.loads(capsys.readouterr().out)
    assert main(["replay", str(MINIMAL)]) == 0
    replayed = json.loads(capsys.readouterr().out)

    assert validated["command"] == "validate"
    assert replayed["command"] == "replay"
    assert validated["result_digest"] == replayed["result_digest"]
    assert validated["persistence"] == replayed["persistence"] == "memory"
    assert "database_url" not in validated


def test_module_entrypoint_is_one_compact_json_line() -> None:
    completed = subprocess.run(
        [sys.executable, "-m", "market_trader.catalysts.cli", "validate", str(MINIMAL)],
        cwd=API_ROOT,
        check=False,
        capture_output=True,
        text=True,
    )

    assert completed.returncode == 0
    assert completed.stderr == ""
    assert len(completed.stdout.splitlines()) == 1
    assert json.loads(completed.stdout)["dataset_id"] == "minimal-catalysts"


def test_persistent_replay_migrates_once_and_exact_rerun_is_idempotent(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    database_url = f"sqlite:///{tmp_path / 'catalysts.db'}"
    _seed_symbol(database_url)
    arguments = ["replay", str(MINIMAL), "--database-url", database_url]

    assert main(arguments) == 0
    first = json.loads(capsys.readouterr().out)
    first_count = _run_count(database_url)
    assert main(arguments) == 0
    second = json.loads(capsys.readouterr().out)

    assert first["persistence"] == second["persistence"] == "database"
    assert first["result_digest"] == second["result_digest"]
    assert first_count == _run_count(database_url) == 1


def test_dataset_and_database_errors_are_sanitized(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    secret = "postgresql://user:must-not-leak@example.test/database"
    assert main(["validate", str(tmp_path / "missing")]) == 2
    dataset_error = capsys.readouterr()
    assert json.loads(dataset_error.err)["error"] == "dataset_error"

    def fail_migration(_url: str) -> None:
        raise CommandError(secret)

    monkeypatch.setattr("market_trader.catalysts.cli.upgrade_to_head", fail_migration)
    assert main(["replay", str(MINIMAL), "--database-url", secret]) == 3
    database_error = capsys.readouterr()
    assert json.loads(database_error.err) == {
        "error": "infrastructure_error",
        "message": "database operation failed",
    }
    assert "must-not-leak" not in database_error.err


def test_fetch_requires_explicit_source_and_as_of_and_maps_source_failure_to_four(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    failure = SourceFailure(
        source_id="sec-edgar-public-v1",
        kind=SourceFailureKind.UNAVAILABLE,
        occurred_at=AS_OF,
        reasons=("sec_unavailable",),
    )
    monkeypatch.setattr("market_trader.catalysts.cli._fetch_source", lambda *args: failure)

    code = main(["fetch", "sec", "--as-of", AS_OF.isoformat()])

    captured = capsys.readouterr()
    assert code == 4
    assert captured.out == ""
    assert json.loads(captured.err) == {
        "error": "source_error",
        "message": "catalyst source unavailable",
    }


def _seed_symbol(database_url: str) -> None:
    upgrade_to_head(database_url)
    engine = create_engine_from_url(database_url)
    try:
        with Session(engine) as session, session.begin():
            SymbolRepository(session).create_symbol(
                SymbolCreate(
                    display_symbol="AAPL",
                    instrument_type="equity",
                    exchange="XNAS",
                    is_active=True,
                    first_observed_at=AS_OF,
                    last_observed_at=AS_OF,
                    metadata_payload={},
                    metadata_schema_version=1,
                    correlation_id="cli-seed",
                )
            )
    finally:
        engine.dispose()


def _run_count(database_url: str) -> int:
    engine = create_engine_from_url(database_url)
    try:
        with Session(engine) as session:
            return session.scalar(select(func.count()).select_from(CatalystSourceRunORM)) or 0
    finally:
        engine.dispose()
