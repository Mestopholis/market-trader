import hashlib
import json
import shutil
from datetime import UTC, datetime
from pathlib import Path
from typing import cast

import pytest

from market_trader.catalysts.fixtures import (
    CatalystFixtureDataset,
    CatalystFixtureValidationError,
    FixtureStreamKind,
)
from market_trader.catalysts.models import CatalystProviderEvent, EventFamily

FIXTURES = Path(__file__).parent / "fixtures"


def test_loads_strict_manifest_and_preserves_stream_order() -> None:
    dataset = CatalystFixtureDataset.load(FIXTURES / "minimal")

    assert dataset.manifest.dataset_id == "minimal-catalysts"
    assert dataset.manifest.as_of == datetime(2026, 7, 17, 15, 0, tzinfo=UTC)
    assert tuple(dataset.manifest.policy_hashes) == (
        "classification",
        "risk",
        "sources",
        "summary",
    )
    assert tuple(stream.kind for stream in dataset.manifest.streams) == (
        FixtureStreamKind.PROVIDER_EVENTS,
        FixtureStreamKind.BLS_CALENDAR,
    )
    assert tuple(record.provider_event_id for record in dataset.events) == (
        "company-1",
        "schedule:cpi-july-2026:consumer_price_index",
    )
    assert all(isinstance(record, CatalystProviderEvent) for record in dataset.records)
    assert dataset.events[1].event_family is EventFamily.ECONOMIC_RELEASE


def test_rejects_unknown_or_missing_manifest_keys(tmp_path: Path) -> None:
    dataset_path = _copy_fixture(tmp_path)
    manifest = _manifest(dataset_path)
    manifest["unexpected"] = True
    _write_manifest(dataset_path, manifest)

    with pytest.raises(CatalystFixtureValidationError, match="manifest has unknown"):
        CatalystFixtureDataset.load(dataset_path)


def test_rejects_policy_version_or_hash_drift(tmp_path: Path) -> None:
    dataset_path = _copy_fixture(tmp_path)
    manifest = _manifest(dataset_path)
    manifest["policy_versions"]["risk"] = "event-risk-policy-v2"  # type: ignore[index]
    _write_manifest(dataset_path, manifest)

    with pytest.raises(CatalystFixtureValidationError, match="policy versions"):
        CatalystFixtureDataset.load(dataset_path)


def test_rejects_naive_as_of_and_confined_filename(tmp_path: Path) -> None:
    dataset_path = _copy_fixture(tmp_path)
    manifest = _manifest(dataset_path)
    manifest["as_of"] = "2026-07-17T15:00:00"
    _write_manifest(dataset_path, manifest)
    with pytest.raises(CatalystFixtureValidationError, match="timezone-aware"):
        CatalystFixtureDataset.load(dataset_path)

    manifest["as_of"] = "2026-07-17T15:00:00+00:00"
    manifest["streams"][0]["filename"] = "../events.ndjson"  # type: ignore[index]
    _write_manifest(dataset_path, manifest)
    with pytest.raises(CatalystFixtureValidationError, match="stream filename"):
        CatalystFixtureDataset.load(dataset_path)


def test_verifies_size_hash_and_count_before_parsing(tmp_path: Path) -> None:
    dataset_path = _copy_fixture(tmp_path)
    stream = dataset_path / "events.ndjson"
    stream.write_bytes(stream.read_bytes() + b"\n")

    with pytest.raises(CatalystFixtureValidationError, match="byte count mismatch"):
        CatalystFixtureDataset.load(dataset_path)

    _refresh_stream(dataset_path, "events.ndjson", record_count=3)
    with pytest.raises(CatalystFixtureValidationError, match="record count mismatch"):
        CatalystFixtureDataset.load(dataset_path)


def test_malformed_json_diagnostic_never_echoes_line(tmp_path: Path) -> None:
    dataset_path = _copy_fixture(tmp_path)
    secret = '{"password":"must-not-appear"'
    (dataset_path / "events.ndjson").write_text(secret + "\n", encoding="utf-8")
    _refresh_stream(dataset_path, "events.ndjson", record_count=1)

    with pytest.raises(CatalystFixtureValidationError) as error:
        CatalystFixtureDataset.load(dataset_path)

    assert "events.ndjson:1: malformed JSON" in str(error.value)
    assert "must-not-appear" not in str(error.value)


def test_rejects_unknown_stream_kind_and_invalid_ics(tmp_path: Path) -> None:
    dataset_path = _copy_fixture(tmp_path)
    manifest = _manifest(dataset_path)
    manifest["streams"][0]["kind"] = "unknown"  # type: ignore[index]
    _write_manifest(dataset_path, manifest)
    with pytest.raises(CatalystFixtureValidationError, match="unknown stream kind"):
        CatalystFixtureDataset.load(dataset_path)

    dataset_path = _copy_fixture(tmp_path, name="invalid-ics")
    (dataset_path / "bls-calendar.ics").write_text("not a calendar\n", encoding="utf-8")
    _refresh_stream(dataset_path, "bls-calendar.ics", record_count=1)
    with pytest.raises(CatalystFixtureValidationError, match="invalid ICS"):
        CatalystFixtureDataset.load(dataset_path)


def test_rejects_credentials_and_account_identifiers(tmp_path: Path) -> None:
    dataset_path = _copy_fixture(tmp_path)
    records = _event_records(dataset_path)
    records[0]["structured_fields"]["account_id"] = "must-not-appear"  # type: ignore[index]
    _write_events(dataset_path, records)

    with pytest.raises(CatalystFixtureValidationError) as error:
        CatalystFixtureDataset.load(dataset_path)

    assert "credential-like key" in str(error.value)
    assert "must-not-appear" not in str(error.value)


def _copy_fixture(tmp_path: Path, *, name: str = "minimal") -> Path:
    destination = tmp_path / name
    shutil.copytree(FIXTURES / "minimal", destination)
    return destination


def _manifest(path: Path) -> dict[str, object]:
    return cast(
        dict[str, object],
        json.loads((path / "manifest.json").read_text(encoding="utf-8")),
    )


def _write_manifest(path: Path, manifest: dict[str, object]) -> None:
    (path / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")


def _refresh_stream(path: Path, filename: str, *, record_count: int) -> None:
    content = (path / filename).read_bytes()
    manifest = _manifest(path)
    streams = cast(list[dict[str, object]], manifest["streams"])
    stream = next(item for item in streams if item["filename"] == filename)
    stream["byte_count"] = len(content)
    stream["sha256"] = hashlib.sha256(content).hexdigest()
    stream["record_count"] = record_count
    _write_manifest(path, manifest)


def _event_records(path: Path) -> list[dict[str, object]]:
    return [
        json.loads(line)
        for line in (path / "events.ndjson").read_text(encoding="utf-8").splitlines()
    ]


def _write_events(path: Path, records: list[dict[str, object]]) -> None:
    content = "\n".join(json.dumps(record) for record in records) + "\n"
    (path / "events.ndjson").write_text(content, encoding="utf-8")
    _refresh_stream(path, "events.ndjson", record_count=len(records))
