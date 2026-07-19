from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from enum import StrEnum
from types import MappingProxyType
from typing import cast

from market_trader.domain.time import ensure_utc

EVIDENCE_SCHEMA_VERSION = "scanner-evidence-v1"
MAX_EVIDENCE_RECORDS = 1_000
MAX_IDENTIFIER_LENGTH = 128
MAX_REFERENCE_LENGTH = 2_048
MAX_REASON_CODES = 32

SECTOR_ETFS: Mapping[str, str] = MappingProxyType(
    {
        "XLB": "materials",
        "XLC": "communication_services",
        "XLE": "energy",
        "XLF": "financials",
        "XLI": "industrials",
        "XLK": "technology",
        "XLP": "consumer_staples",
        "XLRE": "real_estate",
        "XLU": "utilities",
        "XLV": "health_care",
        "XLY": "consumer_discretionary",
    }
)

_COMMON_FIELDS = frozenset(
    {
        "evidence_type",
        "schema_version",
        "configuration_version",
        "correlation_id",
        "lineage_id",
        "source",
        "observed_at",
        "valid_until",
    }
)
_SENSITIVE_KEY_FRAGMENTS = (
    "authorization",
    "cookie",
    "token",
    "secret",
    "password",
    "api_key",
    "account",
)
_PROHIBITED_CONTENT_KEYS = (
    "article_body",
    "body_text",
    "instruction_text",
    "instructions",
    "executable_content",
    "model_sentiment",
)


class EvidenceValidationError(ValueError):
    pass


class MacroState(StrEnum):
    RISK_ON = "risk_on"
    NEUTRAL = "neutral"
    RISK_OFF = "risk_off"
    BLOCKED = "blocked"


class CatalystMateriality(StrEnum):
    MATERIAL = "material"
    NON_MATERIAL = "non_material"


class CatalystDirection(StrEnum):
    POSITIVE = "positive"
    NEGATIVE = "negative"
    UNCLEAR = "unclear"


class VolatilityDirection(StrEnum):
    RISING = "rising"
    FALLING = "falling"
    FLAT = "flat"


@dataclass(frozen=True)
class EvidenceMetadata:
    schema_version: str
    configuration_version: str
    correlation_id: str
    lineage_id: str
    source: str
    observed_at: datetime
    valid_until: datetime

    def is_current(self, as_of: datetime) -> bool:
        try:
            reference = ensure_utc(as_of)
        except ValueError as error:
            raise EvidenceValidationError("as_of must be timezone-aware") from error
        return reference <= self.valid_until


@dataclass(frozen=True)
class BreadthEvidence(EvidenceMetadata):
    source_universe: str
    session_date: date
    total_eligible_issues: int
    advancing_issues: int
    declining_issues: int
    unchanged_issues: int
    issues_above_sma_50: int
    up_volume: Decimal
    down_volume: Decimal


@dataclass(frozen=True)
class SectorObservation:
    symbol: str
    sector: str
    close_relative_to_sma_50: Decimal
    return_20_session: Decimal


@dataclass(frozen=True)
class SectorEvidence(EvidenceMetadata):
    session_date: date
    observations: tuple[SectorObservation, ...]


@dataclass(frozen=True)
class VolatilityEvidence(EvidenceMetadata):
    measure: str
    current_value: Decimal
    value_five_sessions_earlier: Decimal
    median_20_session: Decimal
    direction: VolatilityDirection


@dataclass(frozen=True)
class MacroEvidence(EvidenceMetadata):
    state: MacroState
    reason_codes: tuple[str, ...]
    observation_keys: tuple[str, ...] = field(
        default=(), metadata={"canonical_omit_default": True}
    )
    policy_versions: tuple[str, ...] = field(
        default=(), metadata={"canonical_omit_default": True}
    )


