import re
from collections.abc import Collection, Mapping
from dataclasses import dataclass
from datetime import datetime, timedelta
from decimal import Decimal, InvalidOperation
from types import MappingProxyType
from typing import NoReturn, cast

from market_trader.catalysts.configuration import CatalystConfiguration
from market_trader.catalysts.models import (
    CatalystObservation,
    CatalystProviderEvent,
    EventFamily,
    QuarantinedObservation,
)
from market_trader.catalysts.sanitization import (
    SanitizedProviderValue,
    sanitize_provider_payload,
)
from market_trader.catalysts.serialization import stable_digest
from market_trader.domain.time import ensure_utc
from market_trader.market_data.sanitization import ingestion_key

NORMALIZATION_SCHEMA_VERSION = 1
FUTURE_TOLERANCE = timedelta(minutes=5)
DEFAULT_FRESHNESS = timedelta(days=1)

_SYMBOL = re.compile(r"^[A-Z][A-Z0-9.-]{0,9}$")
_SOURCE_FAMILY = {
    "recorded-company-news-v1": EventFamily.COMPANY_NEWS,
    "recorded-earnings-v1": EventFamily.EARNINGS,
    "sec-edgar-public-v1": EventFamily.SEC_FILING,
    "bls-public-v1": EventFamily.ECONOMIC_RELEASE,
    "recorded-social-v1": EventFamily.SOCIAL,
}
_STATIC_CATEGORIES = {
    EventFamily.EARNINGS: frozenset(("earnings_result", "earnings_schedule")),
    EventFamily.SEC_FILING: frozenset(("sec_filing",)),
    EventFamily.SOCIAL: frozenset(("social_post",)),
}
_DECIMAL_FIELDS = frozenset(
    (
        "actual",
        "consensus",
        "guidance_high",
        "guidance_low",
        "prior_guidance_high",
        "prior_guidance_low",
        "value",
    )
)


class _NormalizationFailure(ValueError):
    def __init__(self, reason: str) -> None:
        self.reason = reason
        super().__init__(reason)


@dataclass(frozen=True)
class ObservationWatermark:
    latest_published_at: datetime | None
    observations_by_ingestion_key: Mapping[str, CatalystObservation]

    def __post_init__(self) -> None:
        if self.latest_published_at is not None:
            object.__setattr__(
                self,
                "latest_published_at",
                ensure_utc(self.latest_published_at),
            )
        object.__setattr__(
            self,
            "observations_by_ingestion_key",
            MappingProxyType(dict(self.observations_by_ingestion_key)),
        )


@dataclass(frozen=True)
class NormalizationResult:
    observation: CatalystObservation | None = None
    quarantine: QuarantinedObservation | None = None

    def __post_init__(self) -> None:
        if (self.observation is None) == (self.quarantine is None):
            raise ValueError("normalization result requires exactly one outcome")


