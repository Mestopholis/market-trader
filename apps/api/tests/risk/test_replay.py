from pathlib import Path

from market_trader.risk.replay import replay_risk_fixture


def test_replay_fixture_is_deterministic() -> None:
    path = Path("fixtures/risk/share-sizing-boundaries/approved-share.json")

    first = replay_risk_fixture(path)
    second = replay_risk_fixture(path)

    assert first.decision.status == first.fixture.expected_status
    assert first.decision.result_digest == second.decision.result_digest
