from dataclasses import replace
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

from market_trader.market_data.models import (
    AdjustmentState,
    CandleInterval,
    NormalizedCandle,
    NormalizedProviderState,
    ObservationMetadata,
    ProviderOperationalState,
    QualityState,
)
from market_trader.scanner import ScannerEngine
from market_trader.scanner.configuration import (
    ScannerConfiguration,
    UniversePolicy,
    load_scanner_configuration,
)
from market_trader.scanner.evidence import (
    BreadthEvidence,
    EvidenceMetadata,
    MacroEvidence,
    MacroState,
    SectorEvidence,
    SectorObservation,
    SupplementalEvidence,
    VolatilityDirection,
    VolatilityEvidence,
)
from market_trader.scanner.models import (
    EligibilityStatus,
    EvidenceRef,
    PolicyVersions,
    ScannerInput,
    StrategyStatus,
    SymbolInput,
)

CONFIGURATION_PATH = Path(__file__).parents[2] / "config" / "scanner"
BASE_CONFIGURATION = load_scanner_configuration(CONFIGURATION_PATH)
AS_OF = datetime(2026, 7, 17, 15, 35, tzinfo=UTC)
SESSION_DATE = date(2026, 7, 17)
MARKET_OPEN = datetime(2026, 7, 17, 13, 30, tzinfo=UTC)


def _configuration() -> ScannerConfiguration:
    symbols = {"SPY", "AAPL"}
    entries = tuple(
        entry for entry in BASE_CONFIGURATION.universe.entries if entry.display_symbol in symbols
    )
    return replace(
        BASE_CONFIGURATION,
        universe=UniversePolicy(
            version=BASE_CONFIGURATION.universe.version,
            entries=entries,
        ),
    )


def _metadata(event_id: str, session_date: date) -> ObservationMetadata:
    return ObservationMetadata(
        source="fixture",
        event_id=event_id,
        observed_at=AS_OF - timedelta(minutes=1),
        ingested_at=AS_OF - timedelta(seconds=30),
        session_date=session_date,
        normalized_schema_version=1,
        configuration_version="market-data-v1",
        correlation_id="engine-test",
        quality_state=QualityState.VALID,
        quality_reasons=(),
    )


def _daily(symbol: str, index: int) -> NormalizedCandle:
    session_date = date(2025, 9, 1) + timedelta(days=index)
    price = Decimal(index + 1)
    start = datetime.combine(session_date, datetime.min.time(), tzinfo=UTC)
    return NormalizedCandle(
        symbol=symbol,
        interval=CandleInterval.DAILY,
        start=start,
        end=start + timedelta(hours=23),
        open=price,
        high=price + 1,
        low=price - 1,
        close=price,
        volume=200_000,
        vwap=price,
        trade_count=100,
        adjustment=AdjustmentState.ADJUSTED,
        metadata=_metadata(f"{symbol}-daily-{index}", session_date),
    )


def _minute(
    symbol: str,
    index: int,
    *,
    session_date: date = SESSION_DATE,
    volume: int = 100,
) -> NormalizedCandle:
    eastern = ZoneInfo("America/New_York")
    local_open = datetime.combine(
        session_date,
        datetime.min.time().replace(hour=9, minute=30),
        tzinfo=eastern,
    )
    start = local_open.astimezone(UTC) + timedelta(minutes=index)
    price = Decimal("230") + Decimal(index)
    return NormalizedCandle(
        symbol=symbol,
        interval=CandleInterval.ONE_MINUTE,
        start=start,
        end=start + timedelta(minutes=1),
        open=price,
        high=price + 1,
        low=price - 1,
        close=price + Decimal("0.5"),
        volume=volume,
        vwap=price,
        trade_count=10,
        adjustment=AdjustmentState.ADJUSTED,
        metadata=_metadata(f"{symbol}-{session_date}-{index}", session_date),
    )


def _provider_state(symbol: str) -> NormalizedProviderState:
    return NormalizedProviderState(
        provider="fixture",
        state=ProviderOperationalState.AVAILABLE,
        metadata=_metadata(f"{symbol}-provider", SESSION_DATE),
    )


