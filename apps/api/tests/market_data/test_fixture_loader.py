import hashlib
import json
import shutil
from pathlib import Path
from typing import Any, cast

import pytest

from market_trader.market_data.fixtures import FixtureDataset, FixtureValidationError

FIXTURES = Path(__file__).parent / "fixtures"


def test_loads_events_in_manifest_stream_and_line_order() -> None:
    dataset = FixtureDataset.load(FIXTURES / "minimal")

    assert dataset.manifest.dataset_id == "minimal"
    assert [event.event_id for event in dataset.events] == ["quote-1", "quote-2"]
    assert dataset.events[0].source == "fixture"
    assert dataset.events[0].fixture_schema_version == 1


def test_rejects_stream_hash_mismatch(tmp_path: Path) -> None:
    dataset_path = copy_fixture(tmp_path)
    with (dataset_path / "quotes.ndjson").open("a", encoding="utf-8") as stream:
        stream.write("\n")

    with pytest.raises(FixtureValidationError, match="SHA-256 mismatch"):
        FixtureDataset.load(dataset_path)


def test_rejects_event_count_mismatch(tmp_path: Path) -> None:
    dataset_path = copy_fixture(tmp_path)
    manifest = read_manifest(dataset_path)
    _streams(manifest)[0]["event_count"] = 3
    write_manifest(dataset_path, manifest)

    with pytest.raises(FixtureValidationError, match="event count mismatch"):
        FixtureDataset.load(dataset_path)


def test_reports_malformed_json_without_raw_payload(tmp_path: Path) -> None:
    dataset_path = copy_fixture(tmp_path)
    rewrite_stream(dataset_path, ['{"event_id":"secret-value"'])

    with pytest.raises(FixtureValidationError) as error:
        FixtureDataset.load(dataset_path)

    assert "quotes.ndjson:1" in str(error.value)
    assert "malformed JSON" in str(error.value)
    assert "secret-value" not in str(error.value)


def test_rejects_unknown_fixture_schema(tmp_path: Path) -> None:
    dataset_path = copy_fixture(tmp_path)
    manifest = read_manifest(dataset_path)
    manifest["fixture_schema_version"] = 2
    write_manifest(dataset_path, manifest)

    with pytest.raises(FixtureValidationError, match="unsupported fixture schema"):
        FixtureDataset.load(dataset_path)


def test_rejects_event_with_wrong_stream_kind(tmp_path: Path) -> None:
    dataset_path = copy_fixture(tmp_path)
    events = read_events(dataset_path)
    events[0]["data_kind"] = "candle"
    rewrite_stream(dataset_path, [json.dumps(event, separators=(",", ":")) for event in events])

    with pytest.raises(FixtureValidationError, match="does not match declared data kind"):
        FixtureDataset.load(dataset_path)


def test_rejects_decreasing_ingestion_time(tmp_path: Path) -> None:
    dataset_path = copy_fixture(tmp_path)
    events = read_events(dataset_path)
    events[1]["ingested_at"] = "2026-07-17T14:29:59+00:00"
    rewrite_stream(dataset_path, [json.dumps(event, separators=(",", ":")) for event in events])

    with pytest.raises(FixtureValidationError, match="nondecreasing"):
        FixtureDataset.load(dataset_path)


def test_rejects_naive_timestamp(tmp_path: Path) -> None:
    dataset_path = copy_fixture(tmp_path)
    events = read_events(dataset_path)
    events[0]["observed_at"] = "2026-07-17T14:30:00"
    rewrite_stream(dataset_path, [json.dumps(event, separators=(",", ":")) for event in events])

    with pytest.raises(FixtureValidationError, match="timezone-aware"):
        FixtureDataset.load(dataset_path)


def test_rejects_undeclared_stream(tmp_path: Path) -> None:
    dataset_path = copy_fixture(tmp_path)
    (dataset_path / "extra.ndjson").write_text("", encoding="utf-8")

    with pytest.raises(FixtureValidationError, match="undeclared stream"):
        FixtureDataset.load(dataset_path)


def test_rejects_credential_like_payload_keys(tmp_path: Path) -> None:
    dataset_path = copy_fixture(tmp_path)
    events = read_events(dataset_path)
    payload = events[0]["payload"]
    assert isinstance(payload, dict)
    payload["Authorization"] = "Bearer must-not-appear"
    rewrite_stream(dataset_path, [json.dumps(event, separators=(",", ":")) for event in events])

    with pytest.raises(FixtureValidationError) as error:
        FixtureDataset.load(dataset_path)

    assert "credential-like key" in str(error.value)
    assert "must-not-appear" not in str(error.value)


def copy_fixture(tmp_path: Path) -> Path:
    destination = tmp_path / "minimal"
    shutil.copytree(FIXTURES / "minimal", destination)
    return destination


def read_manifest(dataset_path: Path) -> dict[str, object]:
    return cast(
        dict[str, object],
        json.loads((dataset_path / "manifest.json").read_text(encoding="utf-8")),
    )


def write_manifest(dataset_path: Path, manifest: dict[str, object]) -> None:
    (dataset_path / "manifest.json").write_text(
        json.dumps(manifest, indent=2) + "\n",
        encoding="utf-8",
    )


def read_events(dataset_path: Path) -> list[dict[str, object]]:
    return [
        json.loads(line)
        for line in (dataset_path / "quotes.ndjson").read_text(encoding="utf-8").splitlines()
    ]


def rewrite_stream(dataset_path: Path, lines: list[str]) -> None:
    content = "\n".join(lines) + "\n"
    (dataset_path / "quotes.ndjson").write_text(content, encoding="utf-8")
    manifest = read_manifest(dataset_path)
    stream = _streams(manifest)[0]
    stream["sha256"] = hashlib.sha256(content.encode("utf-8")).hexdigest()
    stream["event_count"] = len(lines)
    write_manifest(dataset_path, manifest)


def _streams(manifest: dict[str, object]) -> list[dict[str, Any]]:
    streams = manifest["streams"]
    assert isinstance(streams, list)
    return cast(list[dict[str, Any]], streams)
