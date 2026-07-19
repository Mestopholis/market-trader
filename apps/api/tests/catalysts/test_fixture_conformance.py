import subprocess
import sys
from dataclasses import replace
from datetime import timedelta
from pathlib import Path

import pytest

from market_trader.catalysts.configuration import load_catalyst_configuration
from market_trader.catalysts.fixtures import CatalystFixtureDataset
from market_trader.catalysts.replay import (
    CatalystReplayEngine,
    CatalystReplayResult,
    InMemoryCatalystReplaySink,
    VirtualCatalystClock,
)
from market_trader.catalysts.risk import display_risk_bounds
from market_trader.market_calendar.adapter import XNYSCalendarAdapter

API_ROOT = Path(__file__).parents[2]
FIXTURE_ROOT = API_ROOT / "fixtures" / "catalysts"
CONFIGURATION_ROOT = API_ROOT / "config" / "catalysts"
GROUPS = (
    "company-and-earnings",
    "macro-risk-windows",
    "sec-and-amendments",
    "social-summary-and-failures",
)
REQUIRED_SCENARIOS = {
    "calendar:dst",
    "calendar:early-close",
    "earnings:after-market",
    "earnings:before-market",
    "earnings:negative-threshold",
    "earnings:positive-threshold",
    "earnings:unknown-time",
    "identity:changed-input",
    "identity:conflict",
    "identity:duplicate",
    "identity:exact-rerun",
    "macro:cpi",
    "macro:employment",
    "macro:fomc",
    "render:chicago",
    "risk:after-boundary",
    "risk:before-boundary",
    "risk:end-boundary",
    "risk:start-boundary",
    "sec:10-k",
    "sec:10-q",
    "sec:8-k",
    "sec:amendment",
    "social:only-unconfirmed",
    "source:failure",
    "source:recovery",
    "summary:cited",
    "summary:injection-text",
}


def test_fixture_inventory_covers_required_scenarios() -> None:
    assert tuple(sorted(path.name for path in FIXTURE_ROOT.iterdir())) == GROUPS
    scenarios = {
        scenario
        for group in GROUPS
        for scenario in CatalystFixtureDataset.load(FIXTURE_ROOT / group).manifest.scenarios
    }

    assert scenarios >= REQUIRED_SCENARIOS


@pytest.mark.parametrize("group", GROUPS)
def test_fixture_replay_is_stable_and_matches_frozen_digests(group: str) -> None:
    dataset = CatalystFixtureDataset.load(FIXTURE_ROOT / group)

    first = _replay(dataset)
    second = _replay(dataset)

    assert first == second
    assert first.result_digest == dataset.manifest.expected_result_digest
    assert first.reason_digest == dataset.manifest.expected_reason_digest


def test_generator_is_byte_stable() -> None:
    before = _fixture_bytes()

    completed = subprocess.run(
        [sys.executable, "scripts/generate_catalyst_fixtures.py"],
        cwd=API_ROOT,
        check=False,
        capture_output=True,
        text=True,
    )

    assert completed.returncode == 0, completed.stderr
    assert completed.stdout == ""
    assert _fixture_bytes() == before


def test_macro_fixture_renders_chicago_time_without_changing_identity() -> None:
    result = _replay(CatalystFixtureDataset.load(FIXTURE_ROOT / "macro-risk-windows"))
    window = next(item for item in result.risk_windows if item.starts_at is not None)
    original = replace(window)

    starts_at, ends_at = display_risk_bounds(window, "America/Chicago")

    assert starts_at is not None and starts_at.tzinfo is not None
    assert ends_at is not None and ends_at.tzinfo is not None
    assert str(starts_at.tzinfo) == str(ends_at.tzinfo) == "America/Chicago"
    assert window == original


def _replay(dataset: CatalystFixtureDataset) -> CatalystReplayResult:
    as_of = dataset.manifest.as_of
    return CatalystReplayEngine(
        clock=VirtualCatalystClock(),
        calendar=XNYSCalendarAdapter(
            start=as_of.date() - timedelta(days=370),
            end=as_of.date() + timedelta(days=370),
        ),
        configuration=load_catalyst_configuration(CONFIGURATION_ROOT),
        sink=InMemoryCatalystReplaySink(),
    ).replay(dataset)


def _fixture_bytes() -> dict[str, bytes]:
    return {
        str(path.relative_to(FIXTURE_ROOT)): path.read_bytes()
        for path in sorted(FIXTURE_ROOT.rglob("*"))
        if path.is_file()
    }
