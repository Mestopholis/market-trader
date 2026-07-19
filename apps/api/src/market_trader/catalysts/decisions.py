from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from types import MappingProxyType

from market_trader.catalysts.classification import ClassifiedObservation
from market_trader.catalysts.models import (
    AuthorityClass,
    CatalystDecision,
    CatalystDirection,
    CatalystPolicyVersions,
    ConfirmationState,
    EventFamily,
    EventRiskWindow,
    Materiality,
    RiskState,
    SourceState,
)
from market_trader.catalysts.serialization import stable_digest
from market_trader.domain.time import ensure_utc

_AUTHORITATIVE = frozenset(
    (
        AuthorityClass.OFFICIAL_STRUCTURED,
        AuthorityClass.AUTHORIZED_STRUCTURED,
    )
)


@dataclass(frozen=True)
class SourceStatus:
    source_id: str
    state: SourceState
    observed_at: datetime
    required: bool
    scope: str
    symbol: str | None
    reasons: tuple[str, ...]

    def __post_init__(self) -> None:
        object.__setattr__(self, "observed_at", ensure_utc(self.observed_at))
        object.__setattr__(self, "reasons", tuple(sorted(set(self.reasons))))
        if self.scope not in ("market", "symbol"):
            raise ValueError("source status scope must be market or symbol")
        if (self.scope == "symbol") != (self.symbol is not None):
            raise ValueError("source status symbol must match scope")


def decide_catalysts(
    observations: tuple[ClassifiedObservation, ...],
    risk_windows: tuple[EventRiskWindow, ...],
    source_states: tuple[SourceStatus, ...],
    *,
    as_of: datetime,
    policy_versions: CatalystPolicyVersions,
) -> tuple[CatalystDecision, ...]:
    reference = ensure_utc(as_of)
    scopes: set[tuple[str, str | None]] = {
        _observation_scope(item) for item in observations
    }
    scopes.update((window.scope, window.symbol) for window in risk_windows)
    scopes.update((status.scope, status.symbol) for status in source_states)
    decisions = tuple(
        _decide_scope(
            scope,
            symbol,
            observations=observations,
            risk_windows=risk_windows,
            source_states=source_states,
            as_of=reference,
            policy_versions=policy_versions,
        )
        for scope, symbol in sorted(scopes, key=lambda item: (item[0], item[1] or ""))
    )
    return decisions


