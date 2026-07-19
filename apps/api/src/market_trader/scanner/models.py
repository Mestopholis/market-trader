from collections.abc import Mapping
from dataclasses import dataclass, fields, is_dataclass
from datetime import date, datetime
from decimal import Decimal
from enum import Enum, StrEnum
from types import MappingProxyType
from typing import cast

from market_trader.domain.time import ensure_utc
from market_trader.market_data.models import (
    NormalizedCandle,
    NormalizedCorporateAction,
    NormalizedProviderState,
    NormalizedQuote,
)
from market_trader.market_data.sanitization import canonical_json, sanitize_payload

_SCORE_QUANTUM = Decimal("0.000001")


class Direction(StrEnum):
    BULLISH = "bullish"
    BEARISH = "bearish"


class EligibilityStatus(StrEnum):
    ELIGIBLE = "eligible"
    INELIGIBLE = "ineligible"
    BLOCKED = "blocked"


class RegimeState(StrEnum):
    BULLISH = "bullish"
    BEARISH = "bearish"
    NEUTRAL = "neutral"
    MIXED = "mixed"
    BLOCKED = "blocked"


class StrategyStatus(StrEnum):
    PASSED = "passed"
    FAILED = "failed"
    BLOCKED = "blocked"
    NOT_APPLICABLE = "not_applicable"


@dataclass(frozen=True)
class EvidenceRef:
    lineage_id: str
    source: str
    event_id: str
    ingestion_key: str
    payload_digest: str
    observed_at: datetime
    ingested_at: datetime

    def __post_init__(self) -> None:
        object.__setattr__(self, "observed_at", ensure_utc(self.observed_at))
        object.__setattr__(self, "ingested_at", ensure_utc(self.ingested_at))


@dataclass(frozen=True)
class PolicyVersions:
    universe: str = "eligible-universe-v1"
    eligibility: str = "eligibility-policy-v1"
    features: str = "scanner-features-v1"
    regime: str = "market-regime-v1"
    strategies: str = "scanner-strategies-v1"
    scoring: str = "candidate-scoring-v1"
    evidence: str = "scanner-evidence-v1"
    fixture: str = "scanner-fixture-v1"


@dataclass(frozen=True)
class SymbolInput:
    symbol: str
    daily_candles: tuple[NormalizedCandle, ...] = ()
    intraday_candles: tuple[NormalizedCandle, ...] = ()
    quotes: tuple[NormalizedQuote, ...] = ()
    provider_states: tuple[NormalizedProviderState, ...] = ()
    corporate_actions: tuple[NormalizedCorporateAction, ...] = ()
    evidence: tuple[EvidenceRef, ...] = ()
    attributes: Mapping[str, object] = MappingProxyType({})

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "daily_candles",
            tuple(sorted(self.daily_candles, key=_stable_sort_key)),
        )
        object.__setattr__(
            self,
            "intraday_candles",
            tuple(sorted(self.intraday_candles, key=_stable_sort_key)),
        )
        object.__setattr__(self, "quotes", tuple(sorted(self.quotes, key=_stable_sort_key)))
        object.__setattr__(
            self,
            "provider_states",
            tuple(sorted(self.provider_states, key=_stable_sort_key)),
        )
        object.__setattr__(
            self,
            "corporate_actions",
            tuple(sorted(self.corporate_actions, key=_stable_sort_key)),
        )
        object.__setattr__(self, "evidence", _sorted_evidence(self.evidence))
        object.__setattr__(self, "attributes", _immutable_mapping(self.attributes))


@dataclass(frozen=True)
class ScannerInput:
    as_of: datetime
    session_date: date
    versions: PolicyVersions
    symbols: tuple[SymbolInput, ...]
    supplemental_evidence: tuple[EvidenceRef, ...] = ()
    configuration_hashes: Mapping[str, str] = MappingProxyType({})

    def __post_init__(self) -> None:
        object.__setattr__(self, "as_of", ensure_utc(self.as_of))
        object.__setattr__(
            self,
            "symbols",
            tuple(sorted(self.symbols, key=_stable_sort_key)),
        )
        object.__setattr__(
            self,
            "supplemental_evidence",
            _sorted_evidence(self.supplemental_evidence),
        )
        object.__setattr__(
            self,
            "configuration_hashes",
            _immutable_mapping(self.configuration_hashes),
        )


@dataclass(frozen=True)
class FeatureSet:
    symbol: str
    values: Mapping[str, Decimal | int | None] = MappingProxyType({})
    reasons: tuple[str, ...] = ()
    lineage: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "values", _immutable_mapping(self.values))
        object.__setattr__(self, "reasons", _ordered_unique(self.reasons))
        object.__setattr__(self, "lineage", _ordered_unique(self.lineage))


@dataclass(frozen=True)
class RegimeResult:
    state: RegimeState
    signed_score: Decimal
    policy_version: str
    components: Mapping[str, Decimal] = MappingProxyType({})
    reasons: tuple[str, ...] = ()
    lineage: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "signed_score", _score(self.signed_score))
        object.__setattr__(self, "components", _immutable_mapping(self.components))
        object.__setattr__(self, "reasons", _ordered_unique(self.reasons))
        object.__setattr__(self, "lineage", _ordered_unique(self.lineage))


