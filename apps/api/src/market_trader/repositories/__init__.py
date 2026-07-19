"""Repository boundaries for persisted domain records."""

from market_trader.repositories.scanner import (
    PersistedScanRun,
    ScannerPersistenceConflict,
    ScannerPersistenceError,
    ScannerRepository,
)

__all__ = [
    "PersistedScanRun",
    "ScannerPersistenceConflict",
    "ScannerPersistenceError",
    "ScannerRepository",
]
