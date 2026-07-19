from collections.abc import Mapping
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from typing import NoReturn

from market_trader.catalysts.configuration import ClassificationPolicy
from market_trader.catalysts.models import (
    AuthorityClass,
    CatalystDirection,
    CatalystObservation,
    EventFamily,
    Materiality,
)

_COMPANY_CATEGORIES = frozenset(
    (
        "acquisition_announced",
        "bankruptcy_filing",
        "buyback_authorized",
        "cyber_incident",
        "dividend_cut",
        "dividend_increase",
        "executive_change",
        "going_concern",
        "regulatory_approval",
        "regulatory_denial",
    )
)
_HIGH_IMPACT_MACRO = frozenset(
    (
        "consumer_price_index",
        "employment_situation",
        "fomc_rate_decision",
        "total_nonfarm_payrolls",
        "unemployment_rate",
    )
)
_AUTHORIZED_CLASSES = frozenset(
    (
        AuthorityClass.OFFICIAL_STRUCTURED,
        AuthorityClass.AUTHORIZED_STRUCTURED,
    )
)


@dataclass(frozen=True)
class ObservationClassification:
    observation_key: str
    materiality: Materiality
    direction: CatalystDirection
    reasons: tuple[str, ...]
    policy_version: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "reasons", tuple(sorted(set(self.reasons))))


@dataclass(frozen=True)
class ClassifiedObservation:
    observation: CatalystObservation
    classification: ObservationClassification

    def __post_init__(self) -> None:
        if self.observation.observation_key != self.classification.observation_key:
            raise ValueError("classification observation key mismatch")


def classify_observation(
    observation: CatalystObservation,
    policy: ClassificationPolicy,
) -> ObservationClassification:
    if set(policy.categories) != _COMPANY_CATEGORIES:
        raise ValueError("classification policy contains an unversioned category")
    if observation.authority_class not in _AUTHORIZED_CLASSES:
        return _result(
            observation,
            policy,
            Materiality.UNKNOWN,
            CatalystDirection.UNCLEAR,
            ("source_not_authorized",),
        )
    if observation.event_family is EventFamily.EARNINGS:
        return _classify_earnings(observation, policy)
    if observation.event_family is EventFamily.COMPANY_NEWS:
        return _classify_company(observation, policy)
    if observation.event_family is EventFamily.SEC_FILING:
        return _classify_sec(observation, policy)
    if observation.event_family is EventFamily.ECONOMIC_RELEASE:
        return _classify_macro(observation, policy)
    if observation.event_family is EventFamily.SOCIAL:
        return _result(
            observation,
            policy,
            Materiality.CONTEXTUAL,
            CatalystDirection.UNCLEAR,
            ("direction_unclear",),
        )
    return _unknown(observation, policy)


def _classify_earnings(
    observation: CatalystObservation,
    policy: ClassificationPolicy,
) -> ObservationClassification:
    facts = observation.structured_facts
    if observation.event_category in ("guidance_raised", "guidance_lowered"):
        return _classify_guidance(observation, policy)
    if observation.event_category != "earnings_result":
        return _unknown(observation, policy)
    mismatch = _comparability_reason(facts)
    if mismatch is not None:
        return _blocked(observation, policy, mismatch)
    try:
        actual = _decimal(facts, "actual")
        consensus = _decimal(facts, "consensus")
    except _FactFailure as error:
        return _blocked(observation, policy, error.reason)
    if consensus == 0:
        return _blocked(observation, policy, "consensus_conflicting")
    surprise = (actual - consensus) / abs(consensus) * Decimal("100")
    threshold = policy.earnings_surprise_threshold
    if surprise >= threshold:
        return _result(
            observation,
            policy,
            Materiality.MATERIAL,
            CatalystDirection.POSITIVE,
        )
    if surprise <= -threshold:
        return _result(
            observation,
            policy,
            Materiality.MATERIAL,
            CatalystDirection.NEGATIVE,
        )
    return _result(
        observation,
        policy,
        Materiality.CONTEXTUAL,
        CatalystDirection.NEUTRAL,
    )


def _classify_guidance(
    observation: CatalystObservation,
    policy: ClassificationPolicy,
) -> ObservationClassification:
    mismatch = _comparability_reason(observation.structured_facts)
    if mismatch is not None:
        return _blocked(observation, policy, mismatch)
    try:
        low = _decimal(observation.structured_facts, "guidance_low")
        high = _decimal(observation.structured_facts, "guidance_high")
        prior_low = _decimal(observation.structured_facts, "prior_guidance_low")
        prior_high = _decimal(observation.structured_facts, "prior_guidance_high")
    except _FactFailure as error:
        return _blocked(observation, policy, error.reason)
    if low > high or prior_low > prior_high:
        return _blocked(observation, policy, "structured_fact_conflicting")
    raised = low > prior_low and high > prior_high
    lowered = low < prior_low and high < prior_high
    if observation.event_category == "guidance_raised" and raised:
        direction = CatalystDirection.POSITIVE
    elif observation.event_category == "guidance_lowered" and lowered:
        direction = CatalystDirection.NEGATIVE
    else:
        return _blocked(observation, policy, "structured_fact_conflicting")
    return _result(observation, policy, Materiality.MATERIAL, direction)


