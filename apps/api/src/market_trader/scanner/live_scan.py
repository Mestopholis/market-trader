from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta

from sqlalchemy.orm import Session

from market_trader.domain.time import ensure_utc, utc_now
from market_trader.repositories.scanner import ScannerRepository
from market_trader.scanner.configuration import ScannerConfiguration
from market_trader.scanner.engine import ScannerEngine
from market_trader.scanner.live_input import build_scanner_input_from_market_data


@dataclass(frozen=True)
class SchwabLiveScanResult:
    source: str
    run_key: str
    result_digest: str
    counts: dict[str, int]


class SchwabLiveScannerService:
    def __init__(self, *, configuration: ScannerConfiguration) -> None:
        self._configuration = configuration

    def scan(
        self,
        session: Session,
        *,
        source: str = "schwab",
        as_of: datetime | None = None,
        observed_lookback_minutes: int = 15,
        correlation_id: str,
    ) -> SchwabLiveScanResult:
        if observed_lookback_minutes <= 0:
            raise ValueError("observed_lookback_minutes must be positive")
        scan_as_of = ensure_utc(as_of) if as_of is not None else utc_now()
        scanner_input = build_scanner_input_from_market_data(
            session,
            configuration=self._configuration,
            as_of=scan_as_of,
            observed_from=scan_as_of - timedelta(minutes=observed_lookback_minutes),
            source=source,
        )
        result = ScannerEngine(self._configuration).scan(scanner_input)
        ScannerRepository(session).persist(result)
        _ = correlation_id
        return SchwabLiveScanResult(
            source=source,
            run_key=result.run_key,
            result_digest=result.result_digest,
            counts={
                "eligible": result.counts.eligible,
                "ineligible": result.counts.ineligible,
                "blocked": result.counts.blocked,
                "signals": result.counts.signals,
                "candidates": result.counts.candidates,
            },
        )
