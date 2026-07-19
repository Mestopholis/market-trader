import hashlib
import json
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from pathlib import Path
from types import MappingProxyType
from typing import NoReturn, cast

from market_trader.catalysts.adapters.bls import _parse_calendar
from market_trader.catalysts.models import (
    CatalystPolicyVersions,
    CatalystProviderEvent,
    EventFamily,
    SourceFailure,
    SourceFailureKind,
)
from market_trader.catalysts.summaries import (
    SummaryProviderResponse,
    SummarySegmentInput,
)
from market_trader.domain.time import ensure_utc

MAX_FIXTURE_STREAM_BYTES = 2_097_152
FIXTURE_SCHEMA_VERSION = 1

_MANIFEST_KEYS = {
    "as_of",
    "dataset_id",
    "description",
    "expected_reason_digest",
    "expected_result_digest",
    "fixture_schema_version",
    "policy_hashes",
    "policy_versions",
    "scenarios",
    "streams",
}
_STREAM_KEYS = {"byte_count", "filename", "kind", "record_count", "sha256"}
_EVENT_KEYS = {
    "correlation_id",
    "event_family",
    "external_text",
    "ingested_at",
    "provider_event_id",
    "provider_schema_version",
    "published_at",
    "scheduled_for",
    "source_id",
    "source_reference",
    "structured_fields",
    "symbol_identity",
}
_FAILURE_KEYS = {"kind", "occurred_at", "reasons", "source_id"}
_SUMMARY_KEYS = {"generated_at", "provider_id", "segments"}
_SEGMENT_KEYS = {"observation_keys", "source_references", "text"}
_POLICY_KEYS = {"classification", "fixture", "risk", "source", "summary"}
_HASH_KEYS = {"classification", "risk", "sources", "summary"}
_SENSITIVE_FRAGMENTS = (
    "authorization",
    "cookie",
    "token",
    "secret",
    "password",
    "api_key",
    "account",
)


class CatalystFixtureValidationError(ValueError):
    pass


class FixtureStreamKind(StrEnum):
    PROVIDER_EVENTS = "provider_events"
    BLS_CALENDAR = "bls_calendar"
    SOURCE_FAILURES = "source_failures"
    SUMMARIES = "summaries"


type CatalystFixtureRecord = CatalystProviderEvent | SourceFailure | SummaryProviderResponse


@dataclass(frozen=True)
class CatalystFixtureStream:
    filename: str
    kind: FixtureStreamKind
    byte_count: int
    record_count: int
    sha256: str


@dataclass(frozen=True)
class CatalystFixtureManifest:
    dataset_id: str
    description: str
    fixture_schema_version: int
    as_of: datetime
    policy_versions: CatalystPolicyVersions
    policy_hashes: Mapping[str, str]
    scenarios: tuple[str, ...]
    streams: tuple[CatalystFixtureStream, ...]
    expected_result_digest: str | None
    expected_reason_digest: str | None

    def __post_init__(self) -> None:
        object.__setattr__(self, "as_of", ensure_utc(self.as_of))
        object.__setattr__(
            self,
            "policy_hashes",
            MappingProxyType(dict(sorted(self.policy_hashes.items()))),
        )


@dataclass(frozen=True)
class CatalystFixtureDataset:
    path: Path
    manifest: CatalystFixtureManifest
    records: tuple[CatalystFixtureRecord, ...]

    @property
    def events(self) -> tuple[CatalystProviderEvent, ...]:
        return tuple(item for item in self.records if isinstance(item, CatalystProviderEvent))

    @property
    def source_failures(self) -> tuple[SourceFailure, ...]:
        return tuple(item for item in self.records if isinstance(item, SourceFailure))

    @property
    def summary_responses(self) -> tuple[SummaryProviderResponse, ...]:
        return tuple(item for item in self.records if isinstance(item, SummaryProviderResponse))

    @classmethod
    def load(cls, path: Path | str) -> "CatalystFixtureDataset":
        root = Path(path)
        manifest = _load_manifest(root)
        _validate_declared_files(root, manifest)
        contents = _read_and_verify_streams(root, manifest)
        records: list[CatalystFixtureRecord] = []
        for stream, content in zip(manifest.streams, contents, strict=True):
            parsed = _parse_stream(manifest, stream, content)
            if len(parsed) != stream.record_count:
                _error(manifest.dataset_id, stream.filename, "record count mismatch")
            records.extend(parsed)
        return cls(path=root, manifest=manifest, records=tuple(records))