def _reference(symbol: str) -> EvidenceRef:
    return EvidenceRef(
        lineage_id=f"{symbol}-market-lineage",
        source="fixture",
        event_id=f"{symbol}-market-event",
        ingestion_key=f"{symbol}-ingestion-key",
        payload_digest="a" * 64,
        observed_at=AS_OF - timedelta(minutes=1),
        ingested_at=AS_OF - timedelta(seconds=30),
    )


def _symbol(symbol: str, *, active: bool = True) -> SymbolInput:
    historical_dates = tuple(date(2026, 6, 15) + timedelta(days=index) for index in range(20))
    historical = tuple(
        candle
        for historical_date in historical_dates
        for candle in (
            _minute(symbol, index, session_date=historical_date, volume=50) for index in range(10)
        )
    )
    return SymbolInput(
        symbol=symbol,
        daily_candles=tuple(_daily(symbol, index) for index in range(220)),
        intraday_candles=(
            *historical,
            *(_minute(symbol, index) for index in range(10)),
        ),
        provider_states=(_provider_state(symbol),),
        evidence=(_reference(symbol),),
        attributes={
            "symbol_active": active,
            "halted": False,
            "quote_updating": True,
            "adjustment_supported": True,
            "corporate_actions_resolved": True,
        },
    )


def _supplemental() -> SupplementalEvidence:
    sectors = (
        "materials",
        "communication_services",
        "energy",
        "financials",
        "industrials",
        "information_technology",
        "consumer_staples",
        "real_estate",
        "utilities",
        "health_care",
        "consumer_discretionary",
    )
    return SupplementalEvidence(
        as_of=AS_OF,
        breadth=(
            BreadthEvidence(
                **_evidence_metadata("breadth-lineage").__dict__,
                source_universe="synthetic",
                session_date=date(2026, 7, 16),
                total_eligible_issues=100,
                advancing_issues=60,
                declining_issues=40,
                unchanged_issues=0,
                issues_above_sma_50=60,
                up_volume=Decimal("150"),
                down_volume=Decimal("100"),
            ),
        ),
        sector=(
            SectorEvidence(
                **_evidence_metadata("sector-lineage").__dict__,
                session_date=date(2026, 7, 16),
                observations=tuple(
                    SectorObservation(
                        symbol=f"SECTOR-{index}",
                        sector=sector,
                        close_relative_to_sma_50=Decimal("1.1"),
                        return_20_session=Decimal("0.01"),
                    )
                    for index, sector in enumerate(sectors)
                ),
            ),
        ),
        volatility=(
            VolatilityEvidence(
                **_evidence_metadata("volatility-lineage").__dict__,
                measure="VIX",
                current_value=Decimal("19"),
                value_five_sessions_earlier=Decimal("20"),
                median_20_session=Decimal("20"),
                direction=VolatilityDirection.FALLING,
            ),
        ),
        macro=(
            MacroEvidence(
                **_evidence_metadata("macro-lineage").__dict__,
                state=MacroState.RISK_ON,
                reason_codes=(),
            ),
        ),
        catalysts=(),
    )


def _evidence_metadata(lineage_id: str) -> EvidenceMetadata:
    return EvidenceMetadata(
        schema_version="scanner-evidence-v1",
        configuration_version="fixture-v1",
        correlation_id="engine-test",
        lineage_id=lineage_id,
        source="fixture",
        observed_at=AS_OF - timedelta(minutes=1),
        valid_until=AS_OF,
    )


def _scanner_input(*symbols: SymbolInput) -> ScannerInput:
    configuration = _configuration()
    return ScannerInput(
        as_of=AS_OF,
        session_date=SESSION_DATE,
        versions=configuration.versions,
        symbols=symbols or (_symbol("SPY", active=False), _symbol("AAPL")),
        supplemental_evidence=_supplemental(),
        configuration_hashes=configuration.content_hashes,
    )


