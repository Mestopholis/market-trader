import argparse
import contextlib
import io
import json
import sys
from collections.abc import Sequence
from datetime import timedelta
from pathlib import Path
from typing import TextIO

from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from market_trader.db.engine import create_engine_from_url
from market_trader.db.migrations import upgrade_to_head
from market_trader.market_calendar.adapter import XNYSCalendarAdapter
from market_trader.market_data.fixtures import FixtureDataset, FixtureValidationError
from market_trader.market_data.replay import ReplayEngine, ReplayResult, VirtualReplayClock
from market_trader.market_data.sinks import (
    InMemoryIngestionSink,
    ReplayInfrastructureError,
    RepositoryIngestionSink,
)


def main(argv: Sequence[str] | None = None) -> int:
    arguments = _parser().parse_args(argv)
    try:
        dataset = FixtureDataset.load(arguments.dataset)
        result = _validate(dataset)
        persistence = "memory"
        if arguments.command == "replay" and arguments.database_url is not None:
            _persist(dataset, arguments.database_url)
            persistence = "database"
    except FixtureValidationError as error:
        _print_error("dataset_error", str(error))
        return 2
    except ReplayInfrastructureError as error:
        _print_error("infrastructure_error", str(error))
        return 3
    except (OSError, SQLAlchemyError):
        _print_error("infrastructure_error", "database operation failed")
        return 3

    payload: dict[str, object] = {
        "accepted": result.accepted,
        "command": arguments.command,
        "dataset_id": result.dataset_id,
        "deduplicated": result.deduplicated,
        "degraded": result.degraded,
        "quarantined": result.quarantined,
        "reasons": dict(result.reasons),
        "result_digest": result.result_digest,
        "stale": result.stale,
    }
    if arguments.command == "replay":
        payload["persistence"] = persistence
    _print_json(payload, stream=sys.stdout)
    return 0


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="market-data")
    commands = parser.add_subparsers(dest="command", required=True)

    validate = commands.add_parser("validate")
    validate.add_argument("dataset", type=Path)

    replay = commands.add_parser("replay")
    replay.add_argument("dataset", type=Path)
    replay.add_argument("--database-url")
    return parser


def _validate(dataset: FixtureDataset) -> ReplayResult:
    result = _replay(dataset, InMemoryIngestionSink())
    if result.counts != dataset.manifest.expected_counts:
        raise FixtureValidationError(
            f"{dataset.manifest.dataset_id}: replay counts do not match manifest"
        )
    expected_digest = dataset.manifest.expected_result_digest
    if expected_digest is not None and result.result_digest != expected_digest:
        raise FixtureValidationError(
            f"{dataset.manifest.dataset_id}: replay digest does not match manifest"
        )
    return result


def _persist(dataset: FixtureDataset, database_url: str) -> None:
    with contextlib.redirect_stderr(io.StringIO()):
        upgrade_to_head(database_url)
    engine = create_engine_from_url(database_url)
    try:
        with Session(engine) as session:
            try:
                _replay(dataset, RepositoryIngestionSink(session))
                session.commit()
            except Exception:
                session.rollback()
                raise
    finally:
        engine.dispose()


def _replay(
    dataset: FixtureDataset,
    sink: InMemoryIngestionSink | RepositoryIngestionSink,
) -> ReplayResult:
    event_dates = [event.observed_at.date() for event in dataset.events]
    start = min(event_dates) - timedelta(days=370)
    end = max(event_dates) + timedelta(days=370)
    return ReplayEngine(
        clock=VirtualReplayClock(),
        calendar=XNYSCalendarAdapter(start=start, end=end),
        sink=sink,
    ).replay(dataset)


def _print_error(error: str, message: str) -> None:
    _print_json({"error": error, "message": message}, stream=sys.stderr)


def _print_json(payload: dict[str, object], *, stream: TextIO) -> None:
    print(json.dumps(payload, sort_keys=True, separators=(",", ":")), file=stream)


if __name__ == "__main__":
    raise SystemExit(main())