@dataclass(frozen=True)
class CatalystEvidence(EvidenceMetadata):
    evidence_id: str
    symbol: str
    source_reference: str
    published_at: datetime
    materiality: CatalystMateriality
    direction: CatalystDirection
    category: str
    blocked: bool = field(default=False, metadata={"canonical_omit_default": True})
    reason_codes: tuple[str, ...] = field(
        default=(), metadata={"canonical_omit_default": True}
    )
    observation_keys: tuple[str, ...] = field(
        default=(), metadata={"canonical_omit_default": True}
    )
    policy_versions: tuple[str, ...] = field(
        default=(), metadata={"canonical_omit_default": True}
    )


@dataclass(frozen=True)
class SupplementalEvidence:
    as_of: datetime
    breadth: tuple[BreadthEvidence, ...]
    sector: tuple[SectorEvidence, ...]
    volatility: tuple[VolatilityEvidence, ...]
    macro: tuple[MacroEvidence, ...]
    catalysts: tuple[CatalystEvidence, ...]

    @property
    def sector_by_symbol(self) -> Mapping[str, SectorObservation]:
        if len(self.sector) != 1:
            return MappingProxyType({})
        return MappingProxyType(
            {item.symbol: item for item in self.sector[0].observations}
        )


def parse_supplemental_evidence(
    records: Sequence[Mapping[str, object]], *, as_of: datetime
) -> SupplementalEvidence:
    reference = _as_of(as_of)
    if isinstance(records, (str, bytes)) or len(records) > MAX_EVIDENCE_RECORDS:
        raise EvidenceValidationError("too many evidence records")

    breadth: list[BreadthEvidence] = []
    sector: list[SectorEvidence] = []
    volatility: list[VolatilityEvidence] = []
    macro: list[MacroEvidence] = []
    catalysts: list[CatalystEvidence] = []
    evidence_ids: set[str] = set()

    for position, value in enumerate(records):
        record = _mapping(value, "evidence record")
        if _contains_forbidden_key(record):
            raise EvidenceValidationError("evidence contains prohibited field")
        evidence_type = _string(record.get("evidence_type"), "evidence_type")
        metadata = _metadata(record, evidence_type, reference)
        if evidence_type == "breadth":
            breadth.append(_parse_breadth(record, metadata))
        elif evidence_type == "sector":
            sector.append(_parse_sector(record, metadata))
        elif evidence_type == "volatility":
            volatility.append(_parse_volatility(record, metadata))
        elif evidence_type == "macro":
            macro.append(_parse_macro(record, metadata))
        elif evidence_type == "catalyst":
            catalyst = _parse_catalyst(record, metadata, reference)
            if catalyst.evidence_id in evidence_ids:
                raise EvidenceValidationError("duplicate catalyst evidence_id")
            evidence_ids.add(catalyst.evidence_id)
            catalysts.append(catalyst)
        else:
            raise EvidenceValidationError(f"record {position}: unknown evidence type")

    if any(item.session_date > reference.date() for item in breadth) or any(
        item.session_date > reference.date() for item in sector
    ):
        raise EvidenceValidationError("session_date is after as_of")

    return SupplementalEvidence(
        as_of=reference,
        breadth=tuple(sorted(breadth, key=_record_sort_key)),
        sector=tuple(sorted(sector, key=_record_sort_key)),
        volatility=tuple(sorted(volatility, key=_record_sort_key)),
        macro=tuple(sorted(macro, key=_record_sort_key)),
        catalysts=tuple(sorted(catalysts, key=_catalyst_sort_key)),
    )


