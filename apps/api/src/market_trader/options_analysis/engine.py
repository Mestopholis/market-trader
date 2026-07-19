from dataclasses import dataclass
from datetime import datetime

from market_trader.options_analysis.models import ContractEvaluation, SpreadCandidate
from market_trader.options_analysis.warnings import SpreadWarning


@dataclass(frozen=True)
class RankedSpread:
    candidate: SpreadCandidate
    blocked: bool
    warnings: tuple[SpreadWarning, ...] = ()


@dataclass(frozen=True)
class OptionsAnalysisResult:
    selectable: tuple[RankedSpread, ...]
    blocked: tuple[RankedSpread, ...]
    evaluations: tuple[ContractEvaluation, ...] = ()
    run_key: str = ""
    scanner_run_key: str = ""
    candidate_key: str = ""
    symbol: str = ""
    input_digest: str = ""
    result_digest: str = ""
    policy_version: str = ""
    policy_hash: str = ""
    as_of: datetime | None = None


class OptionsAnalysisEngine:
    def rank(
        self,
        candidates: tuple[SpreadCandidate, ...],
        *,
        blocked_contract_ids: frozenset[str],
    ) -> OptionsAnalysisResult:
        ranked = tuple(
            RankedSpread(
                candidate=candidate,
                blocked=(
                    candidate.long_contract_id in blocked_contract_ids
                    or candidate.short_contract_id in blocked_contract_ids
                ),
            )
            for candidate in sorted(
                candidates,
                key=lambda candidate: (
                    candidate.maximum_loss,
                    candidate.expiration,
                    candidate.long_contract_id,
                    candidate.short_contract_id,
                ),
            )
        )
        return OptionsAnalysisResult(
            selectable=tuple(item for item in ranked if not item.blocked),
            blocked=tuple(item for item in ranked if item.blocked),
        )
