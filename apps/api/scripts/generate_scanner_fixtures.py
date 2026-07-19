from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from decimal import Decimal
from pathlib import Path

from market_trader.market_calendar.adapter import XNYSCalendarAdapter
from market_trader.market_calendar.models import ExchangeSession
from market_trader.market_data.replay import ReplayEngine, VirtualReplayClock
from market_trader.market_data.sinks import InMemoryIngestionSink
from market_trader.scanner.cli import _reason_summary
from market_trader.scanner.configuration import (
    ScannerConfiguration,
    load_scanner_configuration,
)
from market_trader.scanner.engine import ScannerEngine
from market_trader.scanner.fixtures import ScannerFixtureDataset, assemble_scanner_input

API_ROOT = Path(__file__).resolve().parents[1]
OUTPUT = API_ROOT / "fixtures" / "scanner"
CONFIGURATION_PATH = API_ROOT / "config" / "scanner"


@dataclass(frozen=True)
class Scenario:
    dataset_id: str
    session_date: date
    trend: str
    regime: str
    description: str
    provider_state: str = "available"
    halted: bool = False


SCENARIOS = (
    Scenario(
        dataset_id="bullish",
        session_date=date(2026, 7, 17),
        trend="bullish",
        regime="bullish",
        description=(
            "Bullish breakout, bullish pullback, and positive news continuation in a "
            "normal session with deterministic idempotence."
        ),
    ),
    Scenario(
        dataset_id="bearish",
        session_date=date(2026, 11, 2),
        trend="bearish",
        regime="bearish",
        description=(
            "Bearish breakdown, bearish failed rally, and negative news continuation "
            "across daylight-saving session timing."
        ),
    ),
    Scenario(
        dataset_id="neutral-mixed-blocked",
        session_date=date(2026, 11, 27),
        trend="neutral",
        regime="mixed",
        description=(
            "Neutral, mixed, and blocked regime interpretation on an early close, "
            "including stale and missing evidence behavior."
        ),
    ),
    Scenario(
        dataset_id="boundaries-and-conflicts",
        session_date=date(2026, 3, 9),
        trend="boundary",
        regime="bullish",
        provider_state="unavailable",
        halted=True,
        description=(
            "Threshold boundary, conflicting and halted inputs, unresolved corporate action, "
            "evidence deduplication, family cap, changed-input conflict, and exact idempotence."
        ),
    ),
)


def main() -> None:
    configuration = load_scanner_configuration(CONFIGURATION_PATH)
    for scenario in SCENARIOS:
        _write_scenario(scenario, configuration.content_hashes)
        _freeze_expected(scenario, configuration)


def _write_scenario(scenario: Scenario, hashes: Mapping[str, str]) -> None:
    path = OUTPUT / scenario.dataset_id
    path.mkdir(parents=True, exist_ok=True)
    calendar = XNYSCalendarAdapter(
        start=scenario.session_date - timedelta(days=500),
        end=scenario.session_date + timedelta(days=10),
    )
    current_session = calendar.session(scenario.session_date)
    as_of = current_session.market_open + timedelta(minutes=10)
    previous_sessions = _previous_sessions(calendar, scenario.session_date, 220)

    candle_records = _candle_records(scenario, previous_sessions, as_of)
    quote_records = [_quote_record(scenario, as_of)]
    state_records = [_state_record(scenario, as_of)]
    supplemental_records = _supplemental_records(scenario, as_of)
    files = {
        "market.ndjson": candle_records,
        "quotes.ndjson": quote_records,
        "states.ndjson": state_records,
        "supplemental.ndjson": supplemental_records,
    }
    descriptors: dict[str, tuple[str, int]] = {}
    for filename, records in files.items():
        content = "".join(_json_line(record) for record in records)
        (path / filename).write_text(content, encoding="utf-8")
        descriptors[filename] = (
            hashlib.sha256(content.encode()).hexdigest(),
            len(records),
        )

    manifest = {
        "dataset_id": scenario.dataset_id,
        "description": scenario.description,
        "scanner_fixture_schema_version": "scanner-fixture-v1",
        "as_of": as_of.isoformat(),
        "session_date": scenario.session_date.isoformat(),
        "source": "synthetic-scanner-fixture",
        "market_configuration_version": "market-data-fixtures-v1",
        "versions": {
            "universe": "eligible-universe-v1",
            "eligibility": "eligibility-policy-v1",
            "features": "scanner-features-v1",
            "regime": "market-regime-v1",
            "strategies": "scanner-strategies-v1",
            "scoring": "candidate-scoring-v1",
            "evidence": "scanner-evidence-v1",
            "fixture": "scanner-fixture-v1",
        },
        "configuration_hashes": dict(hashes),
        "market_streams": [
            _stream("market.ndjson", "candle", descriptors),
            _stream("quotes.ndjson", "quote", descriptors),
            _stream("states.ndjson", "provider_state", descriptors),
        ],
        "supplemental": {
            "filename": "supplemental.ndjson",
            "sha256": descriptors["supplemental.ndjson"][0],
            "record_count": descriptors["supplemental.ndjson"][1],
        },
        "expected": {
            "regime_state": "blocked",
            "regime_score": "0.000000",
            "eligible": 0,
            "ineligible": 0,
            "blocked": 30,
            "signals": 0,
            "candidates": 0,
            "reason_summary": {},
            "result_digest": "0" * 64,
        },
    }
    _write_manifest(path, manifest)


