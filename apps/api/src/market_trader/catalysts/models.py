from collections.abc import Mapping
from dataclasses import dataclass, fields, is_dataclass
from datetime import datetime
from decimal import Decimal
from enum import Enum, StrEnum
from types import MappingProxyType
from typing import cast

from market_trader.domain.time import ensure_utc


class EventFamily(StrEnum):
    COMPANY_NEWS = "company_news"
    EARNINGS = "earnings"
    SEC_FILING = "sec_filing"
    ECONOMIC_RELEASE = "economic_release"
    SOCIAL = "social"


class Materiality(StrEnum):
    MATERIAL = "material"
    CONTEXTUAL = "contextual"
    UNKNOWN = "unknown"


class CatalystDirection(StrEnum):
    POSITIVE = "positive"
    NEGATIVE = "negative"
    NEUTRAL = "neutral"
    UNCLEAR = "unclear"


class ConfirmationState(StrEnum):
    CONFIRMED = "confirmed"
    UNCONFIRMED = "unconfirmed"
    BLOCKED = "blocked"


class SourceState(StrEnum):
    AVAILABLE = "available"
    DEGRADED = "degraded"
    STALE = "stale"
    UNAVAILABLE = "unavailable"
    MALFORMED = "malformed"


class AuthorityClass(StrEnum):
    OFFICIAL_STRUCTURED = "official_structured"
    AUTHORIZED_STRUCTURED = "authorized_structured"
    EXTERNAL_TEXT = "external_text"
    GENERATED_SUMMARY = "generated_summary"


class RiskState(StrEnum):
    CLEAR = "clear"
    ACTIVE = "active"
    BLOCKED = "blocked"


class SourceFailureKind(StrEnum):
    UNSUPPORTED = "unsupported"
    UNAVAILABLE = "unavailable"
    THROTTLED = "throttled"
    PARTIAL = "partial"
    MALFORMED = "malformed"
    SECURITY_REJECTED = "security_rejected"


@dataclass(frozen=True)
class CatalystPolicyVersions:
    source: str = "catalyst-source-policy-v1"
    classification: str = "catalyst-classification-policy-v1"
    risk: str = "event-risk-policy-v1"
    summary: str = "catalyst-summary-policy-v1"
    fixture: str = "catalyst-fixture-v1"


@dataclass(frozen=True)
class CatalystProviderEvent:
    source_id: str
    provider_event_id: str
    event_family: EventFamily
    provider_schema_version: int
    published_at: datetime
    ingested_at: datetime
    scheduled_for: datetime | None
    symbol_identity: str | None
    structured_fields: Mapping[str, object]
    external_text: Mapping[str, object]
    source_reference: str
    correlation_id: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "published_at", ensure_utc(self.published_at))
        object.__setattr__(self, "ingested_at", ensure_utc(self.ingested_at))
        if self.scheduled_for is not None:
            object.__setattr__(self, "scheduled_for", ensure_utc(self.scheduled_for))
        object.__setattr__(self, "structured_fields", _immutable_mapping(self.structured_fields))
        object.__setattr__(self, "external_text", _immutable_mapping(self.external_text))


@dataclass(frozen=True)
class SourceFailure:
    source_id: str
    kind: SourceFailureKind
    occurred_at: datetime
    reasons: tuple[str, ...]

    def __post_init__(self) -> None:
        object.__setattr__(self, "occurred_at", ensure_utc(self.occurred_at))
        object.__setattr__(self, "reasons", _ordered_unique(self.reasons))


@dataclass(frozen=True)
class CatalystObservation:
    observation_key: str
    ingestion_key: str
    authoritative_digest: str
    external_text_digest: str
    source_id: str
    authority_class: AuthorityClass
    event_family: EventFamily
    event_category: str
    provider_event_id: str
    source_reference: str
    symbol: str | None
    published_at: datetime
    ingested_at: datetime
    scheduled_for: datetime | None
    valid_until: datetime
    structured_facts: Mapping[str, object]
    external_text: Mapping[str, object]
    source_schema_version: int
    normalization_schema_version: int
    configuration_version: str
    correlation_id: str
    quality_reasons: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "published_at", ensure_utc(self.published_at))
        object.__setattr__(self, "ingested_at", ensure_utc(self.ingested_at))
        if self.scheduled_for is not None:
            object.__setattr__(self, "scheduled_for", ensure_utc(self.scheduled_for))
        object.__setattr__(self, "valid_until", ensure_utc(self.valid_until))
        object.__setattr__(self, "structured_facts", _immutable_mapping(self.structured_facts))
        object.__setattr__(self, "external_text", _immutable_mapping(self.external_text))
        object.__setattr__(self, "quality_reasons", _ordered_unique(self.quality_reasons))