def _metadata(
    record: Mapping[str, object], evidence_type: str, as_of: datetime
) -> EvidenceMetadata:
    schema_version = _string(
        record.get("schema_version"), f"{evidence_type}.schema_version"
    )
    if schema_version != EVIDENCE_SCHEMA_VERSION:
        raise EvidenceValidationError("unsupported evidence schema")
    observed_at = _timestamp(record.get("observed_at"), f"{evidence_type}.observed_at")
    valid_until = _timestamp(record.get("valid_until"), f"{evidence_type}.valid_until")
    if observed_at > as_of:
        raise EvidenceValidationError(f"{evidence_type}.observed_at is after as_of")
    if valid_until < observed_at:
        raise EvidenceValidationError(f"{evidence_type}.valid_until is before observed_at")
    return EvidenceMetadata(
        schema_version=schema_version,
        configuration_version=_identifier(
            record.get("configuration_version"), f"{evidence_type}.configuration_version"
        ),
        correlation_id=_identifier(
            record.get("correlation_id"), f"{evidence_type}.correlation_id"
        ),
        lineage_id=_identifier(record.get("lineage_id"), f"{evidence_type}.lineage_id"),
        source=_identifier(record.get("source"), f"{evidence_type}.source"),
        observed_at=observed_at,
        valid_until=valid_until,
    )


def _parse_breadth(
    record: Mapping[str, object], metadata: EvidenceMetadata
) -> BreadthEvidence:
    _strict_keys(
        record,
        "breadth",
        {
            "source_universe",
            "session_date",
            "total_eligible_issues",
            "advancing_issues",
            "declining_issues",
            "unchanged_issues",
            "issues_above_sma_50",
            "up_volume",
            "down_volume",
        },
    )
    total = _nonnegative_int(record.get("total_eligible_issues"), "breadth.total_eligible_issues")
    advancing = _nonnegative_int(record.get("advancing_issues"), "breadth.advancing_issues")
    declining = _nonnegative_int(record.get("declining_issues"), "breadth.declining_issues")
    unchanged = _nonnegative_int(record.get("unchanged_issues"), "breadth.unchanged_issues")
    above = _nonnegative_int(record.get("issues_above_sma_50"), "breadth.issues_above_sma_50")
    if advancing + declining + unchanged != total or above > total:
        raise EvidenceValidationError("breadth issue counts are inconsistent")
    return BreadthEvidence(
        **metadata.__dict__,
        source_universe=_identifier(record.get("source_universe"), "breadth.source_universe"),
        session_date=_date(record.get("session_date"), "breadth.session_date"),
        total_eligible_issues=total,
        advancing_issues=advancing,
        declining_issues=declining,
        unchanged_issues=unchanged,
        issues_above_sma_50=above,
        up_volume=_decimal(record.get("up_volume"), "breadth.up_volume", nonnegative=True),
        down_volume=_decimal(
            record.get("down_volume"), "breadth.down_volume", nonnegative=True
        ),
    )


def _parse_sector(
    record: Mapping[str, object], metadata: EvidenceMetadata
) -> SectorEvidence:
    _strict_keys(record, "sector", {"session_date", "observations"})
    raw_observations = record.get("observations")
    if not isinstance(raw_observations, list) or len(raw_observations) != len(SECTOR_ETFS):
        raise EvidenceValidationError("sector requires exactly 11 sector observations")
    observations: list[SectorObservation] = []
    seen: set[str] = set()
    for value in raw_observations:
        item = _mapping(value, "sector observation")
        _strict_keys(
            item,
            "sector observation",
            {"symbol", "sector", "close_relative_to_sma_50", "return_20_session"},
            include_common=False,
        )
        symbol = _identifier(item.get("symbol"), "sector.symbol")
        if symbol in seen:
            raise EvidenceValidationError("duplicate sector symbol")
        seen.add(symbol)
        identity = _identifier(item.get("sector"), "sector.sector")
        if SECTOR_ETFS.get(symbol) != identity:
            raise EvidenceValidationError("invalid sector identity")
        observations.append(
            SectorObservation(
                symbol=symbol,
                sector=identity,
                close_relative_to_sma_50=_decimal(
                    item.get("close_relative_to_sma_50"),
                    "sector.close_relative_to_sma_50",
                    positive=True,
                ),
                return_20_session=_decimal(
                    item.get("return_20_session"), "sector.return_20_session"
                ),
            )
        )
    if seen != set(SECTOR_ETFS):
        raise EvidenceValidationError("sector observations do not match required ETFs")
    return SectorEvidence(
        **metadata.__dict__,
        session_date=_date(record.get("session_date"), "sector.session_date"),
        observations=tuple(sorted(observations, key=lambda item: item.symbol)),
    )