def _freeze_expected(scenario: Scenario, configuration: ScannerConfiguration) -> None:
    path = OUTPUT / scenario.dataset_id
    dataset = ScannerFixtureDataset.load(path)
    sink = InMemoryIngestionSink()
    event_dates = [event.observed_at.date() for event in dataset.market.events]
    ReplayEngine(
        clock=VirtualReplayClock(),
        calendar=XNYSCalendarAdapter(
            start=min(event_dates) - timedelta(days=370),
            end=max(event_dates) + timedelta(days=370),
        ),
        sink=sink,
    ).replay(dataset.market)
    result = ScannerEngine(configuration).scan(assemble_scanner_input(dataset, sink.accepted))
    manifest = json.loads((path / "manifest.json").read_text(encoding="utf-8"))
    manifest["expected"] = {
        "regime_state": result.regime.state.value,
        "regime_score": format(result.regime.signed_score, "f"),
        "eligible": result.counts.eligible,
        "ineligible": result.counts.ineligible,
        "blocked": result.counts.blocked,
        "signals": result.counts.signals,
        "candidates": result.counts.candidates,
        "reason_summary": _reason_summary(result),
        "result_digest": result.result_digest,
    }
    _write_manifest(path, manifest)


def _previous_sessions(
    calendar: XNYSCalendarAdapter, session_date: date, count: int
) -> tuple[ExchangeSession, ...]:
    sessions: list[ExchangeSession] = []
    cursor = session_date
    for _ in range(count):
        session = calendar.previous_session(cursor)
        sessions.append(session)
        cursor = session.session_date
    return tuple(reversed(sessions))


def _candle_records(
    scenario: Scenario, sessions: tuple[ExchangeSession, ...], as_of: datetime
) -> list[dict[str, object]]:
    records: list[dict[str, object]] = []
    closes: list[Decimal] = []
    for index, session in enumerate(sessions):
        close = _daily_close(scenario.trend, index)
        closes.append(close)
        records.append(
            _event(
                event_id=f"{scenario.dataset_id}-daily-{index:03d}",
                data_kind="candle",
                observed_at=session.market_close,
                ingested_at=session.market_close + timedelta(seconds=30),
                payload={
                    "schema_version": 1,
                    "scenario": scenario.dataset_id,
                    "symbol": "SPY",
                    "interval": "1d",
                    "start": session.market_open.isoformat(),
                    "end": session.market_close.isoformat(),
                    "open": str(close),
                    "high": str(close + Decimal("1")),
                    "low": str(close - Decimal("1")),
                    "close": str(close),
                    "volume": 2_500_000 if scenario.trend == "boundary" else 1_000_000,
                    "vwap": str(close),
                    "trade_count": 10_000,
                    "session_date": session.session_date.isoformat(),
                    "adjustment": "adjusted",
                },
            )
        )

    intraday_sessions = sessions[-20:]
    for session_index, session in enumerate(intraday_sessions):
        for minute in range(10):
            start = session.market_open + timedelta(minutes=minute)
            price = closes[-20 + session_index]
            records.append(
                _minute_event(
                    scenario,
                    f"history-{session_index:02d}-{minute:02d}",
                    start,
                    price,
                    volume=1_000,
                )
            )

    prior_high = max(closes[-20:]) + Decimal("1")
    prior_low = min(closes[-20:]) - Decimal("1")
    for minute in range(9):
        start = as_of - timedelta(minutes=10 - minute)
        if scenario.trend == "bullish":
            price = prior_high + Decimal("1") + Decimal(minute) / Decimal("10")
        elif scenario.trend == "bearish":
            price = prior_low - Decimal("1") - Decimal(minute) / Decimal("10")
        else:
            price = closes[-1]
        records.append(
            _minute_event(
                scenario,
                f"current-{minute:02d}",
                start,
                price,
                volume=3_000,
            )
        )
    return sorted(records, key=lambda record: str(record["ingested_at"]))


