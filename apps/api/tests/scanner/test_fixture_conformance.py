import json
from pathlib import Path

import pytest

from market_trader.scanner.cli import main
from market_trader.scanner.fixtures import ScannerFixtureDataset

API_ROOT = Path(__file__).parents[2]
FIXTURES = API_ROOT / "fixtures" / "scanner"
SCENARIOS = (
    "bullish",
    "bearish",
    "neutral-mixed-blocked",
    "boundaries-and-conflicts",
)


@pytest.mark.parametrize("scenario", SCENARIOS)
def test_production_fixture_replays_twice_with_frozen_expected_result(
    scenario: str, capsys: pytest.CaptureFixture[str]
) -> None:
    path = FIXTURES / scenario
    dataset = ScannerFixtureDataset.load(path)

    first_code = main(["validate", str(path)])
    first = capsys.readouterr()
    second_code = main(["validate", str(path)])
    second = capsys.readouterr()
    payload = json.loads(first.out)

    assert first_code == second_code == 0
    assert first.err == second.err == ""
    assert first.out == second.out
    assert payload["dataset_id"] == dataset.manifest.dataset_id == scenario
    assert payload["result_digest"] == dataset.manifest.expected.result_digest
    assert payload["regime"]["state"] == dataset.manifest.expected.regime_state


def test_fixture_matrix_declares_every_approved_scenario_family() -> None:
    descriptions = " ".join(
        ScannerFixtureDataset.load(FIXTURES / scenario).manifest.description
        for scenario in SCENARIOS
    ).casefold()

    for phrase in (
        "bullish breakout",
        "bullish pullback",
        "bearish breakdown",
        "bearish failed rally",
        "positive news",
        "negative news",
        "neutral",
        "mixed",
        "blocked",
        "threshold boundary",
        "stale",
        "missing",
        "conflicting",
        "halted",
        "corporate action",
        "deduplication",
        "family cap",
        "idempotence",
        "changed-input conflict",
        "normal session",
        "early close",
        "daylight-saving",
    ):
        assert phrase in descriptions
