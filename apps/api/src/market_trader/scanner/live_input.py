from __future__ import annotations

from collections.abc import Mapping
from datetime import date, datetime, timedelta
from decimal import Decimal

from sqlalchemy.orm import Session

from market_trader.domain.time import ensure_utc
from market_trader.market_calendar.adapter import XNYSCalendarAdapter
from market_trader.market_data.models import (
    NormalizedQuote,
    ObservationMetadata,
    QualityState,
)
from market_trader.repositories.market_data import MarketDataRepository, MarketDataSnapshot
from market_trader.repositories.symbols import SymbolRepository
from market_trader.scanner.configuration import ScannerConfiguration
from market_trader.scanner.models import EvidenceRef, ScannerInput, SymbolInput


def build_scanner_input_from_market_data(
    session: Session,
    *,
    configuration: ScannerConfiguration,
    as_of: datetime,
    observed_from: datetime,
    source: str = "schwab",
) -> ScannerInput:
    as_of_utc = ensure_utc(as_of)
    symbol_repository = SymbolRepository(session)
    market_data_repository = MarketDataRepository(session)
    symbols: list[SymbolInput] = []

    for entry in configuration.universe.entries:
        symbol = symbol_repository.get_symbol_by_display_symbol(entry.display_symbol)
        if symbol is None:
            continue
        snapshots = [
            snapshot
            for snapshot in market_data_repository.list_snapshots(
                symbol_id=symbol.id,
                source=source,
                observed_from=observed_from,
                observed_to=as_of_utc,
            )
            if snapshot.quality_state in configuration.eligibility.permitted_quality_states
        ]
        quotes = tuple(
            _quote_from_snapshot(snapshot)
            for snapshot in snapshots
            if snapshot.data_kind == "quote"
        )
        evidence = tuple(_evidence_from_snapshot(snapshot) for snapshot in snapshots)
        halted = any(
            "halt" in code.casefold() for quote in quotes for code in quote.condition_codes
        )
        symbols.append(
            SymbolInput(
                symbol=symbol.display_symbol,
                quotes=quotes,
                evidence=evidence,
                attributes={
                    "symbol_active": symbol.is_active,
                    "halted": halted,
                    "quote_updating": bool(quotes),
                    "adjustment_supported": True,
                    "corporate_actions_resolved": True,
                },
            )
        )

    return ScannerInput(
        as_of=as_of_utc,
        session_date=_session_date(as_of_utc),
        versions=configuration.versions,
        symbols=tuple(symbols),
        supplemental_evidence=None,
        configuration_hashes=configuration.content_hashes,
    )


def _quote_from_snapshot(snapshot: MarketDataSnapshot) -> NormalizedQuote:
    payload = snapshot.payload
    return NormalizedQuote(
        symbol=_string(payload, "symbol"),
        bid=_decimal(payload, "bid"),
        ask=_decimal(payload, "ask"),
        bid_size=_int(payload, "bid_size"),
        ask_size=_int(payload, "ask_size"),
        last=_optional_decimal(payload, "last"),
        last_size=_optional_int(payload, "last_size"),
        last_at=_optional_datetime(payload, "last_at"),
        bid_venue=_optional_string(payload, "bid_venue"),
        ask_venue=_optional_string(payload, "ask_venue"),
        trade_venue=_optional_string(payload, "trade_venue"),
        condition_codes=_string_tuple(payload.get("condition_codes", ()), "condition_codes"),
        metadata=_metadata(payload.get("metadata"), snapshot),
    )


