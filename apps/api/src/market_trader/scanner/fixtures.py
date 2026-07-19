import hashlib
import json
from collections import defaultdict
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from decimal import Decimal, InvalidOperation
from pathlib import Path
from types import MappingProxyType
from typing import NoReturn, cast

from market_trader.domain.time import ensure_utc
from market_trader.market_calendar.adapter import XNYSCalendarAdapter
from market_trader.market_data.fixtures import (
    FixtureDataset,
    FixtureExpectedCounts,
    FixtureManifest,
    FixtureStream,
)
from market_trader.market_data.models import (
    AdjustmentState,
    DataKind,
    NormalizedCandle,
    NormalizedCorporateAction,
    NormalizedProviderState,
    NormalizedQuote,
    ProviderEvent,
)
from market_trader.market_data.sinks import AcceptedIngestion
from market_trader.scanner.evidence import (
    EvidenceValidationError,
    SupplementalEvidence,
    parse_supplemental_evidence,
)
from market_trader.scanner.models import EvidenceRef, PolicyVersions, ScannerInput, SymbolInput

_HASH_KEYS = {"universe", "eligibility", "regime", "strategies", "scoring"}
_SENSITIVE_FRAGMENTS = (
    "authorization",
    "cookie",
    "token",
    "secret",
    "password",
    "api_key",
    "account",
)


class ScannerFixtureValidationError(ValueError):
    pass


@dataclass(frozen=True)
class ScannerSupplementalFile:
    filename: str
    sha256: str
    record_count: int


@dataclass(frozen=True)
class ScannerExpectedResult:
    regime_state: str
    regime_score: Decimal
    eligible: int
    ineligible: int
    blocked: int
    signals: int
    candidates: int
    reason_summary: Mapping[str, int]
    result_digest: str


@dataclass(frozen=True)
class ScannerFixtureManifest:
    dataset_id: str
    description: str
    schema_version: str
    as_of: datetime
    session_date: date
    source: str
    market_configuration_version: str
    versions: PolicyVersions
    configuration_hashes: Mapping[str, str]
    market_streams: tuple[FixtureStream, ...]
    supplemental: ScannerSupplementalFile
    expected: ScannerExpectedResult


@dataclass(frozen=True)
class ScannerFixtureDataset:
    path: Path
    manifest: ScannerFixtureManifest
    market: FixtureDataset
    supplemental: SupplementalEvidence

    @classmethod
    def load(cls, path: Path | str) -> "ScannerFixtureDataset":
        dataset_path = Path(path)
        raw = _load_manifest(dataset_path)
        if _contains_sensitive_key(raw):
            raise ScannerFixtureValidationError(f"{dataset_path}: manifest contains sensitive key")
        manifest = _parse_manifest(raw, dataset_path)
        _validate_files(dataset_path, manifest)
        events = _load_market_events(dataset_path, manifest)
        supplemental = _load_supplemental(dataset_path, manifest)
        market_manifest = FixtureManifest(
            dataset_id=manifest.dataset_id,
            description=manifest.description,
            fixture_schema_version=1,
            source=manifest.source,
            configuration_version=manifest.market_configuration_version,
            streams=manifest.market_streams,
            expected_counts=FixtureExpectedCounts(
                accepted=sum(stream.event_count for stream in manifest.market_streams),
                degraded=0,
                stale=0,
                quarantined=0,
                deduplicated=0,
            ),
            expected_result_digest=None,
        )
        return cls(
            path=dataset_path,
            manifest=manifest,
            market=FixtureDataset(
                path=dataset_path,
                manifest=market_manifest,
                events=events,
            ),
            supplemental=supplemental,
        )