@dataclass(frozen=True)
class QuarantinedObservation:
    ingestion_key: str
    sanitized_payload_digest: str
    source_id: str | None
    provider_event_id: str | None
    published_at: datetime | None
    ingested_at: datetime
    reasons: tuple[str, ...]
    sanitized_payload: Mapping[str, object]
    source_schema_version: int | None = None
    normalization_schema_version: int | None = None
    correlation_id: str | None = None

    def __post_init__(self) -> None:
        if self.published_at is not None:
            object.__setattr__(self, "published_at", ensure_utc(self.published_at))
        object.__setattr__(self, "ingested_at", ensure_utc(self.ingested_at))
        object.__setattr__(self, "reasons", _ordered_unique(self.reasons))
        object.__setattr__(self, "sanitized_payload", _immutable_mapping(self.sanitized_payload))


@dataclass(frozen=True)
class EventRiskWindow:
    category: str
    scope: str
    symbol: str | None
    starts_at: datetime | None
    ends_at: datetime | None
    state: RiskState
    reasons: tuple[str, ...]
    lineage: tuple[str, ...]
    policy_version: str

    def __post_init__(self) -> None:
        if self.starts_at is not None:
            object.__setattr__(self, "starts_at", ensure_utc(self.starts_at))
        if self.ends_at is not None:
            object.__setattr__(self, "ends_at", ensure_utc(self.ends_at))
        object.__setattr__(self, "reasons", _ordered_unique(self.reasons))
        object.__setattr__(self, "lineage", _ordered_unique(self.lineage))


@dataclass(frozen=True)
class CatalystDecision:
    decision_key: str
    scope: str
    symbol: str | None
    as_of: datetime
    materiality: Materiality
    direction: CatalystDirection
    confirmation: ConfirmationState
    risk_state: RiskState
    reasons: tuple[str, ...]
    observation_keys: tuple[str, ...]
    policy_versions: CatalystPolicyVersions
    input_digest: str
    explanation: Mapping[str, object]

    def __post_init__(self) -> None:
        object.__setattr__(self, "as_of", ensure_utc(self.as_of))
        object.__setattr__(self, "reasons", _ordered_unique(self.reasons))
        object.__setattr__(self, "observation_keys", _ordered_unique(self.observation_keys))
        object.__setattr__(self, "explanation", _immutable_mapping(self.explanation))


@dataclass(frozen=True)
class SummarySegment:
    text: str
    observation_keys: tuple[str, ...]
    source_references: tuple[str, ...]

    def __post_init__(self) -> None:
        if not self.observation_keys or not self.source_references:
            raise ValueError("summary segment requires at least one citation")
        object.__setattr__(self, "observation_keys", _ordered_unique(self.observation_keys))
        object.__setattr__(self, "source_references", _ordered_unique(self.source_references))


@dataclass(frozen=True)
class CitedSummary:
    summary_key: str
    provider_id: str
    generated_at: datetime
    segments: tuple[SummarySegment, ...]
    policy_version: str
    content_digest: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "generated_at", ensure_utc(self.generated_at))
        if not self.segments:
            raise ValueError("cited summary requires at least one segment")


@dataclass(frozen=True)
class SourceRunResult:
    run_key: str
    source_id: str
    capability: str
    request_digest: str
    source_policy_version: str
    policy_hashes: Mapping[str, str]
    as_of: datetime
    state: SourceState
    observations: tuple[CatalystObservation, ...]
    quarantined: tuple[QuarantinedObservation, ...]
    decisions: tuple[CatalystDecision, ...]
    summaries: tuple[CitedSummary, ...]
    reasons: tuple[str, ...]
    result_digest: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "as_of", ensure_utc(self.as_of))
        object.__setattr__(
            self,
            "policy_hashes",
            MappingProxyType(dict(sorted(self.policy_hashes.items()))),
        )
        object.__setattr__(
            self,
            "observations",
            _sorted_records(self.observations, "observation_key"),
        )
        object.__setattr__(self, "quarantined", _sorted_records(self.quarantined, "ingestion_key"))
        object.__setattr__(self, "decisions", _sorted_records(self.decisions, "decision_key"))
        object.__setattr__(self, "summaries", _sorted_records(self.summaries, "summary_key"))
        object.__setattr__(self, "reasons", _ordered_unique(self.reasons))


def _ordered_unique(values: tuple[str, ...]) -> tuple[str, ...]:
    return tuple(sorted(set(values)))


def _immutable_mapping[T](values: Mapping[str, T]) -> Mapping[str, T]:
    return cast(
        Mapping[str, T],
        MappingProxyType({str(key): _freeze_value(value) for key, value in values.items()}),
    )


def _freeze_value(value: object) -> object:
    if isinstance(value, Mapping):
        return MappingProxyType({str(key): _freeze_value(item) for key, item in value.items()})
    if isinstance(value, (list, tuple)):
        return tuple(_freeze_value(item) for item in value)
    if is_dataclass(value) and not isinstance(value, type):
        return MappingProxyType(
            {item.name: _freeze_value(getattr(value, item.name)) for item in fields(value)}
        )
    if value is None or isinstance(value, (bool, int, float, str, bytes, Decimal, datetime, Enum)):
        return value
    raise TypeError(f"unsupported mutable catalyst value: {type(value).__name__}")


def _sorted_records[T](values: tuple[T, ...], attribute: str) -> tuple[T, ...]:
    return tuple(sorted(values, key=lambda value: str(getattr(value, attribute))))
