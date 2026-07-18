import hashlib
import json
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import NoReturn, cast

from market_trader.domain.time import ensure_utc
from market_trader.market_data.models import DataKind, ProviderEvent


class FixtureValidationError(ValueError):
    pass


@dataclass(frozen=True)
class FixtureExpectedCounts:
    accepted: int
    degraded: int
    stale: int
    quarantined: int
    deduplicated: int


@dataclass(frozen=True)
class FixtureStream:
    filename: str
    data_kind: DataKind
    sha256: str
    event_count: int


@dataclass(frozen=True)
class FixtureManifest:
    dataset_id: str
    description: str
    fixture_schema_version: int
    source: str
    configuration_version: str
    streams: tuple[FixtureStream, ...]
    expected_counts: FixtureExpectedCounts
    expected_result_digest: str | None


@dataclass(frozen=True)
class FixtureDataset:
    path: Path
    manifest: FixtureManifest
    events: tuple[ProviderEvent, ...]

    @classmethod
    def load(cls, path: Path | str) -> "FixtureDataset":
        dataset_path = Path(path)
        manifest = _load_manifest(dataset_path)
        _validate_declared_streams(dataset_path, manifest)

        events: list[ProviderEvent] = []
        last_ingested_at: datetime | None = None
        for stream in manifest.streams:
            stream_path = dataset_path / stream.filename
            content = stream_path.read_bytes()
            actual_hash = hashlib.sha256(content).hexdigest()
            if actual_hash != stream.sha256:
                _error(manifest.dataset_id, stream.filename, "SHA-256 mismatch")
            lines = content.decode("utf-8").splitlines()
            if len(lines) != stream.event_count:
                _error(manifest.dataset_id, stream.filename, "event count mismatch")

            for line_number, line in enumerate(lines, start=1):
                event = _parse_event(
                    line,
                    manifest=manifest,
                    stream=stream,
                    line_number=line_number,
                )
                if last_ingested_at is not None and event.ingested_at < last_ingested_at:
                    _error(
                        manifest.dataset_id,
                        stream.filename,
                        "ingestion timestamps must be nondecreasing",
                        line_number,
                    )
                last_ingested_at = event.ingested_at
                events.append(event)

        return cls(path=dataset_path, manifest=manifest, events=tuple(events))


def _load_manifest(dataset_path: Path) -> FixtureManifest:
    manifest_path = dataset_path / "manifest.json"
    if not manifest_path.is_file():
        raise FixtureValidationError(f"{dataset_path}: missing manifest.json")
    try:
        raw_value: object = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise FixtureValidationError(f"{dataset_path}: malformed manifest") from error
    raw = _mapping(raw_value, "manifest")

    schema_version = _integer(raw.get("fixture_schema_version"), "fixture_schema_version")
    if schema_version != 1:
        raise FixtureValidationError(f"{dataset_path}: unsupported fixture schema")
    dataset_id = _string(raw.get("dataset_id"), "dataset_id")
    raw_streams = _list(raw.get("streams"), "streams")
    streams = tuple(_parse_stream(item, dataset_id) for item in raw_streams)
    if not streams:
        raise FixtureValidationError(f"{dataset_id}: manifest requires at least one stream")
    if len({stream.filename for stream in streams}) != len(streams):
        raise FixtureValidationError(f"{dataset_id}: duplicate stream filename")

    raw_counts = _mapping(raw.get("expected_counts"), "expected_counts")
    expected_counts = FixtureExpectedCounts(
        accepted=_count(raw_counts, "accepted"),
        degraded=_count(raw_counts, "degraded"),
        stale=_count(raw_counts, "stale"),
        quarantined=_count(raw_counts, "quarantined"),
        deduplicated=_count(raw_counts, "deduplicated"),
    )
    expected_digest = raw.get("expected_result_digest")
    if expected_digest is not None and not isinstance(expected_digest, str):
        raise FixtureValidationError(f"{dataset_id}: invalid expected_result_digest")
    return FixtureManifest(
        dataset_id=dataset_id,
        description=_string(raw.get("description"), "description"),
        fixture_schema_version=schema_version,
        source=_string(raw.get("source"), "source"),
        configuration_version=_string(
            raw.get("configuration_version"),
            "configuration_version",
        ),
        streams=streams,
        expected_counts=expected_counts,
        expected_result_digest=expected_digest,
    )


def _parse_stream(value: object, dataset_id: str) -> FixtureStream:
    raw = _mapping(value, "stream")
    filename = _string(raw.get("filename"), "filename")
    if Path(filename).name != filename or Path(filename).suffix != ".ndjson":
        raise FixtureValidationError(f"{dataset_id}: invalid stream filename")
    kind_value = _string(raw.get("data_kind"), "data_kind")
    try:
        data_kind = DataKind(kind_value)
    except ValueError as error:
        raise FixtureValidationError(f"{dataset_id}/{filename}: unknown data kind") from error
    digest = _string(raw.get("sha256"), "sha256")
    if len(digest) != 64 or any(character not in "0123456789abcdef" for character in digest):
        raise FixtureValidationError(f"{dataset_id}/{filename}: invalid SHA-256")
    return FixtureStream(
        filename=filename,
        data_kind=data_kind,
        sha256=digest,
        event_count=_count(raw, "event_count"),
    )