def _load_manifest(root: Path) -> CatalystFixtureManifest:
    path = root / "manifest.json"
    try:
        raw_value: object = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise CatalystFixtureValidationError(f"{root}: malformed manifest") from error
    raw = _mapping(raw_value, "manifest")
    _exact_keys(raw, _MANIFEST_KEYS, "manifest")
    if _contains_sensitive_key(raw):
        raise CatalystFixtureValidationError("manifest contains credential-like key")
    schema = _integer(raw["fixture_schema_version"], "fixture_schema_version")
    if schema != FIXTURE_SCHEMA_VERSION:
        raise CatalystFixtureValidationError("unsupported fixture schema")
    versions = _parse_versions(raw["policy_versions"])
    if versions != CatalystPolicyVersions():
        raise CatalystFixtureValidationError("unsupported policy versions")
    hashes = _parse_hashes(raw["policy_hashes"])
    streams = tuple(_parse_stream_descriptor(item) for item in _list(raw["streams"], "streams"))
    if not streams or len({item.filename for item in streams}) != len(streams):
        raise CatalystFixtureValidationError("manifest streams must be nonempty and unique")
    return CatalystFixtureManifest(
        dataset_id=_string(raw["dataset_id"], "dataset_id"),
        description=_string(raw["description"], "description"),
        fixture_schema_version=schema,
        as_of=_timestamp(raw["as_of"], "as_of"),
        policy_versions=versions,
        policy_hashes=hashes,
        scenarios=_string_tuple(raw["scenarios"], "scenarios"),
        streams=streams,
        expected_result_digest=_optional_digest(raw["expected_result_digest"]),
        expected_reason_digest=_optional_digest(raw["expected_reason_digest"]),
    )


def _parse_versions(value: object) -> CatalystPolicyVersions:
    raw = _mapping(value, "policy_versions")
    _exact_keys(raw, _POLICY_KEYS, "policy_versions")
    return CatalystPolicyVersions(
        source=_string(raw["source"], "policy source"),
        classification=_string(raw["classification"], "policy classification"),
        risk=_string(raw["risk"], "policy risk"),
        summary=_string(raw["summary"], "policy summary"),
        fixture=_string(raw["fixture"], "policy fixture"),
    )


def _parse_hashes(value: object) -> Mapping[str, str]:
    raw = _mapping(value, "policy_hashes")
    _exact_keys(raw, _HASH_KEYS, "policy_hashes")
    return MappingProxyType({key: _digest(raw[key], f"policy hash {key}") for key in sorted(raw)})


def _parse_stream_descriptor(value: object) -> CatalystFixtureStream:
    raw = _mapping(value, "stream")
    _exact_keys(raw, _STREAM_KEYS, "stream")
    filename = _string(raw["filename"], "stream filename")
    path = Path(filename)
    if path.name != filename or path.is_absolute() or path.suffix not in (".ndjson", ".ics"):
        raise CatalystFixtureValidationError("invalid stream filename")
    try:
        kind = FixtureStreamKind(_string(raw["kind"], "stream kind"))
    except ValueError as error:
        raise CatalystFixtureValidationError("unknown stream kind") from error
    if (kind is FixtureStreamKind.BLS_CALENDAR) != (path.suffix == ".ics"):
        raise CatalystFixtureValidationError("stream kind does not match filename")
    byte_count = _integer(raw["byte_count"], "byte_count")
    if byte_count > MAX_FIXTURE_STREAM_BYTES:
        raise CatalystFixtureValidationError("fixture stream exceeds size bound")
    return CatalystFixtureStream(
        filename=filename,
        kind=kind,
        byte_count=byte_count,
        record_count=_integer(raw["record_count"], "record_count"),
        sha256=_digest(raw["sha256"], "stream SHA-256"),
    )