def _metadata(value: object, snapshot: MarketDataSnapshot) -> ObservationMetadata:
    payload = _mapping(value, "metadata")
    return ObservationMetadata(
        source=_optional_string(payload, "source") or snapshot.source,
        event_id=_optional_string(payload, "event_id") or snapshot.ingestion_key,
        observed_at=_optional_datetime(payload, "observed_at") or snapshot.observed_at,
        ingested_at=_optional_datetime(payload, "ingested_at") or snapshot.ingested_at,
        session_date=_optional_date(payload, "session_date"),
        normalized_schema_version=_optional_int(payload, "normalized_schema_version")
        or snapshot.payload_schema_version,
        configuration_version=_optional_string(payload, "configuration_version")
        or "unknown",
        correlation_id=_optional_string(payload, "correlation_id") or snapshot.correlation_id,
        quality_state=QualityState(
            _optional_string(payload, "quality_state") or snapshot.quality_state
        ),
        quality_reasons=_string_tuple(payload.get("quality_reasons", ()), "quality_reasons"),
    )


def _evidence_from_snapshot(snapshot: MarketDataSnapshot) -> EvidenceRef:
    metadata = _mapping(snapshot.payload.get("metadata"), "metadata")
    event_id = _optional_string(metadata, "event_id") or snapshot.ingestion_key
    return EvidenceRef(
        lineage_id=snapshot.ingestion_key,
        source=snapshot.source,
        event_id=event_id,
        ingestion_key=snapshot.ingestion_key,
        payload_digest=snapshot.payload_digest,
        observed_at=snapshot.observed_at,
        ingested_at=snapshot.ingested_at,
    )


def _session_date(as_of: datetime) -> date:
    calendar = XNYSCalendarAdapter(
        start=as_of.date() - timedelta(days=7),
        end=as_of.date() + timedelta(days=7),
    )
    session = calendar.session_for_timestamp(as_of)
    if session is None:
        return as_of.date()
    return session.session_date


def _mapping(value: object, name: str) -> Mapping[str, object]:
    if not isinstance(value, Mapping):
        raise ValueError(f"{name} must be an object")
    return value


def _string(payload: Mapping[str, object], key: str) -> str:
    value = payload.get(key)
    if not isinstance(value, str) or not value:
        raise ValueError(f"{key} must be a non-empty string")
    return value


def _optional_string(payload: Mapping[str, object], key: str) -> str | None:
    value = payload.get(key)
    if value is None:
        return None
    if not isinstance(value, str):
        raise ValueError(f"{key} must be a string")
    return value


def _decimal(payload: Mapping[str, object], key: str) -> Decimal:
    value = payload.get(key)
    if value is None:
        raise ValueError(f"{key} is required")
    return Decimal(str(value))


def _optional_decimal(payload: Mapping[str, object], key: str) -> Decimal | None:
    value = payload.get(key)
    if value is None:
        return None
    return Decimal(str(value))


def _int(payload: Mapping[str, object], key: str) -> int:
    value = payload.get(key)
    if not isinstance(value, int) or isinstance(value, bool):
        raise ValueError(f"{key} must be an integer")
    return value


def _optional_int(payload: Mapping[str, object], key: str) -> int | None:
    value = payload.get(key)
    if value is None:
        return None
    if not isinstance(value, int) or isinstance(value, bool):
        raise ValueError(f"{key} must be an integer")
    return value


def _optional_datetime(payload: Mapping[str, object], key: str) -> datetime | None:
    value = payload.get(key)
    if value is None:
        return None
    if not isinstance(value, str):
        raise ValueError(f"{key} must be an ISO timestamp")
    return ensure_utc(datetime.fromisoformat(value.replace("Z", "+00:00")))


def _optional_date(payload: Mapping[str, object], key: str) -> date | None:
    value = payload.get(key)
    if value is None:
        return None
    if not isinstance(value, str):
        raise ValueError(f"{key} must be an ISO date")
    return date.fromisoformat(value)


def _string_tuple(value: object, name: str) -> tuple[str, ...]:
    if not isinstance(value, list | tuple):
        raise ValueError(f"{name} must be a list")
    items: list[str] = []
    for item in value:
        if not isinstance(item, str):
            raise ValueError(f"{name} must contain only strings")
        items.append(item)
    return tuple(items)