def assemble_scanner_input(
    dataset: ScannerFixtureDataset,
    accepted: Sequence[AcceptedIngestion],
) -> ScannerInput:
    grouped: dict[str, list[AcceptedIngestion]] = defaultdict(list)
    provider_states: list[NormalizedProviderState] = []
    for outcome in accepted:
        value = outcome.value
        if isinstance(value, NormalizedProviderState):
            provider_states.append(value)
        elif isinstance(value, (NormalizedQuote, NormalizedCandle, NormalizedCorporateAction)):
            grouped[value.symbol].append(outcome)

    symbols: list[SymbolInput] = []
    for symbol in sorted(grouped):
        outcomes = grouped[symbol]
        quotes = tuple(
            outcome.value for outcome in outcomes if isinstance(outcome.value, NormalizedQuote)
        )
        candles = tuple(
            outcome.value for outcome in outcomes if isinstance(outcome.value, NormalizedCandle)
        )
        actions = tuple(
            outcome.value
            for outcome in outcomes
            if isinstance(outcome.value, NormalizedCorporateAction)
        )
        references = tuple(_evidence_ref(outcome) for outcome in outcomes)
        halted = any(
            "halt" in code.casefold() for quote in quotes for code in quote.condition_codes
        )
        symbols.append(
            SymbolInput(
                symbol=symbol,
                daily_candles=tuple(candle for candle in candles if candle.interval.value == "1d"),
                intraday_candles=tuple(
                    candle for candle in candles if candle.interval.value == "1m"
                ),
                quotes=quotes,
                provider_states=tuple(provider_states),
                corporate_actions=actions,
                evidence=references,
                attributes={
                    "symbol_active": True,
                    "halted": halted,
                    "quote_updating": bool(quotes),
                    "adjustment_supported": all(
                        candle.adjustment is AdjustmentState.ADJUSTED for candle in candles
                    ),
                    "corporate_actions_resolved": not actions,
                },
            )
        )
    manifest = dataset.manifest
    return ScannerInput(
        as_of=manifest.as_of,
        session_date=manifest.session_date,
        versions=manifest.versions,
        symbols=tuple(symbols),
        supplemental_evidence=dataset.supplemental,
        configuration_hashes=manifest.configuration_hashes,
    )


def _load_manifest(dataset_path: Path) -> Mapping[str, object]:
    path = dataset_path / "manifest.json"
    if not path.is_file():
        raise ScannerFixtureValidationError(f"{dataset_path}: missing manifest.json")
    try:
        value: object = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise ScannerFixtureValidationError(f"{dataset_path}: malformed manifest") from error
    return _mapping(value, "manifest")


def _parse_manifest(raw: Mapping[str, object], dataset_path: Path) -> ScannerFixtureManifest:
    schema_version = _string(
        raw.get("scanner_fixture_schema_version"), "scanner_fixture_schema_version"
    )
    if schema_version != "scanner-fixture-v1":
        raise ScannerFixtureValidationError(f"{dataset_path}: unsupported scanner fixture")
    as_of = _timestamp(raw.get("as_of"), "as_of")
    session_date = _date(raw.get("session_date"), "session_date")
    calendar = XNYSCalendarAdapter(
        start=session_date - timedelta(days=7), end=session_date + timedelta(days=7)
    )
    if not calendar.is_session(session_date):
        raise ScannerFixtureValidationError(f"{dataset_path}: session_date is not an XNYS session")
    scan_session = calendar.session_for_timestamp(as_of)
    if scan_session is None or scan_session.session_date != session_date:
        raise ScannerFixtureValidationError(f"{dataset_path}: as_of does not match session_date")
    versions = _versions(_mapping(raw.get("versions"), "versions"))
    if versions != PolicyVersions():
        raise ScannerFixtureValidationError(f"{dataset_path}: unknown scanner versions")
    hashes = _configuration_hashes(
        _mapping(raw.get("configuration_hashes"), "configuration_hashes")
    )
    streams_raw = _list(raw.get("market_streams"), "market_streams")
    streams = tuple(_market_stream(item) for item in streams_raw)
    if not streams or len({stream.filename for stream in streams}) != len(streams):
        raise ScannerFixtureValidationError(f"{dataset_path}: invalid market streams")
    supplemental_raw = _mapping(raw.get("supplemental"), "supplemental")
    supplemental = ScannerSupplementalFile(
        filename=_filename(supplemental_raw.get("filename")),
        sha256=_hash(supplemental_raw.get("sha256"), "supplemental hash"),
        record_count=_count(supplemental_raw.get("record_count"), "record_count"),
    )
    expected = _expected(_mapping(raw.get("expected"), "expected"))
    return ScannerFixtureManifest(
        dataset_id=_string(raw.get("dataset_id"), "dataset_id"),
        description=_string(raw.get("description"), "description"),
        schema_version=schema_version,
        as_of=as_of,
        session_date=session_date,
        source=_string(raw.get("source"), "source"),
        market_configuration_version=_string(
            raw.get("market_configuration_version"),
            "market_configuration_version",
        ),
        versions=versions,
        configuration_hashes=MappingProxyType(hashes),
        market_streams=streams,
        supplemental=supplemental,
        expected=expected,
    )