def normalize_event(
    event: CatalystProviderEvent,
    *,
    as_of: datetime,
    configuration: CatalystConfiguration,
    watermark: ObservationWatermark | None = None,
) -> NormalizationResult:
    normalized_as_of = ensure_utc(as_of)
    event_key = ingestion_key(
        event.source_id,
        event.provider_event_id,
        event.provider_schema_version,
    )
    try:
        _validate_attribution(event)
        source = configuration.sources.by_id.get(event.source_id)
        if source is None:
            _fail("unknown_source")
        if event.provider_schema_version != 1:
            _fail("unknown_provider_schema")
        if _SOURCE_FAMILY.get(event.source_id) is not event.event_family:
            _fail("unexpected_source_family")
        symbol = _normalize_symbol(event.symbol_identity, event.event_family)
        facts = _sanitized_mapping(event.structured_fields)
        category = _event_category(facts, event.event_family, configuration)
        canonical_facts = _canonicalize_facts(facts)
        _validate_family_facts(event.event_family, canonical_facts, configuration)
        _validate_temporal(event, normalized_as_of)
        valid_until = _valid_until(event, configuration)
        if normalized_as_of > valid_until:
            _fail("stale_observation")
        reference = _source_reference(event, canonical_facts, configuration)
        external_text = _sanitized_mapping(event.external_text)
        authoritative_record = {
            "source_id": event.source_id,
            "provider_event_id": event.provider_event_id,
            "event_family": event.event_family,
            "provider_schema_version": event.provider_schema_version,
            "published_at": event.published_at,
            "scheduled_for": event.scheduled_for,
            "symbol": symbol,
            "structured_facts": canonical_facts,
            "source_reference": reference,
            "source_policy_version": configuration.sources.version,
            "normalization_schema_version": NORMALIZATION_SCHEMA_VERSION,
        }
        authoritative_digest = stable_digest(authoritative_record)
        existing = (
            None
            if watermark is None
            else watermark.observations_by_ingestion_key.get(event_key)
        )
        if existing is not None:
            if existing.authoritative_digest != authoritative_digest:
                _fail("event_identity_conflict")
            return NormalizationResult(observation=existing)
        if (
            watermark is not None
            and watermark.latest_published_at is not None
            and event.published_at < watermark.latest_published_at
        ):
            _fail("out_of_order")
        observation_key = f"obs_{stable_digest((event_key, authoritative_digest))}"
        return NormalizationResult(
            observation=CatalystObservation(
                observation_key=observation_key,
                ingestion_key=event_key,
                authoritative_digest=authoritative_digest,
                external_text_digest=stable_digest(external_text),
                source_id=event.source_id,
                authority_class=source.authority_class,
                event_family=event.event_family,
                event_category=category,
                provider_event_id=event.provider_event_id,
                source_reference=reference,
                symbol=symbol,
                published_at=event.published_at,
                ingested_at=event.ingested_at,
                scheduled_for=event.scheduled_for,
                valid_until=valid_until,
                structured_facts=canonical_facts,
                external_text=external_text,
                source_schema_version=event.provider_schema_version,
                normalization_schema_version=NORMALIZATION_SCHEMA_VERSION,
                configuration_version=configuration.sources.version,
                correlation_id=event.correlation_id,
            )
        )
    except _NormalizationFailure as error:
        return NormalizationResult(
            quarantine=_quarantine(event, event_key=event_key, reason=error.reason)
        )


def _validate_attribution(event: CatalystProviderEvent) -> None:
    required = (event.source_id, event.provider_event_id, event.correlation_id)
    if any(not value.strip() for value in required):
        _fail("missing_attribution")


def _normalize_symbol(symbol: str | None, family: EventFamily) -> str | None:
    if family is EventFamily.ECONOMIC_RELEASE:
        if symbol is not None:
            _fail("invalid_symbol")
        return None
    if symbol is None or _SYMBOL.fullmatch(symbol) is None:
        _fail("invalid_symbol")
    return symbol


def _event_category(
    facts: Mapping[str, object],
    family: EventFamily,
    configuration: CatalystConfiguration,
) -> str:
    category = facts.get("event_category")
    if not isinstance(category, str) or not category:
        _fail("missing_event_category")
    allowed: Collection[str]
    if family is EventFamily.COMPANY_NEWS:
        allowed = configuration.classification.categories
    elif family is EventFamily.ECONOMIC_RELEASE:
        allowed = {
            *configuration.sources.bls_series,
            "employment_situation",
        }
    else:
        allowed = _STATIC_CATEGORIES[family]
    if category not in allowed:
        _fail("unknown_event_category")
    return category


def _canonicalize_facts(facts: Mapping[str, object]) -> Mapping[str, object]:
    canonical: dict[str, object] = {}
    for key, value in facts.items():
        if key in _DECIMAL_FIELDS and value is not None:
            canonical[key] = _decimal_string(value)
        else:
            canonical[key] = value
    return MappingProxyType(canonical)


def _validate_family_facts(
    family: EventFamily,
    facts: Mapping[str, object],
    configuration: CatalystConfiguration,
) -> None:
    if family is EventFamily.EARNINGS and facts["event_category"] == "earnings_result":
        _required_fields(facts, "actual", "consensus", "currency", "period", "unit")
    elif family is EventFamily.SEC_FILING:
        _required_fields(facts, "accession_number", "cik", "form")
        cik = facts["cik"]
        if not isinstance(cik, str) or len(cik) != 10 or not cik.isdigit():
            _fail("invalid_cik")
    elif family is EventFamily.ECONOMIC_RELEASE and "series_id" in facts:
        _required_fields(facts, "period", "series_id", "value")
        if facts["series_id"] not in configuration.sources.bls_series.values():
            _fail("unsupported_series")
    elif family is EventFamily.SOCIAL:
        _required_fields(facts, "attribution_id")


