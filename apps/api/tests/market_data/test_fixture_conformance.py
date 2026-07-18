from datetime import date
from pathlib import Path

import pytest

from market_trader.market_calendar.adapter import XNYSCalendarAdapter
from market_trader.market_data.fixtures import FixtureDataset, FixtureValidationError
from market_trader.market_data.replay import (
    ReplayEngine,
    ReplayResult,
    VirtualReplayClock,
)
from market_trader.market_data.sinks import InMemoryIngestionSink

API_ROOT = Path(__file__).parents[2]
PRODUCTION_FIXTURES = API_ROOT / "fixtures" / "market_data"
TEST_FIXTURES = Path(__file__).parent / "fixtures"
DATASET_NAMES = (
    "regular-session",
    "quality-boundaries",
    "corporate-actions",
    "provider-recovery",
)
REQUIRED_SCENARIOS = {
    "regular_quote",
    "one_minute_candle",
    "daily_candle",
    "daylight_saving",
    "early_close",
    "complete_option_chain",
    "freshness_equality",
    "freshness_past_boundary",
    "halted_symbol",
    "non_updating_symbol",
    "wide_market",
    "locked_market",
    "crossed_market",
    "incomplete_market",
    "forward_split",
    "reverse_split",
    "stock_dividend",
    "cash_dividend",
    "standard_deliverable",
    "unsupported_deliverable",
    "missing_field",
    "invalid_value",
    "unknown_schema",
    "duplicate_event",
    "out_of_order",
    "future_timestamp",
    "provider_unavailable",
    "provider_throttled",
    "provider_partial",
    "provider_recovery",
}


@pytest.mark.parametrize("dataset_name", DATASET_NAMES)
def test_production_fixture_replays_deterministically(dataset_name: str) -> None:
    dataset = FixtureDataset.load(PRODUCTION_FIXTURES / dataset_name)

    first = replay_in_memory(dataset)
    second = replay_in_memory(dataset)

    assert first == second
    assert first.counts == dataset.manifest.expected_counts
    assert first.result_digest == dataset.manifest.expected_result_digest


def test_production_fixtures_cover_required_scenarios() -> None:
    observed: set[str] = set()
    for dataset_name in DATASET_NAMES:
        dataset = FixtureDataset.load(PRODUCTION_FIXTURES / dataset_name)
        for event in dataset.events:
            scenario = event.payload.get("scenario")
            if isinstance(scenario, str):
                observed.add(scenario)
            elif isinstance(scenario, list):
                observed.update(item for item in scenario if isinstance(item, str))

    assert observed >= REQUIRED_SCENARIOS


def test_static_malformed_json_fixture_fails_without_leaking_payload() -> None:
    with pytest.raises(FixtureValidationError) as error:
        FixtureDataset.load(TEST_FIXTURES / "malformed-json")

    assert "malformed JSON" in str(error.value)
    assert "must-not-leak" not in str(error.value)


def replay_in_memory(dataset: FixtureDataset) -> ReplayResult:
    calendar = XNYSCalendarAdapter(start=date(2025, 1, 1), end=date(2028, 12, 31))
    return ReplayEngine(
        clock=VirtualReplayClock(),
        calendar=calendar,
        sink=InMemoryIngestionSink(),
    ).replay(dataset)