def _load_market_events(path: Path, manifest: ScannerFixtureManifest) -> tuple[ProviderEvent, ...]:
    events: list[ProviderEvent] = []
    previous_ingested_at: datetime | None = None
    for stream in manifest.market_streams:
        lines = _verified_lines(
            path / stream.filename,
            stream.sha256,
            stream.event_count,
            manifest.dataset_id,
        )
        for position, line in enumerate(lines, start=1):
            raw = _json_record(line, manifest.dataset_id, stream.filename, position)
            if _contains_sensitive_key(raw):
                _error(manifest.dataset_id, stream.filename, position, "sensitive key")
            kind_value = _string(raw.get("data_kind"), "data_kind")
            try:
                kind = DataKind(kind_value)
            except ValueError as error:
                raise ScannerFixtureValidationError(
                    f"{manifest.dataset_id}/{stream.filename}:{position}: unknown data kind"
                ) from error
            if kind is not stream.data_kind:
                _error(manifest.dataset_id, stream.filename, position, "data kind mismatch")
            observed_at = _timestamp(raw.get("observed_at"), "observed_at")
            ingested_at = _timestamp(raw.get("ingested_at"), "ingested_at")
            if observed_at > manifest.as_of or ingested_at > manifest.as_of:
                _error(manifest.dataset_id, stream.filename, position, "record is after as_of")
            if previous_ingested_at is not None and ingested_at < previous_ingested_at:
                _error(
                    manifest.dataset_id,
                    stream.filename,
                    position,
                    "ingestion timestamps must be nondecreasing",
                )
            previous_ingested_at = ingested_at
            events.append(
                ProviderEvent(
                    source=manifest.source,
                    event_id=_string(raw.get("event_id"), "event_id"),
                    data_kind=kind,
                    observed_at=observed_at,
                    ingested_at=ingested_at,
                    payload=_mapping(raw.get("payload"), "payload"),
                    fixture_schema_version=1,
                    configuration_version=manifest.market_configuration_version,
                    correlation_id=f"replay:{manifest.dataset_id}:{position}",
                )
            )
    return tuple(events)


def _load_supplemental(path: Path, manifest: ScannerFixtureManifest) -> SupplementalEvidence:
    descriptor = manifest.supplemental
    lines = _verified_lines(
        path / descriptor.filename,
        descriptor.sha256,
        descriptor.record_count,
        manifest.dataset_id,
    )
    records: list[Mapping[str, object]] = []
    for position, line in enumerate(lines, start=1):
        record = _json_record(line, manifest.dataset_id, descriptor.filename, position)
        if _contains_sensitive_key(record):
            _error(manifest.dataset_id, descriptor.filename, position, "sensitive key")
        records.append(record)
    try:
        return parse_supplemental_evidence(records, as_of=manifest.as_of)
    except EvidenceValidationError as error:
        raise ScannerFixtureValidationError(
            f"{manifest.dataset_id}/{descriptor.filename}: invalid supplemental evidence"
        ) from error


def _validate_files(path: Path, manifest: ScannerFixtureManifest) -> None:
    declared = {
        *(stream.filename for stream in manifest.market_streams),
        manifest.supplemental.filename,
    }
    actual = {item.name for item in path.glob("*.ndjson")}
    if missing := declared - actual:
        raise ScannerFixtureValidationError(
            f"{manifest.dataset_id}: missing file {sorted(missing)[0]}"
        )
    if undeclared := actual - declared:
        raise ScannerFixtureValidationError(
            f"{manifest.dataset_id}: undeclared file {sorted(undeclared)[0]}"
        )


def _verified_lines(
    path: Path, expected_hash: str, expected_count: int, dataset_id: str
) -> list[str]:
    content = path.read_bytes()
    if hashlib.sha256(content).hexdigest() != expected_hash:
        raise ScannerFixtureValidationError(f"{dataset_id}/{path.name}: SHA-256 mismatch")
    try:
        lines = content.decode("utf-8").splitlines()
    except UnicodeError as error:
        raise ScannerFixtureValidationError(f"{dataset_id}/{path.name}: invalid UTF-8") from error
    if len(lines) != expected_count:
        raise ScannerFixtureValidationError(f"{dataset_id}/{path.name}: record count mismatch")
    return lines


def _market_stream(value: object) -> FixtureStream:
    raw = _mapping(value, "market stream")
    kind_value = _string(raw.get("data_kind"), "data_kind")
    try:
        kind = DataKind(kind_value)
    except ValueError as error:
        raise ScannerFixtureValidationError("invalid market stream data_kind") from error
    return FixtureStream(
        filename=_filename(raw.get("filename")),
        data_kind=kind,
        sha256=_hash(raw.get("sha256"), "market stream hash"),
        event_count=_count(raw.get("event_count"), "event_count"),
    )


