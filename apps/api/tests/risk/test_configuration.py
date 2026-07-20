import hashlib
import json
from collections.abc import MutableMapping
from decimal import Decimal
from pathlib import Path

import pytest

from market_trader.risk.configuration import (
    RiskConfigurationError,
    RiskPolicy,
    load_risk_policy,
)


def test_loads_checked_in_risk_policy() -> None:
    policy = load_risk_policy(Path("config/risk/risk-policy-v1.json"))

    assert isinstance(policy, RiskPolicy)
    assert policy.version == "risk-policy-v1"
    assert policy.per_trade_risk_fraction == Decimal("0.01")
    assert policy.contract_multiplier == Decimal("100")
    assert "daily_loss" in policy.required_lock_types
    assert policy.tax_disclaimer.startswith("Educational warning")


def test_policy_rejects_unknown_and_missing_keys(tmp_path: Path) -> None:
    raw = _base_policy()
    raw["unknown"] = True
    path = _write_policy(tmp_path, raw)

    with pytest.raises(RiskConfigurationError, match="unknown policy keys"):
        load_risk_policy(path)

    raw = _base_policy()
    raw.pop("max_positions")
    path = _write_policy(tmp_path, raw)

    with pytest.raises(RiskConfigurationError, match="missing policy keys"):
        load_risk_policy(path)


def test_policy_requires_decimal_strings_and_content_hash_match(tmp_path: Path) -> None:
    raw = _base_policy()
    raw["per_trade_risk_fraction"] = 0.01
    path = _write_policy(tmp_path, raw)

    with pytest.raises(RiskConfigurationError, match="decimal string"):
        load_risk_policy(path)

    raw = _base_policy()
    raw["content_hash"] = "not-the-real-hash"
    path = tmp_path / "risk-policy.json"
    path.write_text(json.dumps(raw, sort_keys=True), encoding="utf-8")

    with pytest.raises(RiskConfigurationError, match="content hash"):
        load_risk_policy(path)


def test_policy_rejects_unsupported_version_and_non_positive_limits(tmp_path: Path) -> None:
    raw = _base_policy()
    raw["version"] = "risk-policy-v2"
    path = _write_policy(tmp_path, raw)

    with pytest.raises(RiskConfigurationError, match="unsupported policy version"):
        load_risk_policy(path)

    raw = _base_policy()
    raw["per_trade_risk_fraction"] = "0"
    path = _write_policy(tmp_path, raw)

    with pytest.raises(RiskConfigurationError, match="positive"):
        load_risk_policy(path)


def test_policy_rejects_overlapping_trading_windows_and_missing_locks(tmp_path: Path) -> None:
    raw = _base_policy()
    raw["blocked_trading_windows"] = [
        {"label": "open-auction", "start": "09:30", "end": "09:45"},
        {"label": "overlap", "start": "09:40", "end": "10:00"},
    ]
    path = _write_policy(tmp_path, raw)

    with pytest.raises(RiskConfigurationError, match="overlap"):
        load_risk_policy(path)

    raw = _base_policy()
    raw["required_lock_types"] = ["daily_loss"]
    path = _write_policy(tmp_path, raw)

    with pytest.raises(RiskConfigurationError, match="required lock types"):
        load_risk_policy(path)


def test_policy_requires_tax_disclaimer_and_strict_equivalent_symbol_groups(tmp_path: Path) -> None:
    raw = _base_policy()
    raw["tax_disclaimer"] = ""
    path = _write_policy(tmp_path, raw)

    with pytest.raises(RiskConfigurationError, match="tax disclaimer"):
        load_risk_policy(path)

    raw = _base_policy()
    raw["equivalent_symbol_groups"] = [["SPY", ""]]
    path = _write_policy(tmp_path, raw)

    with pytest.raises(RiskConfigurationError, match="equivalent symbol"):
        load_risk_policy(path)


def _base_policy() -> dict[str, object]:
    return {
        "version": "risk-policy-v1",
        "content_hash": "",
        "per_trade_risk_fraction": "0.01",
        "max_share_notional_fraction": "0.20",
        "max_spread_debit_fraction": "0.05",
        "max_total_reserved_risk_fraction": "0.06",
        "min_settled_cash_after_trade": "250.00",
        "contract_multiplier": "100",
        "allow_unsettled_cash": False,
        "block_borrowed_buying_power": True,
        "max_positions": 8,
        "max_open_trades_per_day": 3,
        "max_correlation_group_fraction": "0.30",
        "max_daily_loss_fraction": "0.02",
        "max_weekly_loss_fraction": "0.04",
        "max_drawdown_fraction": "0.08",
        "required_lock_types": ["daily_loss", "weekly_loss", "drawdown", "manual"],
        "informational_lock_types": ["catalyst_warning"],
        "blocked_trading_windows": [
            {"label": "open-auction", "start": "09:30", "end": "09:35"},
            {"label": "closing-auction", "start": "15:55", "end": "16:00"},
        ],
        "wash_sale_window_days": 30,
        "short_term_holding_period_days": 365,
        "long_term_holding_period_days": 366,
        "equivalent_symbol_groups": [["SPY", "VOO", "IVV"], ["QQQ", "QQQM"]],
        "tax_disclaimer": (
            "Educational warning only; not tax advice. Consult a qualified tax professional."
        ),
    }


def _write_policy(tmp_path: Path, raw: MutableMapping[str, object]) -> Path:
    raw["content_hash"] = _content_hash(raw)
    path = tmp_path / "risk-policy.json"
    path.write_text(json.dumps(raw, sort_keys=True), encoding="utf-8")
    return path


def _content_hash(raw: MutableMapping[str, object]) -> str:
    payload = dict(raw)
    payload.pop("content_hash", None)
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()