def _validate_declared_streams(dataset_path: Path, manifest: FixtureManifest) -> None:
    declared = {stream.filename for stream in manifest.streams}
    actual = {path.name for path in dataset_path.glob("*.ndjson")}
    undeclared = actual - declared
    if undeclared:
        raise FixtureValidationError(
            f"{manifest.dataset_id}: undeclared stream {sorted(undeclared)[0]}"
        )
    missing = declared - actual
    if missing:
        raise FixtureValidationError(
            f"{manifest.dataset_id}: missing stream {sorted(missing)[0]}"
        )


def _parse_event(
    line: str,
    *,
    manifest: FixtureManifest,
    stream: FixtureStream,
    line_number: int,
) -> ProviderEvent:
    try:
        raw_value: object = json.loads(line)
    except json.JSONDecodeError as error:
        _error(manifest.dataset_id, stream.filename, "malformed JSON", line_number, error)
    raw = _mapping(raw_value, "event")
    kind_value = _string(raw.get("data_kind"), "data_kind")
    try:
        event_kind = DataKind(kind_value)
    except ValueError as error:
        _error(manifest.dataset_id, stream.filename, "unknown data kind", line_number, error)
    if event_kind is not stream.data_kind:
        _error(
            manifest.dataset_id,
            stream.filename,
            "event does not match declared data kind",
            line_number,
        )
    observed_at = _timestamp(
        raw.get("observed_at"), manifest.dataset_id, stream.filename, line_number
    )
    ingested_at = _timestamp(
        raw.get("ingested_at"), manifest.dataset_id, stream.filename, line_number
    )
    payload = _mapping(raw.get("payload"), "payload")
    if _contains_sensitive_key(payload):
        _error(
            manifest.dataset_id,
            stream.filename,
            "payload contains credential-like key",
            line_number,
        )
    return ProviderEvent(
        source=manifest.source,
        event_id=_string(raw.get("event_id"), "event_id"),
        data_kind=event_kind,
        observed_at=observed_at,
        ingested_at=ingested_at,
        payload=payload,
        fixture_schema_version=manifest.fixture_schema_version,
        configuration_version=manifest.configuration_version,
        correlation_id=f"replay:{manifest.dataset_id}:{line_number}",
    )


def _timestamp(
    value: object,
    dataset_id: str,
    filename: str,
    line_number: int,
) -> datetime:
    if not isinstance(value, str):
        _error(dataset_id, filename, "invalid timestamp", line_number)
    try:
        return ensure_utc(datetime.fromisoformat(value))
    except ValueError as error:
        _error(dataset_id, filename, str(error), line_number, error)


def _contains_sensitive_key(value: object) -> bool:
    if isinstance(value, Mapping):
        for key, nested in value.items():
            normalized = str(key).casefold().replace("-", "_").replace(" ", "_")
            if any(
                fragment in normalized
                for fragment in (
                    "authorization",
                    "cookie",
                    "token",
                    "secret",
                    "password",
                    "api_key",
                    "account",
                )
            ):
                return True
            if _contains_sensitive_key(nested):
                return True
    elif isinstance(value, list):
        return any(_contains_sensitive_key(item) for item in value)
    return False


def _mapping(value: object, field: str) -> Mapping[str, object]:
    if not isinstance(value, dict) or not all(isinstance(key, str) for key in value):
        raise FixtureValidationError(f"invalid {field}")
    return cast(Mapping[str, object], value)


def _list(value: object, field: str) -> list[object]:
    if not isinstance(value, list):
        raise FixtureValidationError(f"invalid {field}")
    return cast(list[object], value)


def _string(value: object, field: str) -> str:
    if not isinstance(value, str) or not value:
        raise FixtureValidationError(f"invalid {field}")
    return value


def _integer(value: object, field: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise FixtureValidationError(f"invalid {field}")
    return value


def _count(value: Mapping[str, object], field: str) -> int:
    result = _integer(value.get(field), field)
    if result < 0:
        raise FixtureValidationError(f"invalid {field}")
    return result


def _error(
    dataset_id: str,
    filename: str,
    message: str,
    line_number: int | None = None,
    cause: Exception | None = None,
) -> NoReturn:
    location = f"{dataset_id}/{filename}"
    if line_number is not None:
        location = f"{location}:{line_number}"
    error = FixtureValidationError(f"{location}: {message}")
    if cause is not None:
        raise error from cause
    raise error
