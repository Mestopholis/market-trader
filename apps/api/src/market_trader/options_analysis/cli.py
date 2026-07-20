import argparse
import json
import sys
from collections.abc import Sequence
from pathlib import Path
from typing import TextIO, cast

from market_trader.options_analysis.fixtures import OptionsFixtureDataset
from market_trader.options_analysis.replay import replay_options_analysis
from market_trader.options_analysis.serialization import canonical_record


def main(argv: Sequence[str] | None = None) -> int:
    arguments = _parser().parse_args(argv)
    try:
        dataset = OptionsFixtureDataset.load(arguments.dataset)
        records = replay_options_analysis(dataset)
    except (OSError, UnicodeError, ValueError):
        _print_error("dataset_error", "options analysis fixture is invalid")
        return 2
    except Exception:
        _print_error("infrastructure_error", "options analysis operation failed")
        return 3

    payload = _summary_payload(dataset, record_count=len(records))
    payload.update({"command": arguments.command, "persistence": "memory"})
    if arguments.command == "analyze":
        payload["records"] = _sorted_records(records)
    _print_json(payload, stream=sys.stdout)
    return 0


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="options-analysis")
    commands = parser.add_subparsers(dest="command", required=True)
    for command in ("validate", "analyze"):
        subcommand = commands.add_parser(command)
        subcommand.add_argument("dataset", type=Path)
        if command == "analyze":
            subcommand.add_argument("--database-url")
    return parser


def _summary_payload(
    dataset: OptionsFixtureDataset,
    *,
    record_count: int,
) -> dict[str, object]:
    manifest = dataset.manifest
    return {
        "as_of": manifest["as_of"],
        "dataset_id": dataset.dataset_id,
        "expected_counts": manifest["expected_counts"],
        "expected_reason_summary": manifest["expected_reason_summary"],
        "expected_result_digest": manifest["expected_result_digest"],
        "policy_hash": manifest["policy_hash"],
        "policy_version": manifest["policy_version"],
        "record_count": record_count,
    }


def _sorted_records(records: tuple[dict[str, object], ...]) -> list[dict[str, object]]:
    canonical = []
    for record in records:
        value = canonical_record(record)
        if not isinstance(value, dict):
            raise TypeError("options analysis record must serialize to an object")
        canonical.append(cast(dict[str, object], value))
    return sorted(
        canonical,
        key=lambda record: json.dumps(record, sort_keys=True, separators=(",", ":")),
    )


def _print_error(error: str, message: str) -> None:
    _print_json({"error": error, "message": message}, stream=sys.stderr)


def _print_json(payload: dict[str, object], *, stream: TextIO) -> None:
    print(json.dumps(payload, sort_keys=True, separators=(",", ":")), file=stream)


if __name__ == "__main__":
    raise SystemExit(main())
