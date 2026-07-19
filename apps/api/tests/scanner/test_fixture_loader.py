import hashlib
import json
import shutil
from datetime import date
from pathlib import Path
from typing import Any, cast

import pytest

from market_trader.market_calendar.adapter import XNYSCalendarAdapter
from market_trader.market_data.replay import ReplayEngine, VirtualReplayClock
from market_trader.market_data.sinks import InMemoryIngestionSink
from market_trader.scanner.fixtures import (
    ScannerFixtureDataset,
    ScannerFixtureValidationError,
    assemble_scanner_input,
)

FIXTURES = Path(__file__).parent / "fixtures"


def test_loads_versioned_scanner_fixture_and_expected_outcomes() -> None:
    dataset = ScannerFixtureDataset.load(FIXTURES / "minimal")

    assert dataset.manifest.dataset_id == "scanner-minimal"
    assert dataset.manifest.schema_version == "scanner-fixture-v1"
    assert dataset.manifest.as_of.isoformat() == "2026-07-17T15:35:00+00:00"
    assert dataset.manifest.session_date == date(2026, 7, 17)
    assert dataset.manifest.versions.fixture == "scanner-fixture-v1"
    assert set(dataset.manifest.configuration_hashes) == {
        "universe",
        "eligibility",
        "regime",
        "strategies",
        "scoring",
    }
    assert dataset.manifest.expected.blocked == 30
    assert dataset.manifest.expected.result_digest == "0" * 64
    assert [event.event_id for event in dataset.market.events] == ["quote-1"]
    assert len(dataset.supplemental.macro) == 1


def test_replay_and_assembly_reuse_normalized_market_records() -> None:
    dataset = ScannerFixtureDataset.load(FIXTURES / "minimal")
    sink = InMemoryIngestionSink()
    ReplayEngine(
        clock=VirtualReplayClock(),
        calendar=XNYSCalendarAdapter(start=date(2026, 1, 1), end=date(2027, 1, 1)),
        sink=sink,
    ).replay(dataset.market)

    scanner_input = assemble_scanner_input(dataset, sink.accepted)

    assert scanner_input.as_of == dataset.manifest.as_of
    assert scanner_input.versions == dataset.manifest.versions
    assert scanner_input.configuration_hashes == dataset.manifest.configuration_hashes
    assert scanner_input.supplemental_evidence == dataset.supplemental
    assert [symbol.symbol for symbol in scanner_input.symbols] == ["SPY"]
    assert scanner_input.symbols[0].quotes[0].symbol == "SPY"
    assert scanner_input.symbols[0].evidence[0].ingestion_key.startswith("ing_")
    assert scanner_input.symbols[0].attributes["quote_updating"] is True


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        ("scanner_fixture_schema_version", "scanner-fixture-v2", "unsupported"),
        ("as_of", "2026-07-17T15:35:00", "timezone-aware"),
        ("session_date", "2026-07-18", "XNYS session"),
    ],
)
def test_rejects_invalid_schema_and_temporal_contract(
    tmp_path: Path, field: str, value: str, message: str
) -> None:
    path = _copy_fixture(tmp_path)
    manifest = _manifest(path)
    manifest[field] = value
    _write_manifest(path, manifest)

    with pytest.raises(ScannerFixtureValidationError, match=message):
        ScannerFixtureDataset.load(path)


def test_rejects_as_of_from_a_different_xnys_session(tmp_path: Path) -> None:
    path = _copy_fixture(tmp_path)
    manifest = _manifest(path)
    manifest["as_of"] = "2026-07-20T15:35:00+00:00"
    _write_manifest(path, manifest)

    with pytest.raises(ScannerFixtureValidationError, match="does not match"):
        ScannerFixtureDataset.load(path)


def test_rejects_unknown_versions_and_invalid_configuration_hashes(
    tmp_path: Path,
) -> None:
    path = _copy_fixture(tmp_path)
    manifest = _manifest(path)
    _nested(manifest, "versions")["scoring"] = "candidate-scoring-v2"
    _write_manifest(path, manifest)
    with pytest.raises(ScannerFixtureValidationError, match="versions"):
        ScannerFixtureDataset.load(path)

    path = _copy_fixture(tmp_path, name="hashes")
    manifest = _manifest(path)
    _nested(manifest, "configuration_hashes")["scoring"] = "not-a-hash"
    _write_manifest(path, manifest)
    with pytest.raises(ScannerFixtureValidationError, match="hash"):
        ScannerFixtureDataset.load(path)


def test_rejects_filename_escape_missing_and_undeclared_files(tmp_path: Path) -> None:
    escaped = _copy_fixture(tmp_path, name="escaped")
    manifest = _manifest(escaped)
    _first_stream(manifest)["filename"] = "../market.ndjson"
    _write_manifest(escaped, manifest)
    with pytest.raises(ScannerFixtureValidationError, match="filename"):
        ScannerFixtureDataset.load(escaped)

    missing = _copy_fixture(tmp_path, name="missing")
    (missing / "market.ndjson").unlink()
    with pytest.raises(ScannerFixtureValidationError, match="missing"):
        ScannerFixtureDataset.load(missing)

    undeclared = _copy_fixture(tmp_path, name="undeclared")
    (undeclared / "extra.ndjson").write_text("", encoding="utf-8")
    with pytest.raises(ScannerFixtureValidationError, match="undeclared"):
        ScannerFixtureDataset.load(undeclared)


