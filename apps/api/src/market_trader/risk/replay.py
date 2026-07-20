from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from market_trader.risk.configuration import load_risk_policy
from market_trader.risk.engine import RiskEngine
from market_trader.risk.fixtures import RiskFixture, load_risk_fixture
from market_trader.risk.models import RiskDecision


@dataclass(frozen=True)
class RiskReplayResult:
    fixture: RiskFixture
    decision: RiskDecision


def replay_risk_fixture(path: Path | str) -> RiskReplayResult:
    fixture = load_risk_fixture(path)
    policy = load_risk_policy(fixture.policy_path)
    decision = RiskEngine().evaluate(fixture.risk_input, policy)
    return RiskReplayResult(fixture=fixture, decision=decision)