def _validate_declared_files(root: Path, manifest: CatalystFixtureManifest) -> None:
    declared = {item.filename for item in manifest.streams}
    actual = {item.name for item in root.iterdir() if item.suffix in (".ndjson", ".ics")}
    if actual != declared:
        raise CatalystFixtureValidationError("fixture declared files do not match directory")


def _read_and_verify_streams(
    root: Path, manifest: CatalystFixtureManifest
) -> tuple[bytes, ...]:
    contents: list[bytes] = []
    for stream in manifest.streams:
        try:
            content = (root / stream.filename).read_bytes()
        except OSError as error:
            _error(manifest.dataset_id, stream.filename, "stream unreadable", cause=error)
        if len(content) > MAX_FIXTURE_STREAM_BYTES:
            _error(manifest.dataset_id, stream.filename, "fixture stream exceeds size bound")
        if len(content) != stream.byte_count:
            _error(manifest.dataset_id, stream.filename, "byte count mismatch")
        if hashlib.sha256(content).hexdigest() != stream.sha256:
            _error(manifest.dataset_id, stream.filename, "SHA-256 mismatch")
        contents.append(content)
    return tuple(contents)


def _parse_stream(
    manifest: CatalystFixtureManifest,
    stream: CatalystFixtureStream,
    content: bytes,
) -> tuple[CatalystFixtureRecord, ...]:
    if stream.kind is FixtureStreamKind.BLS_CALENDAR:
        try:
            events = _parse_calendar(content, as_of=manifest.as_of)
        except ValueError as error:
            _error(manifest.dataset_id, stream.filename, "invalid ICS", cause=error)
        if not events:
            _error(manifest.dataset_id, stream.filename, "invalid ICS")
        return events
    try:
        lines = content.decode("utf-8").splitlines()
    except UnicodeError as error:
        _error(manifest.dataset_id, stream.filename, "invalid UTF-8", cause=error)
    if len(lines) != stream.record_count:
        _error(manifest.dataset_id, stream.filename, "record count mismatch")
    records: list[CatalystFixtureRecord] = []
    for line_number, line in enumerate(lines, start=1):
        try:
            raw_value: object = json.loads(line)
        except json.JSONDecodeError as error:
            _error(
                manifest.dataset_id,
                stream.filename,
                "malformed JSON",
                line_number,
                error,
            )
        raw = _mapping(raw_value, "record")
        if _contains_sensitive_key(raw):
            _error(
                manifest.dataset_id,
                stream.filename,
                "record contains credential-like key",
                line_number,
            )
        try:
            if stream.kind is FixtureStreamKind.PROVIDER_EVENTS:
                records.append(_parse_event(raw))
            elif stream.kind is FixtureStreamKind.SOURCE_FAILURES:
                records.append(_parse_failure(raw))
            else:
                records.append(_parse_summary(raw))
        except (KeyError, TypeError, ValueError) as error:
            _error(
                manifest.dataset_id,
                stream.filename,
                "invalid record",
                line_number,
                error,
            )
    return tuple(records)


def _parse_event(raw: Mapping[str, object]) -> CatalystProviderEvent:
    _exact_keys(raw, _EVENT_KEYS, "event")
    scheduled = raw["scheduled_for"]
    return CatalystProviderEvent(
        source_id=_string(raw["source_id"], "source_id"),
        provider_event_id=_string(raw["provider_event_id"], "provider_event_id"),
        event_family=EventFamily(_string(raw["event_family"], "event_family")),
        provider_schema_version=_integer(raw["provider_schema_version"], "provider_schema_version"),
        published_at=_timestamp(raw["published_at"], "published_at"),
        ingested_at=_timestamp(raw["ingested_at"], "ingested_at"),
        scheduled_for=None if scheduled is None else _timestamp(scheduled, "scheduled_for"),
        symbol_identity=_optional_string(raw["symbol_identity"], "symbol_identity"),
        structured_fields=_mapping(raw["structured_fields"], "structured_fields"),
        external_text=_mapping(raw["external_text"], "external_text"),
        source_reference=_string(raw["source_reference"], "source_reference"),
        correlation_id=_string(raw["correlation_id"], "correlation_id"),
    )