def _parse_volatility(
    record: Mapping[str, object], metadata: EvidenceMetadata
) -> VolatilityEvidence:
    _strict_keys(
        record,
        "volatility",
        {"measure", "current_value", "value_five_sessions_earlier", "median_20_session"},
    )
    current = _decimal(
        record.get("current_value"), "volatility.current_value", nonnegative=True
    )
    prior = _decimal(
        record.get("value_five_sessions_earlier"),
        "volatility.value_five_sessions_earlier",
        nonnegative=True,
    )
    median = _decimal(
        record.get("median_20_session"),
        "volatility.median_20_session",
        nonnegative=True,
    )
    direction = VolatilityDirection.FLAT
    if current > prior:
        direction = VolatilityDirection.RISING
    elif current < prior:
        direction = VolatilityDirection.FALLING
    return VolatilityEvidence(
        **metadata.__dict__,
        measure=_identifier(record.get("measure"), "volatility.measure"),
        current_value=current,
        value_five_sessions_earlier=prior,
        median_20_session=median,
        direction=direction,
    )


def _parse_macro(record: Mapping[str, object], metadata: EvidenceMetadata) -> MacroEvidence:
    _strict_keys(record, "macro", {"state", "reason_codes"})
    try:
        state = MacroState(_string(record.get("state"), "macro.state"))
    except ValueError as error:
        raise EvidenceValidationError("invalid macro.state") from error
    raw_reasons = record.get("reason_codes")
    if not isinstance(raw_reasons, list) or len(raw_reasons) > MAX_REASON_CODES:
        raise EvidenceValidationError("invalid macro.reason_codes")
    reasons = tuple(
        sorted({_identifier(value, "macro.reason_codes") for value in raw_reasons})
    )
    return MacroEvidence(**metadata.__dict__, state=state, reason_codes=reasons)


def _parse_catalyst(
    record: Mapping[str, object], metadata: EvidenceMetadata, as_of: datetime
) -> CatalystEvidence:
    _strict_keys(
        record,
        "catalyst",
        {
            "evidence_id",
            "symbol",
            "source_reference",
            "published_at",
            "materiality",
            "direction",
            "category",
        },
    )
    published_at = _timestamp(record.get("published_at"), "catalyst.published_at")
    if published_at > as_of:
        raise EvidenceValidationError("catalyst.published_at is after as_of")
    if published_at > metadata.observed_at:
        raise EvidenceValidationError("catalyst.published_at is after observed_at")
    try:
        materiality = CatalystMateriality(
            _string(record.get("materiality"), "catalyst.materiality")
        )
    except ValueError as error:
        raise EvidenceValidationError("invalid catalyst.materiality") from error
    try:
        direction = CatalystDirection(_string(record.get("direction"), "catalyst.direction"))
    except ValueError as error:
        raise EvidenceValidationError("invalid catalyst.direction") from error
    return CatalystEvidence(
        **metadata.__dict__,
        evidence_id=_identifier(record.get("evidence_id"), "catalyst.evidence_id"),
        symbol=_identifier(record.get("symbol"), "catalyst.symbol"),
        source_reference=_bounded_string(
            record.get("source_reference"),
            "catalyst.source_reference",
            MAX_REFERENCE_LENGTH,
        ),
        published_at=published_at,
        materiality=materiality,
        direction=direction,
        category=_identifier(record.get("category"), "catalyst.category"),
    )


