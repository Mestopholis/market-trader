from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from market_trader.broker.schwab.client import SchwabClientError, SchwabClientState
from market_trader.db.models import SchwabMarketDataSyncORM
from market_trader.domain.ids import new_domain_id
from market_trader.domain.time import Clock, SystemClock, ensure_utc
from market_trader.market_calendar.adapter import XNYSCalendarAdapter
from market_trader.market_data.fixtures import (
    FixtureDataset,
    FixtureExpectedCounts,
    FixtureManifest,
)
from market_trader.market_data.providers import (
    ProviderResponse,
    QuoteRequest,
    UnsupportedCapability,
)
from market_trader.market_data.replay import ReplayEngine, ReplayResult, VirtualReplayClock
from market_trader.market_data.sinks import RepositoryIngestionSink


@dataclass(frozen=True)
class SchwabLiveMarketDataIngestionResult:
    sync_key: str
    data_kind: str
    symbols: tuple[str, ...]
    provider_state: str
    accepted: int
    degraded: int
    stale: int
    quarantined: int
    deduplicated: int


class SchwabLiveMarketDataIngestionService:
    def __init__(
        self,
        *,
        provider: object,
        clock: Clock | None = None,
    ) -> None:
        self._provider = provider
        self._clock = clock or SystemClock()

    def refresh_quotes(
        self,
        session: Session,
        *,
        symbols: tuple[str, ...],
        correlation_id: str,
    ) -> SchwabLiveMarketDataIngestionResult:
        normalized_symbols = _normalize_symbols(symbols)
        sync_key = _sync_key("quote", normalized_symbols)
        try:
            response = self._provider.quotes(QuoteRequest(normalized_symbols))  # type: ignore[attr-defined]
        except SchwabClientError as error:
            provider_state = _provider_state_from_error(error.state)
            _store_sync(
                session,
                sync_key=sync_key,
                data_kind="quote",
                provider_state=provider_state,
                status="failed",
                observed_at=None,
                correlation_id=correlation_id,
                payload={"schema_version": 1, "error_code": error.code},
            )
            return SchwabLiveMarketDataIngestionResult(
                sync_key=sync_key,
                data_kind="quote",
                symbols=normalized_symbols,
                provider_state=provider_state,
                accepted=0,
                degraded=0,
                stale=0,
                quarantined=0,
                deduplicated=0,
            )
        if isinstance(response, UnsupportedCapability):
            _store_sync(
                session,
                sync_key=sync_key,
                data_kind="quote",
                provider_state="unavailable",
                status="unsupported",
                observed_at=None,
                correlation_id=correlation_id,
                payload={"schema_version": 1, "reason": response.reason},
            )
            return SchwabLiveMarketDataIngestionResult(
                sync_key=sync_key,
                data_kind="quote",
                symbols=normalized_symbols,
                provider_state="unavailable",
                accepted=0,
                degraded=0,
                stale=0,
                quarantined=0,
                deduplicated=0,
            )

        result = _ingest_provider_response(
            session,
            response=response,
            dataset_id=sync_key,
        )
        provider_state = "available" if result.quarantined == 0 else "quarantined"
        observed_at = max((event.observed_at for event in response), default=None)
        _store_sync(
            session,
            sync_key=sync_key,
            data_kind="quote",
            provider_state=provider_state,
            status="completed",
            observed_at=observed_at,
            correlation_id=correlation_id,
            payload={
                "schema_version": 1,
                "symbols": list(normalized_symbols),
                "accepted": result.accepted,
                "degraded": result.degraded,
                "stale": result.stale,
                "quarantined": result.quarantined,
                "deduplicated": result.deduplicated,
            },
        )
        return SchwabLiveMarketDataIngestionResult(
            sync_key=sync_key,
            data_kind="quote",
            symbols=normalized_symbols,
            provider_state=provider_state,
            accepted=result.accepted,
            degraded=result.degraded,
            stale=result.stale,
            quarantined=result.quarantined,
            deduplicated=result.deduplicated,
        )


def _ingest_provider_response(
    session: Session,
    *,
    response: ProviderResponse,
    dataset_id: str,
) -> ReplayResult:
    assert not isinstance(response, UnsupportedCapability)
    event_dates = [event.observed_at.date() for event in response]
    today = ensure_utc(SystemClock().now()).date()
    start = min(event_dates, default=today) - timedelta(days=1)
    end = max(event_dates, default=today) + timedelta(days=1)
    dataset = FixtureDataset(
        path=Path("."),
        manifest=FixtureManifest(
            dataset_id=dataset_id,
            description="Live Schwab Market Data ingestion",
            fixture_schema_version=1,
            source="schwab",
            configuration_version="schwab-market-data-v1",
            streams=(),
            expected_counts=FixtureExpectedCounts(
                accepted=0,
                degraded=0,
                stale=0,
                quarantined=0,
                deduplicated=0,
            ),
            expected_result_digest=None,
        ),
        events=response,
    )
    return ReplayEngine(
        clock=VirtualReplayClock(),
        calendar=XNYSCalendarAdapter(start=start, end=end),
        sink=RepositoryIngestionSink(session),
    ).replay(dataset)


def _store_sync(
    session: Session,
    *,
    sync_key: str,
    data_kind: str,
    provider_state: str,
    status: str,
    observed_at: datetime | None,
    correlation_id: str,
    payload: dict[str, object],
) -> None:
    now = ensure_utc(SystemClock().now())
    completed_at = now
    record = session.scalar(
        select(SchwabMarketDataSyncORM).where(SchwabMarketDataSyncORM.sync_key == sync_key)
    )
    if record is None:
        session.add(
            SchwabMarketDataSyncORM(
                id=new_domain_id("schwabsync"),
                sync_key=sync_key,
                data_kind=data_kind,
                status=status,
                provider_state=provider_state,
                observed_at=observed_at,
                completed_at=completed_at,
                payload=payload,
                correlation_id=correlation_id,
                created_at=completed_at,
            )
        )
        return
    record.status = status
    record.provider_state = provider_state
    record.observed_at = observed_at
    record.completed_at = completed_at
    record.payload = payload
    record.correlation_id = correlation_id


def _normalize_symbols(symbols: tuple[str, ...]) -> tuple[str, ...]:
    normalized = tuple(
        dict.fromkeys(symbol.strip().upper() for symbol in symbols if symbol.strip())
    )
    if not normalized:
        raise ValueError("at least one symbol is required")
    return normalized


def _sync_key(data_kind: str, symbols: tuple[str, ...]) -> str:
    return f"schwab:{data_kind}:{','.join(sorted(symbols))}"


def _provider_state_from_error(state: SchwabClientState) -> str:
    if state is SchwabClientState.RATE_LIMITED:
        return "rate_limited"
    if state is SchwabClientState.QUARANTINED:
        return "quarantined"
    return "unavailable"
