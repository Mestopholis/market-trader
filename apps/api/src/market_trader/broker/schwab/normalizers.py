from __future__ import annotations

from collections.abc import Mapping
from datetime import UTC, datetime

from market_trader.market_data.models import DataKind, ProviderEvent
from market_trader.market_data.sanitization import canonical_digest, sanitize_payload

_SOURCE = "schwab"
_FIXTURE_SCHEMA_VERSION = 1
_CONFIGURATION_VERSION = "schwab-market-data-v1"


def normalize_schwab_quotes(
    payload: object,
    *,
    observed_at: datetime,
    ingested_at: datetime,
    correlation_id: str = "corr-unavailable",
) -> tuple[ProviderEvent, ...]:
    if not isinstance(payload, Mapping):
        return ()
    events: list[ProviderEvent] = []
    for raw_symbol, raw_quote in payload.items():
        if not isinstance(raw_quote, Mapping):
            continue
        symbol = str(raw_quote.get("symbol") or raw_symbol).upper()
        quote = raw_quote.get("quote")
        if not isinstance(quote, Mapping):
            continue
        normalized: dict[str, object] = {
            "symbol": symbol,
            "bid": _decimal_string(quote.get("bidPrice")),
            "ask": _decimal_string(quote.get("askPrice")),
            "bid_size": _integer(quote.get("bidSize")),
            "ask_size": _integer(quote.get("askSize")),
            "last": _optional_decimal_string(quote.get("lastPrice")),
            "last_size": _optional_integer(quote.get("lastSize")),
            "last_at": _millis_to_iso(quote.get("tradeTime")),
            "bid_venue": _optional_string(quote.get("bidMICId")),
            "ask_venue": _optional_string(quote.get("askMICId")),
            "trade_venue": _optional_string(quote.get("lastMICId")),
            "condition_codes": [],
            "schema_version": 1,
        }
        events.append(
            ProviderEvent(
                source=_SOURCE,
                event_id=_event_id("quote", normalized),
                data_kind=DataKind.QUOTE,
                observed_at=observed_at,
                ingested_at=ingested_at,
                payload=normalized,
                fixture_schema_version=_FIXTURE_SCHEMA_VERSION,
                configuration_version=_CONFIGURATION_VERSION,
                correlation_id=correlation_id,
            )
        )
    return tuple(events)


def normalize_schwab_option_chain(
    payload: object,
    *,
    observed_at: datetime,
    ingested_at: datetime,
    correlation_id: str = "corr-unavailable",
) -> ProviderEvent:
    normalized: dict[str, object] = {
        "underlying": "",
        "session_date": observed_at.date().isoformat(),
        "completeness": "partial",
        "contracts": [],
        "schema_version": 1,
    }
    if isinstance(payload, Mapping):
        underlying = payload.get("symbol")
        if isinstance(payload.get("underlying"), Mapping):
            underlying_mapping = payload["underlying"]
            underlying = underlying_mapping.get("symbol")
        normalized["underlying"] = str(underlying or "").upper()
        normalized["completeness"] = (
            "complete" if str(payload.get("status", "")).upper() == "SUCCESS" else "partial"
        )
        normalized["contracts"] = _option_contracts(payload)
    return ProviderEvent(
        source=_SOURCE,
        event_id=_event_id("option-chain", normalized),
        data_kind=DataKind.OPTION_CHAIN,
        observed_at=observed_at,
        ingested_at=ingested_at,
        payload=normalized,
        fixture_schema_version=_FIXTURE_SCHEMA_VERSION,
        configuration_version=_CONFIGURATION_VERSION,
        correlation_id=correlation_id,
    )


def _option_contracts(payload: Mapping[object, object]) -> list[dict[str, object]]:
    contracts: list[dict[str, object]] = []
    for map_name, option_type in (("callExpDateMap", "call"), ("putExpDateMap", "put")):
        raw_expirations = payload.get(map_name)
        if not isinstance(raw_expirations, Mapping):
            continue
        for raw_strikes in raw_expirations.values():
            if not isinstance(raw_strikes, Mapping):
                continue
            for raw_contracts in raw_strikes.values():
                if not isinstance(raw_contracts, list):
                    continue
                for contract in raw_contracts:
                    if isinstance(contract, Mapping):
                        contracts.append(_option_contract(contract, option_type=option_type))
    return contracts


def _option_contract(contract: Mapping[object, object], *, option_type: str) -> dict[str, object]:
    expiration = _optional_string(contract.get("expirationDate"))
    return {
        "contract_id": _optional_string(contract.get("symbol")) or "",
        "expiration": expiration[:10] if expiration else "",
        "strike": _decimal_string(contract.get("strikePrice")),
        "option_type": option_type,
        "deliverable": "unsupported" if bool(contract.get("nonStandard")) else "standard",
        "bid": _decimal_string(contract.get("bid")),
        "ask": _decimal_string(contract.get("ask")),
        "bid_size": _integer(contract.get("bidSize")),
        "ask_size": _integer(contract.get("askSize")),
        "last": _optional_decimal_string(contract.get("last")),
        "volume": _optional_integer(contract.get("totalVolume")),
        "open_interest": _optional_integer(contract.get("openInterest")),
        "implied_volatility": _volatility(contract.get("volatility")),
        "delta": _optional_decimal_string(contract.get("delta")),
        "gamma": _optional_decimal_string(contract.get("gamma")),
        "theta": _optional_decimal_string(contract.get("theta")),
        "vega": _optional_decimal_string(contract.get("vega")),
    }


def _event_id(prefix: str, payload: dict[str, object]) -> str:
    sanitized = sanitize_payload(payload)
    return f"schwab-{prefix}-{canonical_digest(sanitized)[:16]}"


def _millis_to_iso(value: object) -> str | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return datetime.fromtimestamp(value / 1000, tz=UTC).isoformat()


def _decimal_string(value: object) -> str:
    if value is None:
        return ""
    return str(value)


def _optional_decimal_string(value: object) -> str | None:
    if value is None:
        return None
    return str(value)


def _volatility(value: object) -> str | None:
    if value is None:
        return None
    return str(float(str(value)) / 100)


def _integer(value: object) -> int:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return 0
    return int(value)


def _optional_integer(value: object) -> int | None:
    if value is None:
        return None
    return _integer(value)


def _optional_string(value: object) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None
