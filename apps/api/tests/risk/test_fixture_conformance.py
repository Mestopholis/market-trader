from pathlib import Path

from market_trader.risk.replay import replay_risk_fixture


def test_checked_in_risk_fixtures_cover_required_groups() -> None:
    root = Path("fixtures/risk")
    groups = {path.parent.name for path in root.glob("*/*.json")}

    assert {
        "share-sizing-boundaries",
        "spread-sizing-boundaries",
        "portfolio-limits-and-locks",
        "settlement-and-tax-warnings",
    } <= groups


def test_checked_in_risk_fixtures_replay_to_expected_status() -> None:
    for path in sorted(Path("fixtures/risk").glob("*/*.json")):
        result = replay_risk_fixture(path)
        assert result.decision.status == result.fixture.expected_status