@dataclass(frozen=True)
class EligibilityResult:
    symbol: str
    status: EligibilityStatus
    policy_version: str
    reasons: tuple[str, ...] = ()
    observed: Mapping[str, object] = MappingProxyType({})

    def __post_init__(self) -> None:
        object.__setattr__(self, "reasons", _ordered_unique(self.reasons))
        object.__setattr__(self, "observed", _immutable_mapping(self.observed))


@dataclass(frozen=True)
class GateResult:
    name: str
    passed: bool | None
    required: bool = True
    reasons: tuple[str, ...] = ()
    observed: Mapping[str, object] = MappingProxyType({})

    def __post_init__(self) -> None:
        object.__setattr__(self, "reasons", _ordered_unique(self.reasons))
        object.__setattr__(self, "observed", _immutable_mapping(self.observed))


@dataclass(frozen=True)
class ComponentScore:
    family: str
    pre_cap: Decimal
    cap: Decimal
    final: Decimal
    lineage: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "pre_cap", _score(self.pre_cap))
        object.__setattr__(self, "cap", _score(self.cap))
        object.__setattr__(self, "final", _score(self.final))
        object.__setattr__(self, "lineage", _ordered_unique(self.lineage))


@dataclass(frozen=True)
class StrategyResult:
    signal_key: str
    symbol: str
    strategy_id: str
    policy_version: str
    direction: Direction
    status: StrategyStatus
    gates: tuple[GateResult, ...] = ()
    components: tuple[ComponentScore, ...] = ()
    reasons: tuple[str, ...] = ()
    lineage: tuple[str, ...] = ()
    input_references: tuple[EvidenceRef, ...] = ()
    primary_ingestion_key: str | None = None
    input_digest: str | None = None
    score: Decimal | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "gates", tuple(sorted(self.gates, key=_stable_sort_key)))
        object.__setattr__(
            self,
            "components",
            tuple(sorted(self.components, key=_stable_sort_key)),
        )
        object.__setattr__(self, "reasons", _ordered_unique(self.reasons))
        object.__setattr__(self, "lineage", _ordered_unique(self.lineage))
        object.__setattr__(self, "input_references", _sorted_evidence(self.input_references))
        if self.score is not None:
            object.__setattr__(self, "score", _score(self.score))


@dataclass(frozen=True)
class CandidateResult:
    candidate_key: str
    signal_key: str
    symbol: str
    strategy_id: str
    direction: Direction
    score: Decimal
    status: str = "qualified"
    reasons: tuple[str, ...] = ()
    input_digest: str | None = None

    def __post_init__(self) -> None:
        if self.status != "qualified":
            raise ValueError("scanner candidate status must be qualified")
        object.__setattr__(self, "score", _score(self.score))
        object.__setattr__(self, "reasons", _ordered_unique(self.reasons))


@dataclass(frozen=True)
class ScanCounts:
    eligible: int = 0
    ineligible: int = 0
    blocked: int = 0
    signals: int = 0
    candidates: int = 0

    def __post_init__(self) -> None:
        if min(self.eligible, self.ineligible, self.blocked, self.signals, self.candidates) < 0:
            raise ValueError("scan counts must be nonnegative")


@dataclass(frozen=True)
class ScanResult:
    run_key: str
    as_of: datetime
    session_date: date
    versions: PolicyVersions
    input_digest: str
    regime: RegimeResult
    eligibility: tuple[EligibilityResult, ...]
    strategies: tuple[StrategyResult, ...]
    candidates: tuple[CandidateResult, ...]
    counts: ScanCounts
    result_digest: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "as_of", ensure_utc(self.as_of))
        object.__setattr__(
            self,
            "eligibility",
            tuple(sorted(self.eligibility, key=_stable_sort_key)),
        )
        object.__setattr__(
            self,
            "strategies",
            tuple(sorted(self.strategies, key=_stable_sort_key)),
        )
        object.__setattr__(
            self,
            "candidates",
            tuple(sorted(self.candidates, key=_stable_sort_key)),
        )


def _score(value: Decimal) -> Decimal:
    return value.quantize(_SCORE_QUANTUM)


def _ordered_unique(values: tuple[str, ...]) -> tuple[str, ...]:
    return tuple(sorted(set(values)))


def _immutable_mapping[T](values: Mapping[str, T]) -> Mapping[str, T]:
    frozen = {key: _freeze_value(value) for key, value in values.items()}
    return cast(Mapping[str, T], MappingProxyType(frozen))


def _sorted_evidence(values: tuple[EvidenceRef, ...]) -> tuple[EvidenceRef, ...]:
    return tuple(sorted(values, key=_stable_sort_key))


def _freeze_value(value: object) -> object:
    if isinstance(value, Mapping):
        return MappingProxyType(
            {str(key): _freeze_value(item) for key, item in value.items()}
        )
    if isinstance(value, (list, tuple)):
        return tuple(_freeze_value(item) for item in value)
    return value


def _stable_sort_key(value: object) -> str:
    return canonical_json(sanitize_payload(_structural_value(value)))


def _structural_value(value: object) -> object:
    if isinstance(value, Enum):
        return value.value
    if is_dataclass(value) and not isinstance(value, type):
        return {item.name: _structural_value(getattr(value, item.name)) for item in fields(value)}
    if isinstance(value, Mapping):
        return {
            str(key): _structural_value(item)
            for key, item in sorted(value.items(), key=lambda pair: str(pair[0]))
        }
    if isinstance(value, (list, tuple)):
        return [_structural_value(item) for item in value]
    return value
