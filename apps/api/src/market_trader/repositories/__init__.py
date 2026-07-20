"""Repository boundaries for persisted domain records."""

from market_trader.repositories.catalysts import (
    CatalystPersistenceConflict,
    CatalystRepository,
    PersistedCatalystSourceRun,
)
from market_trader.repositories.options_analysis import (
    OptionsAnalysisPersistenceConflict,
    OptionsAnalysisPersistenceError,
    OptionsAnalysisRepository,
    PersistedOptionsAnalysisRun,
)
from market_trader.repositories.risk_decisions import (
    PersistedRiskDecision,
    RiskDecisionPersistenceConflict,
    RiskDecisionPersistenceError,
    RiskDecisionRepository,
)
from market_trader.repositories.scanner import (
    PersistedScanRun,
    ScannerPersistenceConflict,
    ScannerPersistenceError,
    ScannerRepository,
)

__all__ = [
    "CatalystPersistenceConflict",
    "CatalystRepository",
    "OptionsAnalysisPersistenceConflict",
    "OptionsAnalysisPersistenceError",
    "OptionsAnalysisRepository",
    "PersistedScanRun",
    "PersistedCatalystSourceRun",
    "PersistedOptionsAnalysisRun",
    "PersistedRiskDecision",
    "RiskDecisionPersistenceConflict",
    "RiskDecisionPersistenceError",
    "RiskDecisionRepository",
    "ScannerPersistenceConflict",
    "ScannerPersistenceError",
    "ScannerRepository",
]
