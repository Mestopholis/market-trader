from __future__ import annotations

import argparse
import contextlib
import io
import json
import sys
from collections import Counter
from collections.abc import Sequence
from datetime import timedelta
from pathlib import Path
from typing import TextIO, cast

from alembic.util.exc import CommandError
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from market_trader.db.engine import create_engine_from_url
from market_trader.db.migrations import upgrade_to_head
from market_trader.market_calendar.adapter import XNYSCalendarAdapter
from market_trader.market_data.models import NormalizedProviderState
from market_trader.market_data.replay import ReplayEngine, VirtualReplayClock
from market_trader.market_data.sinks import (
    AcceptedIngestion,
    InMemoryIngestionSink,
    RejectedIngestion,
    ReplayInfrastructureError,
    RepositoryIngestionSink,
)
from market_trader.repositories.scanner import ScannerPersistenceError, ScannerRepository
from market_trader.scanner.configuration import (
    ConfigurationError,
    ScannerConfiguration,
    load_scanner_configuration,
)
from market_trader.scanner.engine import ScannerEngine
from market_trader.scanner.fixtures import (
    ScannerFixtureDataset,
    ScannerFixtureValidationError,
    assemble_scanner_input,
)
from market_trader.scanner.models import ScanResult
from market_trader.scanner.serialization import canonical_record

_DEFAULT_CONFIGURATION = Path("config/scanner")


def main(argv: Sequence[str] | None = None) -> int:
    arguments = _parser().parse_args(argv)
    try:
        dataset = ScannerFixtureDataset.load(arguments.dataset)
        configuration = load_scanner_configuration(arguments.config)
        result = _scan(dataset, configuration)
        _require_expected(dataset, result)
    except (ConfigurationError, ScannerFixtureValidationError, OSError, ValueError):
        _print_error(
            "dataset_error",
            "scanner result does not match fixture expectations",
        )
        return 2
    except Exception:
        _print_error("infrastructure_error", "scanner operation failed")
        return 3

    persistence = "memory"
    if arguments.command == "scan" and arguments.database_url is not None:
        try:
            _persist(dataset, result, arguments.database_url)
        except (
            CommandError,
            OSError,
            ReplayInfrastructureError,
            ScannerPersistenceError,
            SQLAlchemyError,
        ):
            _print_error("infrastructure_error", "database operation failed")
            return 3
        persistence = "database"

    payload = _result_payload(result)
    payload.update(
        {
            "command": arguments.command,
            "dataset_id": dataset.manifest.dataset_id,
            "persistence": persistence,
        }
    )
    _print_json(payload, stream=sys.stdout)
    return 0


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="scanner")
    commands = parser.add_subparsers(dest="command", required=True)
    for command in ("validate", "scan"):
        subcommand = commands.add_parser(command)
        subcommand.add_argument("dataset", type=Path)
        subcommand.add_argument("--config", type=Path, default=_DEFAULT_CONFIGURATION)
        if command == "scan":
            subcommand.add_argument("--database-url")
    return parser


def _scan(dataset: ScannerFixtureDataset, configuration: ScannerConfiguration) -> ScanResult:
    if dataset.manifest.configuration_hashes != configuration.content_hashes:
        raise ScannerFixtureValidationError("configuration hashes do not match fixture")
    sink = InMemoryIngestionSink()
    _replay(dataset, sink)
    scanner_input = assemble_scanner_input(dataset, sink.accepted)
    return ScannerEngine(configuration).scan(scanner_input)


def _persist(
    dataset: ScannerFixtureDataset,
    result: ScanResult,
    database_url: str,
) -> None:
    with contextlib.redirect_stderr(io.StringIO()):
        upgrade_to_head(database_url)
    engine = create_engine_from_url(database_url)
    try:
        with Session(engine) as session, session.begin():
            sink = _ScannerRepositoryIngestionSink(session)
            _replay(dataset, sink)
            ScannerRepository(session).persist(result)
    finally:
        engine.dispose()


def _replay(
    dataset: ScannerFixtureDataset,
    sink: InMemoryIngestionSink | _ScannerRepositoryIngestionSink,
) -> None:
    event_dates = [event.observed_at.date() for event in dataset.market.events]
    start = min(event_dates) - timedelta(days=370)
    end = max(event_dates) + timedelta(days=370)
    ReplayEngine(
        clock=VirtualReplayClock(),
        calendar=XNYSCalendarAdapter(start=start, end=end),
        sink=sink,
    ).replay(dataset.market)


def _require_expected(dataset: ScannerFixtureDataset, result: ScanResult) -> None:
    expected = dataset.manifest.expected
    actual = (
        result.regime.state.value,
        result.regime.signed_score,
        result.counts.eligible,
        result.counts.ineligible,
        result.counts.blocked,
        result.counts.signals,
        result.counts.candidates,
        _reason_summary(result),
        result.result_digest,
    )
    declared = (
        expected.regime_state,
        expected.regime_score,
        expected.eligible,
        expected.ineligible,
        expected.blocked,
        expected.signals,
        expected.candidates,
        dict(expected.reason_summary),
        expected.result_digest,
    )
    if actual != declared:
        raise ScannerFixtureValidationError("scanner result does not match fixture expectations")


def _reason_summary(result: ScanResult) -> dict[str, int]:
    reasons: Counter[str] = Counter(result.regime.reasons)
    for collection in (result.eligibility, result.strategies, result.candidates):
        for item in collection:
            reasons.update(item.reasons)
    return dict(sorted(reasons.items()))


def _result_payload(result: ScanResult) -> dict[str, object]:
    payload = canonical_record(result)
    if not isinstance(payload, dict):
        raise TypeError("scan result must serialize to an object")
    result_payload = cast(dict[str, object], payload)
    result_payload["reason_summary"] = _reason_summary(result)
    return result_payload


class _ScannerRepositoryIngestionSink:
    def __init__(self, session: Session) -> None:
        self._repository = RepositoryIngestionSink(session)

    def payload_digest_for(self, ingestion_key: str) -> str | None:
        return self._repository.payload_digest_for(ingestion_key)

    def write_accepted(self, outcome: AcceptedIngestion) -> None:
        if isinstance(outcome.value, NormalizedProviderState):
            return
        self._repository.write_accepted(outcome)

    def write_rejected(self, outcome: RejectedIngestion) -> None:
        self._repository.write_rejected(outcome)


def _print_error(error: str, message: str) -> None:
    _print_json({"error": error, "message": message}, stream=sys.stderr)


def _print_json(payload: dict[str, object], *, stream: TextIO) -> None:
    print(json.dumps(payload, sort_keys=True, separators=(",", ":")), file=stream)


if __name__ == "__main__":
    raise SystemExit(main())