def _parse_failure(raw: Mapping[str, object]) -> SourceFailure:
    _exact_keys(raw, _FAILURE_KEYS, "source failure")
    return SourceFailure(
        source_id=_string(raw["source_id"], "source_id"),
        kind=SourceFailureKind(_string(raw["kind"], "failure kind")),
        occurred_at=_timestamp(raw["occurred_at"], "occurred_at"),
        reasons=_string_tuple(raw["reasons"], "reasons"),
    )


def _parse_summary(raw: Mapping[str, object]) -> SummaryProviderResponse:
    _exact_keys(raw, _SUMMARY_KEYS, "summary")
    segments: list[SummarySegmentInput] = []
    for value in _list(raw["segments"], "segments"):
        segment = _mapping(value, "summary segment")
        _exact_keys(segment, _SEGMENT_KEYS, "summary segment")
        segments.append(
            SummarySegmentInput(
                text=_string(segment["text"], "summary text"),
                observation_keys=_string_tuple(segment["observation_keys"], "observation_keys"),
                source_references=_string_tuple(segment["source_references"], "source_references"),
            )
        )
    return SummaryProviderResponse(
        provider_id=_string(raw["provider_id"], "provider_id"),
        generated_at=_timestamp(raw["generated_at"], "generated_at"),
        segments=tuple(segments),
    )


def _exact_keys(raw: Mapping[str, object], expected: set[str], label: str) -> None:
    unknown = set(raw) - expected
    missing = expected - set(raw)
    if unknown:
        raise CatalystFixtureValidationError(f"{label} has unknown keys")
    if missing:
        raise CatalystFixtureValidationError(f"{label} has missing keys")


def _mapping(value: object, label: str) -> Mapping[str, object]:
    if not isinstance(value, dict) or not all(isinstance(key, str) for key in value):
        raise CatalystFixtureValidationError(f"invalid {label}")
    return cast(Mapping[str, object], value)


def _list(value: object, label: str) -> list[object]:
    if not isinstance(value, list):
        raise CatalystFixtureValidationError(f"invalid {label}")
    return value


def _string(value: object, label: str) -> str:
    if not isinstance(value, str) or not value or len(value) > 2_048:
        raise CatalystFixtureValidationError(f"invalid {label}")
    return value


def _optional_string(value: object, label: str) -> str | None:
    return None if value is None else _string(value, label)


def _string_tuple(value: object, label: str) -> tuple[str, ...]:
    return tuple(_string(item, label) for item in _list(value, label))


def _integer(value: object, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise CatalystFixtureValidationError(f"invalid {label}")
    return value


def _timestamp(value: object, label: str) -> datetime:
    if not isinstance(value, str):
        raise CatalystFixtureValidationError(f"invalid {label}")
    try:
        return ensure_utc(datetime.fromisoformat(value))
    except ValueError as error:
        raise CatalystFixtureValidationError(str(error)) from error


def _digest(value: object, label: str) -> str:
    digest = _string(value, label)
    if len(digest) != 64 or any(character not in "0123456789abcdef" for character in digest):
        raise CatalystFixtureValidationError(f"invalid {label}")
    return digest


def _optional_digest(value: object) -> str | None:
    return None if value is None else _digest(value, "expected digest")


def _contains_sensitive_key(value: object) -> bool:
    if isinstance(value, Mapping):
        for key, nested in value.items():
            normalized = str(key).casefold().replace("-", "_").replace(" ", "_")
            if any(fragment in normalized for fragment in _SENSITIVE_FRAGMENTS):
                return True
            if _contains_sensitive_key(nested):
                return True
    elif isinstance(value, list):
        return any(_contains_sensitive_key(item) for item in value)
    return False


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
    error = CatalystFixtureValidationError(f"{location}: {message}")
    if cause is not None:
        raise error from cause
    raise error
