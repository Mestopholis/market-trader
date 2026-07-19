import argparse
import contextlib
import io
import json
import sys
import time
from collections.abc import Sequence
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import TextIO

import httpx
from alembic.util.exc import CommandError
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from market_trader.catalysts.adapters.bls import BlsPublicAdapter
from market_trader.catalysts.adapters.sec import SecEdgarAdapter
from market_trader.catalysts.configuration import (
    CatalystConfiguration,
    load_catalyst_configuration,
)
from market_trader.catalysts.fixtures import (
    CatalystFixtureDataset,
    CatalystFixtureValidationError,
)
from market_trader.catalysts.models import SourceFailure, SourceRunResult, SourceState
from market_trader.catalysts.providers import (
    EconomicReleaseRequest,
    ProviderBatch,
    SecFilingRequest,
)
from market_trader.catalysts.replay import (
    CatalystReplayEngine,
    CatalystReplayMismatchError,
    CatalystReplayResult,
    InMemoryCatalystReplaySink,
    VirtualCatalystClock,
)
from market_trader.catalysts.serialization import stable_digest
from market_trader.catalysts.sinks import CatalystPersistenceError, RepositoryCatalystSink
from market_trader.db.engine import create_engine_from_url
from market_trader.db.migrations import upgrade_to_head
from market_trader.market_calendar.adapter import XNYSCalendarAdapter
from market_trader.repositories.catalysts import CatalystPersistenceConflict

_DEFAULT_CONFIGURATION = Path("config/catalysts")


def main(argv: Sequence[str] | None = None) -> int:
    arguments = _parser().parse_args(argv)
    try:
        configuration = load_catalyst_configuration(arguments.config)
        if arguments.command == "fetch":
            outcome = _fetch_source(arguments, configuration)
            if isinstance(outcome, SourceFailure):
                _print_error("source_error", "catalyst source unavailable")
                return 4
            _print_json(_fetch_payload(arguments.source, outcome), stream=sys.stdout)
            return 0
        dataset = CatalystFixtureDataset.load(arguments.dataset)
        result = _replay(dataset, configuration)
    except (CatalystFixtureValidationError, CatalystReplayMismatchError, OSError, ValueError):
        _print_error("dataset_error", "catalyst dataset validation failed")
        return 2
    except Exception:
        _print_error("infrastructure_error", "catalyst operation failed")
        return 3

    persistence = "memory"
    if arguments.command == "replay" and arguments.database_url is not None:
        try:
            _persist(dataset, result, arguments.database_url)
        except (
            CommandError,
            CatalystPersistenceConflict,
            CatalystPersistenceError,
            OSError,
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
    parser = argparse.ArgumentParser(prog="catalysts")
    commands = parser.add_subparsers(dest="command", required=True)
    for name in ("validate", "replay"):
        command = commands.add_parser(name)
        command.add_argument("dataset", type=Path)
        command.add_argument("--config", type=Path, default=_DEFAULT_CONFIGURATION)
        if name == "replay":
            command.add_argument("--database-url")
    fetch = commands.add_parser("fetch")
    fetch.add_argument("source", choices=("sec", "bls"))
    fetch.add_argument("--as-of", required=True, type=_aware_datetime)
    fetch.add_argument("--config", type=Path, default=_DEFAULT_CONFIGURATION)
    fetch.add_argument("--symbols", nargs="+")
    fetch.add_argument("--sec-contact")
    return parser


def _replay(
    dataset: CatalystFixtureDataset,
    configuration: CatalystConfiguration,
) -> CatalystReplayResult:
    reference = dataset.manifest.as_of.date()
    return CatalystReplayEngine(
        clock=VirtualCatalystClock(),
        calendar=XNYSCalendarAdapter(
            start=reference - timedelta(days=370),
            end=reference + timedelta(days=370),
        ),
        configuration=configuration,
        sink=InMemoryCatalystReplaySink(),
    ).replay(dataset)


def _persist(
    dataset: CatalystFixtureDataset,
    result: CatalystReplayResult,
    database_url: str,
) -> None:
    with contextlib.redirect_stderr(io.StringIO()):
        upgrade_to_head(database_url)
    engine = create_engine_from_url(database_url)
    try:
        source_result = SourceRunResult(
            run_key=f"catalyst:{dataset.manifest.dataset_id}:{result.result_digest}",
            source_id=f"fixture:{dataset.manifest.dataset_id}",
            as_of=dataset.manifest.as_of,
            state=SourceState.AVAILABLE,
            observations=result.observations,
            quarantined=result.quarantined_outcomes,
            decisions=result.decisions,
            summaries=result.summaries,
            reasons=tuple(reason for reason, _count in result.reasons),
            result_digest=result.result_digest,
        )
        with Session(engine) as session, session.begin():
            RepositoryCatalystSink(session).persist(source_result)
    finally:
        engine.dispose()


class _AllowLimiter:
    def acquire(self, source_id: str) -> bool:
        return bool(source_id)


def _fetch_source(
    arguments: argparse.Namespace,
    configuration: CatalystConfiguration,
) -> ProviderBatch | SourceFailure:
    with httpx.Client(follow_redirects=False, timeout=15.0) as client:
        if arguments.source == "sec":
            contact = arguments.sec_contact
            if not isinstance(contact, str) or "@" not in contact:
                raise ValueError("SEC contact is required")
            symbols = tuple(arguments.symbols or configuration.sources.company_ciks)
            return SecEdgarAdapter(
                client=client,
                configuration=configuration,
                user_agent=f"Market-Trader/0.1 {contact}",
                limiter=_AllowLimiter(),
                sleeper=time.sleep,
            ).sec_filings(SecFilingRequest(as_of=arguments.as_of, symbols=symbols))
        return BlsPublicAdapter(
            client=client,
            configuration=configuration,
            limiter=_AllowLimiter(),
            sleeper=time.sleep,
        ).economic_releases(
            EconomicReleaseRequest(
                as_of=arguments.as_of,
                series_ids=tuple(configuration.sources.bls_series.values()),
            )
        )


def _result_payload(result: CatalystReplayResult) -> dict[str, object]:
    return {
        "accepted": result.accepted,
        "decisions": len(result.decisions),
        "deduplicated": result.deduplicated,
        "quarantined": result.quarantined,
        "reason_digest": result.reason_digest,
        "reasons": dict(result.reasons),
        "result_digest": result.result_digest,
        "risk_windows": len(result.risk_windows),
        "source_failures": result.source_failures,
        "source_recoveries": result.source_recoveries,
        "summaries": len(result.summaries),
    }


def _fetch_payload(source: str, outcome: ProviderBatch) -> dict[str, object]:
    return {
        "as_of": outcome.as_of.isoformat(),
        "command": "fetch",
        "event_count": len(outcome.events),
        "result_digest": stable_digest(outcome),
        "source": source,
    }


def _aware_datetime(value: str) -> datetime:
    parsed = datetime.fromisoformat(value)
    return parsed.astimezone(UTC) if parsed.tzinfo else _raise_as_of()


def _raise_as_of() -> datetime:
    raise argparse.ArgumentTypeError("as-of must be timezone-aware")


def _print_error(error: str, message: str) -> None:
    _print_json({"error": error, "message": message}, stream=sys.stderr)


def _print_json(payload: dict[str, object], *, stream: TextIO) -> None:
    print(json.dumps(payload, sort_keys=True, separators=(",", ":")), file=stream)


if __name__ == "__main__":
    raise SystemExit(main())