def _strict_keys(
    record: Mapping[str, object],
    name: str,
    specific: set[str],
    *,
    include_common: bool = True,
) -> None:
    expected = specific | (set(_COMMON_FIELDS) if include_common else set())
    unknown = set(record) - expected
    if unknown:
        raise EvidenceValidationError(f"unexpected {name} field")
    missing = expected - set(record)
    if missing:
        field = sorted(missing)[0]
        raise EvidenceValidationError(f"invalid {name}.{field}")


def _as_of(value: datetime) -> datetime:
    try:
        return ensure_utc(value)
    except (TypeError, ValueError) as error:
        raise EvidenceValidationError("as_of must be timezone-aware") from error


def _timestamp(value: object, field: str) -> datetime:
    if not isinstance(value, str):
        raise EvidenceValidationError(f"invalid {field}")
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError as error:
        raise EvidenceValidationError(f"{field} must be a valid timestamp") from error
    try:
        return ensure_utc(parsed)
    except ValueError as error:
        raise EvidenceValidationError(f"{field} must be timezone-aware") from error


def _date(value: object, field: str) -> date:
    if not isinstance(value, str):
        raise EvidenceValidationError(f"invalid {field}")
    try:
        return date.fromisoformat(value)
    except ValueError as error:
        raise EvidenceValidationError(f"invalid {field}") from error


def _decimal(
    value: object,
    field: str,
    *,
    nonnegative: bool = False,
    positive: bool = False,
) -> Decimal:
    if not isinstance(value, str) or not value or len(value) > MAX_IDENTIFIER_LENGTH:
        raise EvidenceValidationError(f"invalid {field}")
    try:
        parsed = Decimal(value)
    except InvalidOperation as error:
        raise EvidenceValidationError(f"invalid {field}") from error
    if not parsed.is_finite() or (nonnegative and parsed < 0) or (positive and parsed <= 0):
        raise EvidenceValidationError(f"invalid {field}")
    return parsed


def _nonnegative_int(value: object, field: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise EvidenceValidationError(f"invalid {field}")
    return value


def _identifier(value: object, field: str) -> str:
    return _bounded_string(value, field, MAX_IDENTIFIER_LENGTH)


def _string(value: object, field: str) -> str:
    if not isinstance(value, str) or not value:
        raise EvidenceValidationError(f"invalid {field}")
    return value


def _bounded_string(value: object, field: str, maximum: int) -> str:
    result = _string(value, field)
    if len(result) > maximum or any(character in result for character in ("\x00", "\r", "\n")):
        raise EvidenceValidationError(f"invalid {field}")
    return result


def _mapping(value: object, field: str) -> Mapping[str, object]:
    if not isinstance(value, Mapping) or not all(isinstance(key, str) for key in value):
        raise EvidenceValidationError(f"invalid {field}")
    return cast(Mapping[str, object], value)


def _contains_forbidden_key(value: object) -> bool:
    if isinstance(value, Mapping):
        for key, nested in value.items():
            normalized = str(key).casefold().replace("-", "_").replace(" ", "_")
            if normalized in _PROHIBITED_CONTENT_KEYS or any(
                fragment in normalized for fragment in _SENSITIVE_KEY_FRAGMENTS
            ):
                return True
            if _contains_forbidden_key(nested):
                return True
    elif isinstance(value, (list, tuple)):
        return any(_contains_forbidden_key(item) for item in value)
    return False


def _catalyst_sort_key(value: CatalystEvidence) -> tuple[str, ...]:
    return (
        value.symbol,
        value.evidence_id,
        value.lineage_id,
        value.direction.value,
        value.published_at.isoformat(),
        value.observed_at.isoformat(),
        value.valid_until.isoformat(),
        value.source,
        value.source_reference,
    )


def _record_sort_key(value: EvidenceMetadata) -> tuple[str, ...]:
    return (
        value.lineage_id,
        value.source,
        value.observed_at.isoformat(),
        value.valid_until.isoformat(),
        repr(value),
    )