def test_emits_one_eligibility_per_member_and_five_signals_per_eligible_symbol() -> None:
    result = ScannerEngine(_configuration()).scan(_scanner_input())

    assert [(item.symbol, item.status) for item in result.eligibility] == [
        ("AAPL", EligibilityStatus.ELIGIBLE),
        ("SPY", EligibilityStatus.INELIGIBLE),
    ]
    assert len(result.strategies) == 5
    assert {item.symbol for item in result.strategies} == {"AAPL"}
    assert {item.strategy_id for item in result.strategies} == {
        "bullish_breakout",
        "bullish_pullback",
        "bearish_breakdown",
        "bearish_failed_rally",
        "news_continuation",
    }
    assert result.counts.eligible == 1
    assert result.counts.ineligible == 1
    assert result.counts.blocked == 0
    assert result.counts.signals == 5


def test_candidates_trace_only_to_passing_signals_and_versioned_stable_keys() -> None:
    configuration = _configuration()
    result = ScannerEngine(configuration).scan(_scanner_input())
    strategies = {item.signal_key: item for item in result.strategies}

    assert result.run_key
    assert configuration.versions.universe in result.run_key
    assert configuration.versions.scoring in result.run_key
    assert result.input_digest
    assert result.result_digest
    assert dict(result.configuration_hashes) == dict(configuration.content_hashes)
    assert result.candidates
    for candidate in result.candidates:
        signal = strategies[candidate.signal_key]
        assert signal.status is StrategyStatus.PASSED
        assert all(gate.passed is True for gate in signal.gates if gate.required)
        assert (
            signal.score is not None and signal.score >= configuration.scoring.candidate_threshold
        )
        assert configuration.versions.strategies in signal.signal_key
        assert configuration.versions.scoring in candidate.candidate_key
        assert signal.primary_ingestion_key == "AAPL-ingestion-key"
        assert signal.input_references == (_reference("AAPL"),)


def test_input_order_and_future_market_observations_do_not_change_output() -> None:
    configuration = _configuration()
    base = _scanner_input()
    aapl = next(symbol for symbol in base.symbols if symbol.symbol == "AAPL")
    future_metadata = replace(
        _metadata("future", SESSION_DATE),
        observed_at=AS_OF + timedelta(minutes=1),
        ingested_at=AS_OF + timedelta(minutes=2),
    )
    future = replace(
        _minute("AAPL", 10),
        start=AS_OF + timedelta(minutes=1),
        end=AS_OF + timedelta(minutes=2),
        metadata=future_metadata,
    )
    with_future = replace(aapl, intraday_candles=(*aapl.intraday_candles, future))
    changed = replace(
        base,
        symbols=tuple(
            reversed(
                tuple(with_future if symbol.symbol == "AAPL" else symbol for symbol in base.symbols)
            )
        ),
    )

    first = ScannerEngine(configuration).scan(base)
    second = ScannerEngine(configuration).scan(changed)

    assert second == first


def test_exact_input_reproduces_entire_result() -> None:
    engine = ScannerEngine(_configuration())
    scanner_input = _scanner_input()

    assert engine.scan(scanner_input) == engine.scan(scanner_input)


def test_missing_member_input_is_blocked_and_has_no_signals() -> None:
    result = ScannerEngine(_configuration()).scan(_scanner_input(_symbol("SPY", active=False)))

    aapl = next(item for item in result.eligibility if item.symbol == "AAPL")
    assert aapl.status is EligibilityStatus.BLOCKED
    assert {item.symbol for item in result.strategies} == set()


def test_configuration_version_or_hash_mismatch_is_rejected() -> None:
    engine = ScannerEngine(_configuration())
    scanner_input = _scanner_input()

    with pytest.raises(ValueError, match="versions"):
        engine.scan(
            replace(
                scanner_input,
                versions=replace(PolicyVersions(), scoring="candidate-scoring-v2"),
            )
        )
    with pytest.raises(ValueError, match="hashes"):
        engine.scan(replace(scanner_input, configuration_hashes={}))