def _versions(raw: Mapping[str, object]) -> PolicyVersions:
    expected = {
        "universe",
        "eligibility",
        "features",
        "regime",
        "strategies",
        "scoring",
        "evidence",
        "fixture",
    }
    if set(raw) != expected:
        raise ScannerFixtureValidationError("invalid versions")
    return PolicyVersions(**{key: _string(raw[key], key) for key in expected})


def _configuration_hashes(raw: Mapping[str, object]) -> dict[str, str]:
    if set(raw) != _HASH_KEYS:
        raise ScannerFixtureValidationError("invalid configuration hashes")
    return {key: _hash(raw[key], f"{key} hash") for key in sorted(raw)}


def _expected(raw: Mapping[str, object]) -> ScannerExpectedResult:
    required = {
        "regime_state",
        "regime_score",
        "eligible",
        "ineligible",
        "blocked",
        "signals",
        "candidates",
        "reason_summary",
        "result_digest",
    }
    if set(raw) != required:
        raise ScannerFixtureValidationError("invalid expected result schema")
    try:
        regime_score = Decimal(_string(raw["regime_score"], "regime_score"))
    except InvalidOperation as error:
        raise ScannerFixtureValidationError("invalid expected regime_score") from error
    reasons_raw = _mapping(raw["reason_summary"], "expected reason_summary")
    reasons = {key: _count(value, f"reason_summary.{key}") for key, value in reasons_raw.items()}
    return ScannerExpectedResult(
        regime_state=_string(raw["regime_state"], "regime_state"),
        regime_score=regime_score,
        eligible=_count(raw["eligible"], "eligible"),
        ineligible=_count(raw["ineligible"], "ineligible"),
        blocked=_count(raw["blocked"], "blocked"),
        signals=_count(raw["signals"], "signals"),
        candidates=_count(raw["candidates"], "candidates"),
        reason_summary=MappingProxyType(reasons),
        result_digest=_hash(raw["result_digest"], "expected result digest"),
    )


def _evidence_ref(outcome: AcceptedIngestion) -> EvidenceRef:
    return EvidenceRef(
        lineage_id=outcome.ingestion_key,
        source=outcome.event.source,
        event_id=outcome.event.event_id,
        ingestion_key=outcome.ingestion_key,
        payload_digest=outcome.payload_digest,
        observed_at=outcome.event.observed_at,
        ingested_at=outcome.event.ingested_at,
    )


def _json_record(line: str, dataset_id: str, filename: str, position: int) -> Mapping[str, object]:
    try:
        value: object = json.loads(line)
    except json.JSONDecodeError as error:
        _error(dataset_id, filename, position, "malformed JSON", error)
    return _mapping(value, "record")


def _mapping(value: object, name: str) -> Mapping[str, object]:
    if not isinstance(value, dict) or not all(isinstance(key, str) for key in value):
        raise ScannerFixtureValidationError(f"invalid {name}")
    return cast(Mapping[str, object], value)


def _list(value: object, name: str) -> list[object]:
    if not isinstance(value, list):
        raise ScannerFixtureValidationError(f"invalid {name}")
    return cast(list[object], value)


def _string(value: object, name: str) -> str:
    if not isinstance(value, str) or not value:
        raise ScannerFixtureValidationError(f"invalid {name}")
    return value


def _filename(value: object) -> str:
    filename = _string(value, "filename")
    if Path(filename).name != filename or Path(filename).suffix != ".ndjson":
        raise ScannerFixtureValidationError("invalid filename")
    return filename


def _hash(value: object, name: str) -> str:
    digest = _string(value, name)
    if len(digest) != 64 or any(character not in "0123456789abcdef" for character in digest):
        raise ScannerFixtureValidationError(f"invalid {name}")
    return digest


def _count(value: object, name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ScannerFixtureValidationError(f"invalid {name}")
    return value


def _timestamp(value: object, name: str) -> datetime:
    try:
        return ensure_utc(datetime.fromisoformat(_string(value, name)))
    except ValueError as error:
        raise ScannerFixtureValidationError(f"invalid {name}: {error}") from error


def _date(value: object, name: str) -> date:
    try:
        return date.fromisoformat(_string(value, name))
    except ValueError as error:
        raise ScannerFixtureValidationError(f"invalid {name}") from error


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
    position: int,
    message: str,
    cause: Exception | None = None,
) -> NoReturn:
    error = ScannerFixtureValidationError(f"{dataset_id}/{filename}:{position}: {message}")
    if cause is not None:
        raise error from cause
    raise error
