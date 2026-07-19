from __future__ import annotations

import hashlib
import json
import shutil
from collections.abc import Callable
from dataclasses import FrozenInstanceError
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest

from market_trader.scanner.configuration import (
    ConfigurationError,
    load_scanner_configuration,
)
from market_trader.scanner.models import PolicyVersions

CONFIGURATION_PATH = Path(__file__).parents[2] / "config" / "scanner"
CONFIGURATION_FILES = (
    "eligible-universe-v1.json",
    "eligibility-policy-v1.json",
    "market-regime-v1.json",
    "scanner-strategies-v1.json",
    "candidate-scoring-v1.json",
)

EXPECTED_SYMBOLS = (
    "SPY",
    "QQQ",
    "IWM",
    "DIA",
    "XLB",
    "XLC",
    "XLE",
    "XLF",
    "XLI",
    "XLK",
    "XLP",
    "XLRE",
    "XLU",
    "XLV",
    "XLY",
    "AAPL",
    "MSFT",
    "NVDA",
    "AMZN",
    "META",
    "GOOGL",
    "TSLA",
    "AMD",
    "AVGO",
    "JPM",
    "XOM",
    "UNH",
    "LLY",
    "WMT",
    "COST",
)


def test_loads_exact_versioned_scanner_configuration() -> None:
    configuration = load_scanner_configuration(CONFIGURATION_PATH)

    assert configuration.versions == PolicyVersions()
    assert tuple(entry.display_symbol for entry in configuration.universe.entries) == (
        EXPECTED_SYMBOLS
    )
    assert tuple(entry.role for entry in configuration.universe.entries) == (
        *("broad_benchmark" for _ in range(4)),
        *("sector_benchmark" for _ in range(11)),
        *("candidate" for _ in range(15)),
    )
    assert tuple(entry.security_type for entry in configuration.universe.entries) == (
        *("unleveraged_etf" for _ in range(15)),
        *("common_stock" for _ in range(15)),
    )
    assert all(entry.candidate_enabled for entry in configuration.universe.entries)

    assert configuration.eligibility.minimum_adjusted_close == Decimal("10.00")
    assert configuration.eligibility.maximum_adjusted_close == Decimal("1000.00")
    assert configuration.eligibility.minimum_completed_daily_sessions == 200
    assert configuration.eligibility.dollar_volume_window_sessions == 20
    assert configuration.eligibility.minimum_median_dollar_volume == Decimal(
        "25000000.00"
    )
    assert configuration.eligibility.price_bounds_inclusive is True
    assert configuration.eligibility.dollar_volume_minimum_inclusive is True

    assert sum(configuration.regime.component_weights.values(), Decimal()) == Decimal(
        "100"
    )
    assert configuration.regime.bullish_total_minimum == Decimal("35")
    assert configuration.regime.bearish_total_maximum == Decimal("-35")

    assert tuple(rule.strategy_id for rule in configuration.strategies.rules) == (
        "bullish_breakout",
        "bullish_pullback",
        "bearish_breakdown",
        "bearish_failed_rally",
        "news_continuation",
    )
    assert configuration.strategies.relative_volume_minimum == Decimal("1.50")

    assert sum(configuration.scoring.family_caps.values(), Decimal()) == Decimal("100")
    assert configuration.scoring.candidate_threshold == Decimal("70.000000")
    assert configuration.scoring.score_quantum == Decimal("0.000001")
    assert set(configuration.content_hashes) == {
        "universe",
        "eligibility",
        "regime",
        "strategies",
        "scoring",
    }
    assert all(len(value) == 64 for value in configuration.content_hashes.values())


def test_configuration_values_are_immutable() -> None:
    configuration = load_scanner_configuration(CONFIGURATION_PATH)

    with pytest.raises(FrozenInstanceError):
        cast_configuration: Any = configuration
        cast_configuration.scoring = configuration.scoring
    with pytest.raises(TypeError):
        weights: Any = configuration.regime.component_weights
        weights["broad_trend"] = Decimal("1")
    with pytest.raises(TypeError):
        hashes: Any = configuration.content_hashes
        hashes["universe"] = "tampered"


@pytest.mark.parametrize("filename", CONFIGURATION_FILES)
def test_rejects_wrong_content_hash(tmp_path: Path, filename: str) -> None:
    copied = _copy_configuration(tmp_path)
    path = copied / filename
    payload = _read_object(path)
    payload["content_hash"] = "0" * 64
    path.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(ConfigurationError, match="content_hash"):
        load_scanner_configuration(copied)


