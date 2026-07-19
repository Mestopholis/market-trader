from datetime import datetime

from market_trader.catalysts.models import (
    CatalystDecision,
    CatalystDirection,
    CatalystPolicyVersions,
    ConfirmationState,
    Materiality,
    RiskState,
)
from market_trader.domain.time import ensure_utc
from market_trader.scanner.evidence import (
    EVIDENCE_SCHEMA_VERSION,
    CatalystEvidence,
    CatalystMateriality,
    EvidenceMetadata,
    MacroEvidence,
    MacroState,
    SupplementalEvidence,
)
from market_trader.scanner.evidence import (
    CatalystDirection as ScannerDirection,
)

_SOURCE = "catalyst-decision"


class ScannerCatalystAdapter:
    def adapt(
        self,
        decisions: tuple[CatalystDecision, ...],
        *,
        as_of: datetime,
    ) -> SupplementalEvidence:
        reference = ensure_utc(as_of)
        catalysts: list[CatalystEvidence] = []
        macro: list[MacroEvidence] = []
        for decision in sorted(decisions, key=lambda item: item.decision_key):
            if decision.as_of != reference:
                continue
            if decision.scope == "market":
                if decision.risk_state is not RiskState.CLEAR:
                    macro.append(_macro_evidence(decision, reference))
                continue
            if decision.symbol is None:
                continue
            if decision.risk_state is not RiskState.CLEAR:
                catalysts.append(_blocked_symbol_evidence(decision, reference))
                continue
            if decision.confirmation is ConfirmationState.BLOCKED:
                catalysts.append(_blocked_symbol_evidence(decision, reference))
                continue
            if _can_confirm_news(decision):
                catalysts.append(_news_evidence(decision, reference))
        return SupplementalEvidence(
            as_of=reference,
            breadth=(),
            sector=(),
            volatility=(),
            macro=tuple(macro),
            catalysts=tuple(catalysts),
        )


def _can_confirm_news(decision: CatalystDecision) -> bool:
    return (
        decision.confirmation is ConfirmationState.CONFIRMED
        and decision.materiality is Materiality.MATERIAL
        and decision.direction
        in (CatalystDirection.POSITIVE, CatalystDirection.NEGATIVE)
    )


def _news_evidence(decision: CatalystDecision, as_of: datetime) -> CatalystEvidence:
    direction = (
        ScannerDirection.POSITIVE
        if decision.direction is CatalystDirection.POSITIVE
        else ScannerDirection.NEGATIVE
    )
    return CatalystEvidence(
        **_metadata(decision, as_of).__dict__,
        evidence_id=decision.decision_key,
        symbol=_symbol(decision),
        source_reference=f"decision:{decision.decision_key}",
        published_at=as_of,
        materiality=CatalystMateriality.MATERIAL,
        direction=direction,
        category="catalyst_decision",
        observation_keys=decision.observation_keys,
        policy_versions=_policy_versions(decision.policy_versions),
    )


def _blocked_symbol_evidence(
    decision: CatalystDecision, as_of: datetime
) -> CatalystEvidence:
    return CatalystEvidence(
        **_metadata(decision, as_of).__dict__,
        evidence_id=decision.decision_key,
        symbol=_symbol(decision),
        source_reference=f"decision:{decision.decision_key}",
        published_at=as_of,
        materiality=CatalystMateriality.NON_MATERIAL,
        direction=ScannerDirection.UNCLEAR,
        category=_risk_category(decision, "catalyst_decision"),
        blocked=True,
        reason_codes=decision.reasons or ("catalyst_decision_blocked",),
        observation_keys=_lineage(decision),
        policy_versions=_policy_versions(decision.policy_versions),
    )


def _macro_evidence(decision: CatalystDecision, as_of: datetime) -> MacroEvidence:
    return MacroEvidence(
        **_metadata(decision, as_of).__dict__,
        state=MacroState.BLOCKED,
        reason_codes=decision.reasons or ("macro_catalyst_blocked",),
        observation_keys=_lineage(decision),
        policy_versions=_policy_versions(decision.policy_versions),
    )


def _metadata(decision: CatalystDecision, as_of: datetime) -> EvidenceMetadata:
    versions = _policy_versions(decision.policy_versions)
    return EvidenceMetadata(
        schema_version=EVIDENCE_SCHEMA_VERSION,
        configuration_version="|".join(versions),
        correlation_id=decision.input_digest,
        lineage_id=decision.decision_key,
        source=_SOURCE,
        observed_at=as_of,
        valid_until=as_of,
    )


def _policy_versions(versions: CatalystPolicyVersions) -> tuple[str, ...]:
    return (
        versions.source,
        versions.classification,
        versions.risk,
        versions.summary,
        versions.fixture,
    )


def _lineage(decision: CatalystDecision) -> tuple[str, ...]:
    values = set(decision.observation_keys)
    raw_risks = decision.explanation.get("risk", ())
    if isinstance(raw_risks, tuple):
        for risk in raw_risks:
            if not isinstance(risk, tuple) or len(risk) != 3:
                continue
            raw_lineage = risk[2]
            if isinstance(raw_lineage, tuple):
                values.update(item for item in raw_lineage if isinstance(item, str))
    return tuple(sorted(values))


def _risk_category(decision: CatalystDecision, fallback: str) -> str:
    raw_risks = decision.explanation.get("risk", ())
    if isinstance(raw_risks, tuple):
        categories = sorted(
            risk[0]
            for risk in raw_risks
            if isinstance(risk, tuple)
            and len(risk) == 3
            and isinstance(risk[0], str)
        )
        if categories:
            return categories[0]
    return fallback


def _symbol(decision: CatalystDecision) -> str:
    assert decision.symbol is not None
    return decision.symbol