def _required_fields(facts: Mapping[str, object], *names: str) -> None:
    if any(facts.get(name) in (None, "") for name in names):
        _fail("missing_structured_fact")


def _validate_temporal(event: CatalystProviderEvent, as_of: datetime) -> None:
    if event.published_at > event.ingested_at + FUTURE_TOLERANCE:
        _fail("future_timestamp")
    if event.published_at > as_of + FUTURE_TOLERANCE:
        _fail("future_timestamp")


def _valid_until(
    event: CatalystProviderEvent,
    configuration: CatalystConfiguration,
) -> datetime:
    if event.event_family is EventFamily.SOCIAL:
        return event.published_at + timedelta(
            minutes=configuration.classification.social_freshness_minutes
        )
    if event.scheduled_for is not None:
        return event.scheduled_for + timedelta(minutes=configuration.risk.macro_minutes_after)
    return event.published_at + DEFAULT_FRESHNESS


def _source_reference(
    event: CatalystProviderEvent,
    facts: Mapping[str, object],
    configuration: CatalystConfiguration,
) -> str:
    source = configuration.sources.by_id[event.source_id]
    if event.source_id == "sec-edgar-public-v1":
        cik = cast(str, facts["cik"])
        accession = cast(str, facts["accession_number"])
        if source.origins != ("https://data.sec.gov",):
            _fail("invalid_source_origin")
        return f"{source.origins[0]}/submissions/CIK{cik}.json#{accession}"
    if event.source_id == "bls-public-v1":
        origin = "https://api.bls.gov" if "series_id" in facts else "https://www.bls.gov"
        if origin not in source.origins:
            _fail("invalid_source_origin")
        path = (
            "/publicAPI/v1/timeseries/data/"
            if "series_id" in facts
            else "/schedule/news_release/bls.ics"
        )
        return f"{origin}{path}#{event.provider_event_id}"
    return f"fixture://{event.source_id}/{event.provider_event_id}"


def _decimal_string(value: object) -> str:
    if not isinstance(value, (str, Decimal)):
        _fail("invalid_decimal")
    try:
        parsed = Decimal(value)
    except InvalidOperation:
        _fail("invalid_decimal")
    if not parsed.is_finite():
        _fail("invalid_decimal")
    return format(parsed, "f")


def _sanitized_mapping(value: Mapping[str, object]) -> Mapping[str, object]:
    sanitized = sanitize_provider_payload(value)
    if not isinstance(sanitized, Mapping):
        _fail("malformed_payload")
    return cast(Mapping[str, object], sanitized)


def _quarantine(
    event: CatalystProviderEvent,
    *,
    event_key: str,
    reason: str,
) -> QuarantinedObservation:
    raw_payload = {
        "source_id": event.source_id,
        "provider_event_id": event.provider_event_id,
        "event_family": event.event_family.value,
        "provider_schema_version": event.provider_schema_version,
        "published_at": event.published_at,
        "ingested_at": event.ingested_at,
        "scheduled_for": event.scheduled_for,
        "symbol_identity": event.symbol_identity,
        "structured_fields": event.structured_fields,
        "external_text": event.external_text,
        "source_reference": event.source_reference,
        "correlation_id": event.correlation_id,
    }
    sanitized = sanitize_provider_payload(raw_payload)
    if not isinstance(sanitized, Mapping):
        sanitized = MappingProxyType({"type": cast(SanitizedProviderValue, "malformed")})
    sanitized_mapping = cast(Mapping[str, object], sanitized)
    quarantine_key = (
        f"conflict_{stable_digest((event_key, sanitized_mapping))}"
        if reason == "event_identity_conflict"
        else event_key
    )
    return QuarantinedObservation(
        ingestion_key=quarantine_key,
        sanitized_payload_digest=stable_digest(sanitized_mapping),
        source_id=event.source_id or None,
        provider_event_id=event.provider_event_id or None,
        published_at=event.published_at,
        ingested_at=event.ingested_at,
        reasons=(reason,),
        sanitized_payload=sanitized_mapping,
        source_schema_version=event.provider_schema_version,
        normalization_schema_version=NORMALIZATION_SCHEMA_VERSION,
        correlation_id=event.correlation_id or None,
    )


def _fail(reason: str) -> NoReturn:
    raise _NormalizationFailure(reason)