def _minute_event(
    scenario: Scenario,
    suffix: str,
    start: datetime,
    price: Decimal,
    *,
    volume: int,
) -> dict[str, object]:
    end = start + timedelta(minutes=1)
    close = price + (Decimal("0.05") if scenario.trend != "bearish" else Decimal("-0.05"))
    return _event(
        event_id=f"{scenario.dataset_id}-{suffix}",
        data_kind="candle",
        observed_at=end,
        ingested_at=end,
        payload={
            "schema_version": 1,
            "scenario": scenario.dataset_id,
            "symbol": "SPY",
            "interval": "1m",
            "start": start.isoformat(),
            "end": end.isoformat(),
            "open": str(price),
            "high": str(max(price, close) + Decimal("0.10")),
            "low": str(min(price, close) - Decimal("0.10")),
            "close": str(close),
            "volume": volume,
            "vwap": str(price),
            "trade_count": 100,
            "session_date": start.astimezone().date().isoformat(),
            "adjustment": "adjusted",
        },
    )


def _quote_record(scenario: Scenario, as_of: datetime) -> dict[str, object]:
    price = Decimal("220")
    return _event(
        event_id=f"{scenario.dataset_id}-quote",
        data_kind="quote",
        observed_at=as_of - timedelta(seconds=2),
        ingested_at=as_of - timedelta(seconds=1),
        payload={
            "schema_version": 1,
            "scenario": scenario.dataset_id,
            "symbol": "SPY",
            "bid": str(price - Decimal("0.05")),
            "ask": str(price + Decimal("0.05")),
            "bid_size": 100,
            "ask_size": 100,
            "last": str(price),
            "last_size": 50,
            "condition_codes": ["halt"] if scenario.halted else [],
        },
    )


def _state_record(scenario: Scenario, as_of: datetime) -> dict[str, object]:
    return _event(
        event_id=f"{scenario.dataset_id}-provider",
        data_kind="provider_state",
        observed_at=as_of - timedelta(milliseconds=500),
        ingested_at=as_of - timedelta(milliseconds=500),
        payload={
            "schema_version": 1,
            "scenario": scenario.dataset_id,
            "provider": "synthetic",
            "state": scenario.provider_state,
        },
    )