def test_rejects_hash_count_and_ingestion_order_mismatches(tmp_path: Path) -> None:
    path = _copy_fixture(tmp_path)
    with (path / "market.ndjson").open("a", encoding="utf-8") as stream:
        stream.write("\n")
    with pytest.raises(ScannerFixtureValidationError, match="SHA-256"):
        ScannerFixtureDataset.load(path)

    path = _copy_fixture(tmp_path, name="count")
    manifest = _manifest(path)
    _first_stream(manifest)["event_count"] = 2
    _write_manifest(path, manifest)
    with pytest.raises(ScannerFixtureValidationError, match="count"):
        ScannerFixtureDataset.load(path)

    path = _copy_fixture(tmp_path, name="order")
    records = _records(path / "market.ndjson")
    earlier = dict(records[0])
    earlier["event_id"] = "quote-earlier"
    earlier["ingested_at"] = "2026-07-17T15:34:54+00:00"
    _rewrite_stream(path, "market.ndjson", [records[0], earlier])
    with pytest.raises(ScannerFixtureValidationError, match="nondecreasing"):
        ScannerFixtureDataset.load(path)


def test_rejects_post_as_of_market_records(tmp_path: Path) -> None:
    path = _copy_fixture(tmp_path)
    records = _records(path / "market.ndjson")
    records[0]["observed_at"] = "2026-07-17T15:35:00.000001+00:00"
    _rewrite_stream(path, "market.ndjson", records)

    with pytest.raises(ScannerFixtureValidationError, match="after as_of"):
        ScannerFixtureDataset.load(path)


@pytest.mark.parametrize("filename", ["market.ndjson", "supplemental.ndjson"])
def test_rejects_sensitive_keys_without_echoing_values(tmp_path: Path, filename: str) -> None:
    path = _copy_fixture(tmp_path)
    records = _records(path / filename)
    target = records[0]["payload"] if filename == "market.ndjson" else records[0]
    cast(dict[str, object], target)["api_key"] = "must-not-appear"
    _rewrite_stream(path, filename, records)

    with pytest.raises(ScannerFixtureValidationError) as error:
        ScannerFixtureDataset.load(path)

    assert "sensitive" in str(error.value)
    assert "must-not-appear" not in str(error.value)


def test_rejects_sensitive_manifest_keys_without_echoing_values(tmp_path: Path) -> None:
    path = _copy_fixture(tmp_path)
    manifest = _manifest(path)
    manifest["api_key"] = "must-not-appear"
    _write_manifest(path, manifest)

    with pytest.raises(ScannerFixtureValidationError) as error:
        ScannerFixtureDataset.load(path)

    assert "sensitive" in str(error.value)
    assert "must-not-appear" not in str(error.value)


def test_rejects_malformed_json_without_echoing_content(tmp_path: Path) -> None:
    path = _copy_fixture(tmp_path)
    _rewrite_raw(path, "supplemental.ndjson", '{"secret-value"')

    with pytest.raises(ScannerFixtureValidationError) as error:
        ScannerFixtureDataset.load(path)

    assert "supplemental.ndjson:1" in str(error.value)
    assert "malformed JSON" in str(error.value)
    assert "secret-value" not in str(error.value)


def test_rejects_incomplete_expected_result_schema(tmp_path: Path) -> None:
    path = _copy_fixture(tmp_path)
    manifest = _manifest(path)
    del _nested(manifest, "expected")["signals"]
    _write_manifest(path, manifest)

    with pytest.raises(ScannerFixtureValidationError, match="expected"):
        ScannerFixtureDataset.load(path)


def _copy_fixture(tmp_path: Path, *, name: str = "minimal") -> Path:
    destination = tmp_path / name
    shutil.copytree(FIXTURES / "minimal", destination)
    return destination


def _manifest(path: Path) -> dict[str, object]:
    return cast(
        dict[str, object],
        json.loads((path / "manifest.json").read_text(encoding="utf-8")),
    )


def _nested(manifest: dict[str, object], key: str) -> dict[str, Any]:
    return cast(dict[str, Any], manifest[key])


def _first_stream(manifest: dict[str, object]) -> dict[str, Any]:
    return cast(list[dict[str, Any]], manifest["market_streams"])[0]


def _write_manifest(path: Path, manifest: dict[str, object]) -> None:
    (path / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")


def _records(path: Path) -> list[dict[str, object]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


def _rewrite_stream(path: Path, filename: str, records: list[dict[str, object]]) -> None:
    _rewrite_raw(
        path,
        filename,
        "\n".join(json.dumps(record, separators=(",", ":")) for record in records) + "\n",
    )


def _rewrite_raw(path: Path, filename: str, content: str) -> None:
    (path / filename).write_text(content, encoding="utf-8")
    digest = hashlib.sha256(content.encode()).hexdigest()
    manifest = _manifest(path)
    if filename == "supplemental.ndjson":
        supplemental = _nested(manifest, "supplemental")
        supplemental["sha256"] = digest
        supplemental["record_count"] = len(content.splitlines())
    else:
        stream = _first_stream(manifest)
        stream["sha256"] = digest
        stream["event_count"] = len(content.splitlines())
    _write_manifest(path, manifest)
