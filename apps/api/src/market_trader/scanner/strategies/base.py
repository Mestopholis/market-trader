from typing import Protocol

from market_trader.scanner.evidence import SupplementalEvidence
from market_trader.scanner.features import FeatureResult
from market_trader.scanner.models import RegimeResult, StrategyResult


class StrategyEvaluator(Protocol):
    strategy_id: str
    version: str

    def evaluate(
        self,
        features: FeatureResult,
        regime: RegimeResult,
        evidence: SupplementalEvidence,
    ) -> StrategyResult: ...
