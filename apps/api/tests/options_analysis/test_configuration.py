import json
from pathlib import Path

import pytest

from market_trader.options_analysis.configuration import (
    OptionsAnalysisConfigurationError,
    load_options_analysis_policy,
)


def test_loads_the_checked_in_policy_with_defined_risk_boundaries() -> None:
    policy = load_options_analysis_policy(_policy_path())

    assert policy.version == "options-analysis-policy-v1"
    assert (policy.dte_min, policy.dte_max) == (30, 60)
    assert policy.contract_multiplier == 100
    assert policy.require_standard_deliverable is True
    assert policy.pin_block_distance < policy.pin_warning_distance


def test_rejects_an_unknown_policy_key(tmp_path: Path) -> None:
    policy = json.loads(_policy_path().read_text(encoding="utf-8"))
    policy["unexpected"] = True
    path = tmp_path / "policy.json"
    path.write_text(json.dumps(policy), encoding="utf-8")

    with pytest.raises(OptionsAnalysisConfigurationError, match="unknown policy keys"):
        load_options_analysis_policy(path)


def test_rejects_a_changed_policy_hash(tmp_path: Path) -> None:
    path = tmp_path / "policy.json"
    path.write_text(_policy_path().read_text(encoding="utf-8"), encoding="utf-8")
    path.write_text(
        path.read_text(encoding="utf-8").replace('"dte_min": "30"', '"dte_min": "31"'),
        encoding="utf-8",
    )

    with pytest.raises(OptionsAnalysisConfigurationError, match="content hash"):
        load_options_analysis_policy(path)


def _policy_path() -> Path:
    return (
        Path(__file__).parents[2]
        / "config"
        / "options_analysis"
        / "options-analysis-policy-v1.json"
    )
