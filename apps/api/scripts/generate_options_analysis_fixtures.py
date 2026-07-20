from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path

from market_trader.options_analysis.configuration import load_options_analysis_policy
from market_trader.options_analysis.serialization import stable_digest

API_ROOT = Path(__file__).resolve().parents[1]
OUTPUT = API_ROOT / "fixtures" / "options_analysis"
POLICY_PATH = API_ROOT / "config" / "options_analysis" / "options-analysis-policy-v1.json"


@dataclass(frozen=True)
class Scenario:
    dataset_id: str
    direction: str
    strategy: str
    records: tuple[dict[str, object], ...]
    reason_summary: dict[str, int]


def main() -> None:
    policy = load_options_analysis_policy(POLICY_PATH)
    for scenario in _scenarios():
        _write_scenario(scenario, policy.version, policy.content_hash)


def _scenarios() -> tuple[Scenario, ...]:
    return (
        Scenario(
            dataset_id="bull-call-qualified",
            direction="bullish",
            strategy="bull_call",
            records=(
                _candidate("bull-call-qualified", "AAPL", "bullish"),
                _contract("AAPL-20260918-C-200", "call", "200", "accepted", ()),
                _contract("AAPL-20260918-C-205", "call", "205", "accepted", ()),
                _spread("bull_call", "AAPL-20260918-C-200", "AAPL-20260918-C-205"),
            ),
            reason_summary={},
        ),
        Scenario(
            dataset_id="bear-put-qualified",
            direction="bearish",
            strategy="bear_put",
            records=(
                _candidate("bear-put-qualified", "MSFT", "bearish"),
                _contract("MSFT-20260918-P-320", "put", "320", "accepted", ()),
                _contract("MSFT-20260918-P-315", "put", "315", "accepted", ()),
                _spread("bear_put", "MSFT-20260918-P-320", "MSFT-20260918-P-315"),
            ),
            reason_summary={},
        ),
        Scenario(
            dataset_id="contract-boundaries",
            direction="bullish",
            strategy="bull_call",
            records=(
                _candidate("contract-boundaries", "NVDA", "bullish"),
                _contract("NVDA-20260813-C-120", "call", "120", "rejected", ("dte_out_of_range",)),
                _contract("NVDA-20260814-C-120", "call", "120", "accepted", ()),
                _contract("NVDA-20261013-C-125", "call", "125", "accepted", ()),
                _contract("NVDA-20261014-C-125", "call", "125", "rejected", ("dte_out_of_range",)),
                _contract(
                    "NVDA-20260918-C-130",
                    "call",
                    "130",
                    "rejected",
                    ("delta_out_of_range",),
                ),
                _contract(
                    "NVDA-20260918-C-135",
                    "call",
                    "135",
                    "rejected",
                    ("liquidity_insufficient",),
                ),
            ),
            reason_summary={
                "delta_out_of_range": 1,
                "dte_out_of_range": 2,
                "liquidity_insufficient": 1,
            },
        ),
        Scenario(
            dataset_id="risk-warnings",
            direction="bullish",
            strategy="bull_call",
            records=(
                _candidate("risk-warnings", "TSLA", "bullish"),
                _contract("TSLA-20260918-C-250", "call", "250", "accepted", ()),
                _contract("TSLA-20260918-C-255", "call", "255", "accepted", ()),
                _spread(
                    "bull_call",
                    "TSLA-20260918-C-250",
                    "TSLA-20260918-C-255",
                    blocked=True,
                    warnings=(
                        _warning("earnings_risk", "block"),
                        _warning("ex_dividend_risk", "warning"),
                        _warning("pin_risk", "block"),
                    ),
                ),
            ),
            reason_summary={"earnings_risk": 1, "ex_dividend_risk": 1, "pin_risk": 1},
        ),
    )


def _write_scenario(scenario: Scenario, policy_version: str, policy_hash: str) -> None:
    path = OUTPUT / scenario.dataset_id
    path.mkdir(parents=True, exist_ok=True)
    records = tuple(
        {
            **record,
            "dataset_id": scenario.dataset_id,
            "as_of": "2026-08-14T14:30:00+00:00",
            "policy_version": policy_version,
        }
        for record in scenario.records
    )
    content = json.dumps(records, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    stream = path / "records.json"
    stream.write_text(content, encoding="utf-8")
    manifest = {
        "options_analysis_fixture_schema_version": 1,
        "dataset_id": scenario.dataset_id,
        "as_of": "2026-08-14T14:30:00+00:00",
        "policy_version": policy_version,
        "policy_hash": policy_hash,
        "streams": [
            {
                "filename": "records.json",
                "sha256": hashlib.sha256(content.encode("utf-8")).hexdigest(),
            }
        ],
        "expected_counts": {
            "records": len(records),
            "contracts": sum(1 for item in records if item["record_type"] == "contract"),
            "spreads": sum(1 for item in records if item["record_type"] == "spread"),
            "warnings": _warning_count(records),
        },
        "expected_reason_summary": scenario.reason_summary,
        "expected_result_digest": stable_digest(records),
    }
    (path / "manifest.json").write_text(
        json.dumps(manifest, sort_keys=True, separators=(",", ":"), ensure_ascii=True),
        encoding="utf-8",
    )


def _candidate(dataset_id: str, symbol: str, direction: str) -> dict[str, object]:
    return {
        "record_type": "candidate",
        "candidate_key": f"{dataset_id}:candidate:{symbol}",
        "scanner_run_key": f"{dataset_id}:scanner",
        "symbol": symbol,
        "direction": direction,
        "status": "qualified",
    }


def _contract(
    contract_id: str,
    option_type: str,
    strike: str,
    state: str,
    reasons: tuple[str, ...],
) -> dict[str, object]:
    return {
        "record_type": "contract",
        "contract_id": contract_id,
        "option_type": option_type,
        "expiration": contract_id.split("-")[1],
        "strike": strike,
        "state": state,
        "reasons": list(reasons),
        "bid": "1.20",
        "ask": "1.30",
        "delta": "0.45",
        "open_interest": 100,
        "volume": 50,
    }


def _spread(
    strategy: str,
    long_contract_id: str,
    short_contract_id: str,
    *,
    blocked: bool = False,
    warnings: tuple[dict[str, str], ...] = (),
) -> dict[str, object]:
    return {
        "record_type": "spread",
        "strategy": strategy,
        "long_contract_id": long_contract_id,
        "short_contract_id": short_contract_id,
        "expiration": long_contract_id.split("-")[1],
        "debit": "1.25",
        "maximum_loss": "125.00",
        "maximum_gain": "375.00",
        "break_even": "201.25",
        "net_delta": "0.20",
        "blocked": blocked,
        "warnings": list(warnings),
    }


def _warning(code: str, severity: str) -> dict[str, str]:
    return {"code": code, "severity": severity}


def _warning_count(records: tuple[dict[str, object], ...]) -> int:
    count = 0
    for item in records:
        if item["record_type"] != "spread":
            continue
        warnings = item.get("warnings", [])
        if not isinstance(warnings, list):
            raise TypeError("spread fixture warnings must be a list")
        count += len(warnings)
    return count


if __name__ == "__main__":
    main()