def test_rejects_wrong_policy_version_even_with_matching_hash(tmp_path: Path) -> None:
    copied = _copy_configuration(tmp_path)
    _mutate_and_rehash(
        copied / "market-regime-v1.json",
        lambda payload: payload.__setitem__("version", "market-regime-v2"),
    )

    with pytest.raises(ConfigurationError, match="market-regime-v1"):
        load_scanner_configuration(copied)


def test_rejects_unknown_fields_even_with_matching_hash(tmp_path: Path) -> None:
    copied = _copy_configuration(tmp_path)
    _mutate_and_rehash(
        copied / "eligibility-policy-v1.json",
        lambda payload: payload.__setitem__("minimum_market_cap", "1000000000"),
    )

    with pytest.raises(ConfigurationError, match="unknown field"):
        load_scanner_configuration(copied)


def test_rejects_duplicate_symbols_even_with_matching_hash(tmp_path: Path) -> None:
    copied = _copy_configuration(tmp_path)

    def duplicate_symbol(payload: dict[str, Any]) -> None:
        entries = payload["entries"]
        assert isinstance(entries, list)
        entries.append(entries[0])

    _mutate_and_rehash(copied / "eligible-universe-v1.json", duplicate_symbol)

    with pytest.raises(ConfigurationError, match="duplicate symbol"):
        load_scanner_configuration(copied)


def test_rejects_duplicate_json_object_keys(tmp_path: Path) -> None:
    copied = _copy_configuration(tmp_path)
    path = copied / "eligibility-policy-v1.json"
    text = path.read_text(encoding="utf-8")
    path.write_text(text.replace('"version":', '"version":"duplicate","version":', 1))

    with pytest.raises(ConfigurationError, match="duplicate JSON key"):
        load_scanner_configuration(copied)


@pytest.mark.parametrize(
    ("filename", "field"),
    (
        ("eligibility-policy-v1.json", "minimum_adjusted_close"),
        ("market-regime-v1.json", "bullish_total_minimum"),
        ("scanner-strategies-v1.json", "relative_volume_minimum"),
        ("candidate-scoring-v1.json", "candidate_threshold"),
    ),
)
def test_rejects_numeric_json_decimals(
    tmp_path: Path, filename: str, field: str
) -> None:
    copied = _copy_configuration(tmp_path)

    def replace_decimal(payload: dict[str, Any]) -> None:
        payload[field] = 1.5

    _mutate_and_rehash(copied / filename, replace_decimal)

    with pytest.raises(ConfigurationError, match="decimal string"):
        load_scanner_configuration(copied)


def test_rejects_invalid_regime_weight_total(tmp_path: Path) -> None:
    copied = _copy_configuration(tmp_path)

    def change_weight(payload: dict[str, Any]) -> None:
        weights = payload["component_weights"]
        assert isinstance(weights, dict)
        weights["macro_overlay"] = "9"

    _mutate_and_rehash(copied / "market-regime-v1.json", change_weight)

    with pytest.raises(ConfigurationError, match="regime component weights must total 100"):
        load_scanner_configuration(copied)


def test_rejects_invalid_scoring_cap_total(tmp_path: Path) -> None:
    copied = _copy_configuration(tmp_path)

    def change_cap(payload: dict[str, Any]) -> None:
        caps = payload["family_caps"]
        assert isinstance(caps, dict)
        caps["catalyst"] = "9"

    _mutate_and_rehash(copied / "candidate-scoring-v1.json", change_cap)

    with pytest.raises(ConfigurationError, match="scoring family caps must total 100"):
        load_scanner_configuration(copied)


def test_rejects_changed_scoring_cap_allocation_with_same_total(tmp_path: Path) -> None:
    copied = _copy_configuration(tmp_path)

    def change_caps(payload: dict[str, Any]) -> None:
        caps = payload["family_caps"]
        assert isinstance(caps, dict)
        caps["relative_performance"] = "16"
        caps["catalyst"] = "9"

    _mutate_and_rehash(copied / "candidate-scoring-v1.json", change_caps)

    with pytest.raises(ConfigurationError, match="do not match version one"):
        load_scanner_configuration(copied)


def _copy_configuration(tmp_path: Path) -> Path:
    target = tmp_path / "scanner"
    shutil.copytree(CONFIGURATION_PATH, target)
    return target


def _read_object(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    assert isinstance(value, dict)
    return value


def _mutate_and_rehash(
    path: Path, mutate: Callable[[dict[str, Any]], None]
) -> None:
    payload = _read_object(path)
    mutate(payload)
    payload_without_hash = dict(payload)
    payload_without_hash.pop("content_hash", None)
    canonical = json.dumps(
        payload_without_hash,
        ensure_ascii=True,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    payload["content_hash"] = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