def _decide_scope(
    scope: str,
    symbol: str | None,
    *,
    observations: tuple[ClassifiedObservation, ...],
    risk_windows: tuple[EventRiskWindow, ...],
    source_states: tuple[SourceStatus, ...],
    as_of: datetime,
    policy_versions: CatalystPolicyVersions,
) -> CatalystDecision:
    grouped = tuple(
        sorted(
            (item for item in observations if _observation_scope(item) == (scope, symbol)),
            key=lambda item: (
                item.observation.observation_key,
                item.observation.authoritative_digest,
            ),
        )
    )
    by_key: dict[str, ClassifiedObservation] = {}
    duplicate = False
    for item in grouped:
        key = item.observation.observation_key
        if key in by_key:
            duplicate = True
            continue
        by_key[key] = item
    unique = tuple(by_key[key] for key in sorted(by_key))
    reasons: set[str] = set()
    if duplicate:
        reasons.add("duplicate_evidence_lineage")
    current: list[ClassifiedObservation] = []
    for item in unique:
        observation = item.observation
        if observation.published_at > as_of:
            reasons.add("event_future_dated")
            continue
        if observation.valid_until < as_of:
            reasons.add("event_stale")
            continue
        if observation.authority_class not in _AUTHORITATIVE:
            reasons.add("source_not_authorized")
            continue
        current.append(item)

    statuses = tuple(
        sorted(
            (
                status
                for status in source_states
                if (status.scope, status.symbol) == (scope, symbol)
            ),
            key=lambda status: status.source_id,
        )
    )
    required_failure = False
    for status in statuses:
        if status.state is not SourceState.AVAILABLE:
            reasons.update(status.reasons or (f"source_{status.state.value}",))
            if status.required:
                required_failure = True

    windows = tuple(
        sorted(
            (
                window
                for window in risk_windows
                if (window.scope, window.symbol) == (scope, symbol)
            ),
            key=lambda window: (window.category, window.starts_at or as_of),
        )
    )
    risk_state = _risk_state(windows)
    for window in windows:
        if window.state is not RiskState.CLEAR:
            reasons.update(window.reasons)

    social = tuple(
        item for item in current if item.observation.event_family is EventFamily.SOCIAL
    )
    structured = tuple(
        item for item in current if item.observation.event_family is not EventFamily.SOCIAL
    )
    material = tuple(
        item
        for item in structured
        if item.classification.materiality is Materiality.MATERIAL
    )
    directions: set[CatalystDirection] = {
        item.classification.direction
        for item in material
        if item.classification.direction
        in (CatalystDirection.POSITIVE, CatalystDirection.NEGATIVE)
    }
    materiality = _materiality(current)
    direction = _direction(material, directions)

    if required_failure or risk_state is not RiskState.CLEAR:
        confirmation = ConfirmationState.BLOCKED
    elif len(directions) > 1:
        confirmation = ConfirmationState.BLOCKED
        direction = CatalystDirection.UNCLEAR
        reasons.add("conflicting_catalyst_direction")
    elif directions:
        confirmation = ConfirmationState.CONFIRMED
    elif social and not structured:
        confirmation = ConfirmationState.UNCONFIRMED
        reasons.discard("catalyst_unconfirmed")
        reasons.add("social_only_unconfirmed")
    else:
        confirmation = ConfirmationState.UNCONFIRMED
        reasons.add("catalyst_unconfirmed")
        if any(
            item.classification.direction is CatalystDirection.UNCLEAR
            for item in material
        ):
            reasons.add("direction_unclear")

    observation_keys = tuple(item.observation.observation_key for item in current)
    input_record = {
        "scope": scope,
        "symbol": symbol,
        "as_of": as_of,
        "observations": tuple(
            {
                "observation_key": item.observation.observation_key,
                "authoritative_digest": item.observation.authoritative_digest,
                "materiality": item.classification.materiality,
                "direction": item.classification.direction,
                "reasons": item.classification.reasons,
            }
            for item in current
        ),
        "risk_windows": windows,
        "source_states": statuses,
        "policy_versions": policy_versions,
        "excluded_reasons": tuple(sorted(reasons & {"event_future_dated", "event_stale"})),
    }
    input_digest = stable_digest(input_record)
    explanation: Mapping[str, object] = MappingProxyType(
        {
            "lineage": observation_keys,
            "risk": tuple(
                (window.category, window.state.value, window.lineage) for window in windows
            ),
            "sources": tuple(
                (status.source_id, status.state.value, status.required) for status in statuses
            ),
        }
    )
    return CatalystDecision(
        decision_key=f"decision_{stable_digest((scope, symbol, as_of, input_digest))}",
        scope=scope,
        symbol=symbol,
        as_of=as_of,
        materiality=materiality,
        direction=direction,
        confirmation=confirmation,
        risk_state=risk_state,
        reasons=tuple(reasons),
        observation_keys=observation_keys,
        policy_versions=policy_versions,
        input_digest=input_digest,
        explanation=explanation,
    )


def _observation_scope(item: ClassifiedObservation) -> tuple[str, str | None]:
    symbol = item.observation.symbol
    return ("market", None) if symbol is None else ("symbol", symbol)


def _risk_state(windows: tuple[EventRiskWindow, ...]) -> RiskState:
    states = {window.state for window in windows}
    if RiskState.BLOCKED in states:
        return RiskState.BLOCKED
    if RiskState.ACTIVE in states:
        return RiskState.ACTIVE
    return RiskState.CLEAR


def _materiality(observations: list[ClassifiedObservation]) -> Materiality:
    values = {item.classification.materiality for item in observations}
    if Materiality.MATERIAL in values:
        return Materiality.MATERIAL
    if Materiality.CONTEXTUAL in values:
        return Materiality.CONTEXTUAL
    return Materiality.UNKNOWN


def _direction(
    material: tuple[ClassifiedObservation, ...],
    directional: set[CatalystDirection],
) -> CatalystDirection:
    if len(directional) == 1:
        return next(iter(directional))
    if len(directional) > 1:
        return CatalystDirection.UNCLEAR
    if any(
        item.classification.direction is CatalystDirection.NEUTRAL for item in material
    ):
        return CatalystDirection.NEUTRAL
    return CatalystDirection.UNCLEAR
