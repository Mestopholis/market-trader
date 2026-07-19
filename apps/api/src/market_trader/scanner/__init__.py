"""Deterministic scanner domain contracts."""

from market_trader.scanner.models import (
    CandidateResult,
    ComponentScore,
    Direction,
    EligibilityResult,
    EligibilityStatus,
    EvidenceRef,
    FeatureSet,
    GateResult,
    PolicyVersions,
    RegimeResult,
    RegimeState,
    ScanCounts,
    ScannerInput,
    ScanResult,
    StrategyResult,
    StrategyStatus,
    SymbolInput,
)
from market_trader.scanner.serialization import canonical_record, stable_digest

__all__ = [
    "CandidateResult",
    "ComponentScore",
    "Direction",
    "EligibilityResult",
    "EligibilityStatus",
    "EvidenceRef",
    "FeatureSet",
    "GateResult",
    "PolicyVersions",
    "RegimeResult",
    "RegimeState",
    "ScanCounts",
    "ScanResult",
    "ScannerInput",
    "StrategyResult",
    "StrategyStatus",
    "SymbolInput",
    "canonical_record",
    "stable_digest",
]