def _supplemental_records(scenario: Scenario, as_of: datetime) -> list[dict[str, object]]:
    bullish = scenario.regime == "bullish"
    bearish = scenario.regime == "bearish"
    common = {
        "schema_version": "scanner-evidence-v1",
        "configuration_version": "market-regime-v1",
        "source": "synthetic-scanner-fixture",
        "observed_at": (as_of - timedelta(minutes=1)).isoformat(),
        "valid_until": as_of.isoformat(),
    }
    above = "1.05" if bullish else "0.95" if bearish else "1.00"
    returns = (
        ["0.02"] * 11 if bullish else ["-0.02"] * 11 if bearish else ["0.01", "-0.01"] * 5 + ["0"]
    )
    records: list[dict[str, object]] = [
        {
            **common,
            "evidence_type": "breadth",
            "correlation_id": f"{scenario.dataset_id}-breadth",
            "lineage_id": f"{scenario.dataset_id}-breadth",
            "source_universe": "synthetic-us-listed",
            "session_date": scenario.session_date.isoformat(),
            "total_eligible_issues": 100,
            "advancing_issues": 65 if bullish else 30 if bearish else 50,
            "declining_issues": 30 if bullish else 65 if bearish else 50,
            "unchanged_issues": 5 if bullish or bearish else 0,
            "issues_above_sma_50": 65 if bullish else 35 if bearish else 50,
            "up_volume": "160" if bullish else "60" if bearish else "100",
            "down_volume": "100" if bullish else "100" if bearish else "100",
        },
        {
            **common,
            "evidence_type": "sector",
            "correlation_id": f"{scenario.dataset_id}-sector",
            "lineage_id": f"{scenario.dataset_id}-sector",
            "session_date": scenario.session_date.isoformat(),
            "observations": [
                {
                    "symbol": symbol,
                    "sector": sector,
                    "close_relative_to_sma_50": above,
                    "return_20_session": returns[index],
                }
                for index, (symbol, sector) in enumerate(_sectors())
            ],
        },
        {
            **common,
            "evidence_type": "volatility",
            "correlation_id": f"{scenario.dataset_id}-volatility",
            "lineage_id": f"{scenario.dataset_id}-volatility",
            "measure": "synthetic-volatility-index",
            "current_value": "18" if bullish else "22" if bearish else "20",
            "value_five_sessions_earlier": "20",
            "median_20_session": "20",
        },
        {
            **common,
            "evidence_type": "macro",
            "correlation_id": f"{scenario.dataset_id}-macro",
            "lineage_id": f"{scenario.dataset_id}-macro",
            "state": "risk_on" if bullish else "risk_off" if bearish else "neutral",
            "reason_codes": [],
        },
    ]
    if scenario.trend in {"bullish", "bearish"}:
        records.append(
            {
                **common,
                "evidence_type": "catalyst",
                "correlation_id": f"{scenario.dataset_id}-catalyst",
                "lineage_id": f"{scenario.dataset_id}-catalyst",
                "evidence_id": f"{scenario.dataset_id}-catalyst",
                "symbol": "SPY",
                "source_reference": f"https://example.test/{scenario.dataset_id}",
                "published_at": (as_of - timedelta(minutes=5)).isoformat(),
                "materiality": "material",
                "direction": "positive" if bullish else "negative",
                "category": "synthetic_event",
            }
        )
    return records


def _daily_close(trend: str, index: int) -> Decimal:
    if trend == "bullish":
        return Decimal("100") + Decimal(index) / Decimal("2")
    if trend == "bearish":
        return Decimal("320") - Decimal(index) / Decimal("2")
    if trend == "boundary":
        return Decimal("10")
    return Decimal("200")


def _event(
    *,
    event_id: str,
    data_kind: str,
    observed_at: datetime,
    ingested_at: datetime,
    payload: dict[str, object],
) -> dict[str, object]:
    return {
        "event_id": event_id,
        "data_kind": data_kind,
        "observed_at": observed_at.isoformat(),
        "ingested_at": ingested_at.isoformat(),
        "payload": payload,
    }


def _stream(
    filename: str,
    data_kind: str,
    descriptors: dict[str, tuple[str, int]],
) -> dict[str, object]:
    return {
        "filename": filename,
        "data_kind": data_kind,
        "sha256": descriptors[filename][0],
        "event_count": descriptors[filename][1],
    }


def _sectors() -> tuple[tuple[str, str], ...]:
    return (
        ("XLB", "materials"),
        ("XLC", "communication_services"),
        ("XLE", "energy"),
        ("XLF", "financials"),
        ("XLI", "industrials"),
        ("XLK", "technology"),
        ("XLP", "consumer_staples"),
        ("XLRE", "real_estate"),
        ("XLU", "utilities"),
        ("XLV", "health_care"),
        ("XLY", "consumer_discretionary"),
    )


def _json_line(value: object) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":")) + "\n"


def _write_manifest(path: Path, manifest: object) -> None:
    (path / "manifest.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


if __name__ == "__main__":
    main()