def _classify_company(
    observation: CatalystObservation,
    policy: ClassificationPolicy,
) -> ObservationClassification:
    configured = policy.categories.get(observation.event_category)
    if configured is None:
        return _unknown(observation, policy)
    if observation.event_category in ("dividend_increase", "dividend_cut"):
        try:
            old_amount = _decimal(observation.structured_facts, "old_amount")
            new_amount = _decimal(observation.structured_facts, "new_amount")
        except _FactFailure as error:
            return _blocked(observation, policy, error.reason)
        valid = (
            new_amount > old_amount
            if observation.event_category == "dividend_increase"
            else new_amount < old_amount
        )
        if not valid:
            return _blocked(observation, policy, "structured_fact_conflicting")
    if observation.event_category == "buyback_authorized":
        try:
            amount = _decimal(observation.structured_facts, "amount")
        except _FactFailure as error:
            return _blocked(observation, policy, error.reason)
        authorization_date = observation.structured_facts.get("authorization_date")
        if amount <= 0 or not isinstance(authorization_date, str) or not authorization_date:
            return _blocked(observation, policy, "structured_fact_missing")
    reasons = (
        ("direction_unclear",)
        if configured[1] is CatalystDirection.UNCLEAR
        else ()
    )
    return _result(observation, policy, configured[0], configured[1], reasons)


def _classify_sec(
    observation: CatalystObservation,
    policy: ClassificationPolicy,
) -> ObservationClassification:
    if observation.event_category != "sec_filing":
        return _unknown(observation, policy)
    form = observation.structured_facts.get("form")
    if not isinstance(form, str):
        return _blocked(observation, policy, "structured_fact_missing")
    base_form = form.removesuffix("/A")
    if base_form in ("8-K", "6-K"):
        materiality = Materiality.MATERIAL
    elif base_form in ("10-Q", "10-K", "20-F", "40-F"):
        materiality = Materiality.CONTEXTUAL
    else:
        return _unknown(observation, policy)
    return _result(
        observation,
        policy,
        materiality,
        CatalystDirection.UNCLEAR,
        ("direction_unclear",),
    )


def _classify_macro(
    observation: CatalystObservation,
    policy: ClassificationPolicy,
) -> ObservationClassification:
    if observation.event_category not in _HIGH_IMPACT_MACRO:
        return _unknown(observation, policy)
    facts = observation.structured_facts
    if "consensus" not in facts:
        return _result(
            observation,
            policy,
            Materiality.MATERIAL,
            CatalystDirection.NEUTRAL,
            ("consensus_missing",),
        )
    try:
        actual = _decimal(facts, "actual" if "actual" in facts else "value")
        consensus = _decimal(facts, "consensus")
    except _FactFailure as error:
        return _blocked(observation, policy, error.reason)
    direction = (
        CatalystDirection.POSITIVE
        if actual > consensus
        else CatalystDirection.NEGATIVE
        if actual < consensus
        else CatalystDirection.NEUTRAL
    )
    return _result(observation, policy, Materiality.MATERIAL, direction)


def _comparability_reason(facts: Mapping[str, object]) -> str | None:
    for field, reason in (
        ("period", "numeric_fact_period_mismatch"),
        ("unit", "numeric_fact_unit_mismatch"),
        ("currency", "numeric_fact_currency_mismatch"),
    ):
        actual = facts.get(f"actual_{field}")
        consensus = facts.get(f"consensus_{field}")
        if (actual is not None or consensus is not None) and (
            not isinstance(actual, str)
            or not isinstance(consensus, str)
            or actual != consensus
        ):
            return reason
    return None


class _FactFailure(ValueError):
    def __init__(self, reason: str) -> None:
        self.reason = reason
        super().__init__(reason)


def _decimal(facts: Mapping[str, object], field: str) -> Decimal:
    value = facts.get(field)
    if value is None:
        _fact_fail("structured_fact_missing")
    if not isinstance(value, str):
        _fact_fail("structured_fact_malformed")
    try:
        parsed = Decimal(value)
    except InvalidOperation:
        _fact_fail("structured_fact_malformed")
    if not parsed.is_finite():
        _fact_fail("numeric_fact_nonfinite")
    return parsed


def _unknown(
    observation: CatalystObservation,
    policy: ClassificationPolicy,
) -> ObservationClassification:
    return _result(
        observation,
        policy,
        Materiality.UNKNOWN,
        CatalystDirection.UNCLEAR,
        ("unknown_event_category",),
    )


def _blocked(
    observation: CatalystObservation,
    policy: ClassificationPolicy,
    reason: str,
) -> ObservationClassification:
    return _result(
        observation,
        policy,
        Materiality.UNKNOWN,
        CatalystDirection.UNCLEAR,
        (reason,),
    )


def _result(
    observation: CatalystObservation,
    policy: ClassificationPolicy,
    materiality: Materiality,
    direction: CatalystDirection,
    reasons: tuple[str, ...] = (),
) -> ObservationClassification:
    return ObservationClassification(
        observation_key=observation.observation_key,
        materiality=materiality,
        direction=direction,
        reasons=reasons,
        policy_version=policy.version,
    )


def _fact_fail(reason: str) -> NoReturn:
    raise _FactFailure(reason)
