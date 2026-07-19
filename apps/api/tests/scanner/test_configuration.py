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
EXPECTED_UNIVERSE_METADATA = (
    ("SPY", "unleveraged_etf", "ARCX", None, "broad_benchmark"),
    ("QQQ", "unleveraged_etf", "ARCX", None, "broad_benchmark"),
    ("IWM", "unleveraged_etf", "ARCX", None, "broad_benchmark"),
    ("DIA", "unleveraged_etf", "ARCX", None, "broad_benchmark"),
    ("XLB", "unleveraged_etf", "ARCX", "materials", "sector_benchmark"),
    (
        "XLC",
        "unleveraged_etf",
        "ARCX",
        "communication_services",
        "sector_benchmark",
    ),
    ("XLE", "unleveraged_etf", "ARCX", "energy", "sector_benchmark"),
    ("XLF", "unleveraged_etf", "ARCX", "financials", "sector_benchmark"),
    ("XLI", "unleveraged_etf", "ARCX", "industrials", "sector_benchmark"),
    (
        "XLK",
        "unleveraged_etf",
        "ARCX",
        "information_technology",
        "sector_benchmark",
    ),
    (
        "XLP",
        "unleveraged_etf",
        "ARCX",
        "consumer_staples",
        "sector_benchmark",
    ),
    ("XLRE", "unleveraged_etf", "ARCX", "real_estate", "sector_benchmark"),
    ("XLU", "unleveraged_etf", "ARCX", "utilities", "sector_benchmark"),
    ("XLV", "unleveraged_etf", "ARCX", "health_care", "sector_benchmark"),
    (
        "XLY",
        "unleveraged_etf",
        "ARCX",
        "consumer_discretionary",
        "sector_benchmark",
    ),
    ("AAPL", "common_stock", "XNAS", "information_technology", "candidate"),
    ("MSFT", "common_stock", "XNAS", "information_technology", "candidate"),
    ("NVDA", "common_stock", "XNAS", "information_technology", "candidate"),
    ("AMZN", "common_stock", "XNAS", "consumer_discretionary", "candidate"),
    ("META", "common_stock", "XNAS", "communication_services", "candidate"),
    ("GOOGL", "common_stock", "XNAS", "communication_services", "candidate"),
    ("TSLA", "common_stock", "XNAS", "consumer_discretionary", "candidate"),
    ("AMD", "common_stock", "XNAS", "information_technology", "candidate"),
    ("AVGO", "common_stock", "XNAS", "information_technology", "candidate"),
    ("JPM", "common_stock", "XNYS", "financials", "candidate"),
    ("XOM", "common_stock", "XNYS", "energy", "candidate"),
    ("UNH", "common_stock", "XNYS", "health_care", "candidate"),
    ("LLY", "common_stock", "XNYS", "health_care", "candidate"),
    ("WMT", "common_stock", "XNAS", "consumer_staples", "candidate"),
    ("COST", "common_stock", "XNAS", "consumer_staples", "candidate"),
)

ELIGIBILITY_SEMANTIC_MUTATIONS: tuple[tuple[str, object], ...] = (
    ("allowed_security_types", ["unleveraged_etf", "common_stock"]),
    ("minimum_adjusted_close", "10.01"),
    ("maximum_adjusted_close", "999.99"),
    ("price_bounds_inclusive", False),
    ("minimum_completed_daily_sessions", 201),
    ("dollar_volume_window_sessions", 21),
    ("minimum_median_dollar_volume", "25000000.01"),
    ("dollar_volume_minimum_inclusive", False),
    ("permitted_quality_states", ["valid"]),
    ("provider_unavailable_blocks", False),
    ("halt_blocks", False),
    ("non_updating_quote_blocks", False),
    ("unsupported_adjustment_blocks", False),
    ("unresolved_corporate_action_blocks", False),
)

REGIME_THRESHOLD_MUTATIONS: tuple[tuple[str, object], ...] = (
    ("bullish_total_minimum", "36"),
    ("bearish_total_maximum", "-36"),
    ("mixed_strategy_minimum_absolute_total", "21"),
    ("breadth_bullish_above_sma_fraction", "0.61"),
    ("breadth_bearish_above_sma_fraction", "0.39"),
    ("participation_bullish_ratio", "1.51"),
    ("participation_bearish_ratio", "0.66"),
    ("sector_alignment_count", 8),
    ("volatility_change_minimum", "0.06"),
)

STRATEGY_THRESHOLD_MUTATIONS: tuple[tuple[str, object], ...] = (
    ("relative_volume_minimum", "1.51"),
    ("pullback_tolerance", "0.02"),
    ("price_extension_minimum", "0.0030"),
    ("mixed_direction_minimum", "21"),
    ("catalyst_lookback_completed_sessions", 3),
    ("news_regime_opposition_block_threshold", "36"),
)

SCORING_THRESHOLD_MUTATIONS: tuple[tuple[str, object], ...] = (
    ("candidate_threshold", "70.000001"),
    ("score_quantum", "0.000010"),
    ("relative_volume_standard_minimum", "1.51"),
    ("relative_volume_high_minimum", "2.01"),
    ("price_extension_minimum", "0.0030"),
    ("relative_strength_bullish_standard_minimum", "71"),
    ("relative_strength_bullish_exceptional_minimum", "86"),
    ("relative_strength_bearish_standard_maximum", "29"),
    ("relative_strength_bearish_exceptional_maximum", "14"),
)

COMPONENT_POINT_KEYS = (
    "established_trend",
    "aligned_regime",
    "neutral_reversal_regime",
    "mixed_compatible_regime",
    "price_trigger",
    "price_extension",
    "correct_vwap_side",
    "eligibility_liquidity",
    "relative_volume_standard",
    "relative_volume_high",
    "relative_strength_standard",
    "relative_strength_exceptional",
    "compatible_catalyst",
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
    assert tuple(
        (
            entry.display_symbol,
            entry.security_type,
            entry.exchange_family,
            entry.sector_code,
            entry.role,
        )
        for entry in configuration.universe.entries
    ) == EXPECTED_UNIVERSE_METADATA
    assert all(
        entry.active_from.isoformat() == "2026-01-01"
        for entry in configuration.universe.entries
    )
    assert all(entry.active_to is None for entry in configuration.universe.entries)

    assert configuration.eligibility.minimum_adjusted_close == Decimal("10.00")
    assert configuration.eligibility.maximum_adjusted_close == Decimal("1000.00")
    assert configuration.eligibility.minimum_completed_daily_sessions == 200
    assert configuration.eligibility.dollar_volume_window_sessions == 20
    assert configuration.eligibility.minimum_median_dollar_volume == Decimal(
        "25000000.00"
    )
    assert configuration.eligibility.price_bounds_inclusive is True
    assert configuration.eligibility.dollar_volume_minimum_inclusive is True
    assert configuration.eligibility.allowed_security_types == (
        "common_stock",
        "unleveraged_etf",
    )
    assert configuration.eligibility.permitted_quality_states == ("valid", "degraded")
    assert configuration.eligibility.provider_unavailable_blocks is True
    assert configuration.eligibility.halt_blocks is True
    assert configuration.eligibility.non_updating_quote_blocks is True
    assert configuration.eligibility.unsupported_adjustment_blocks is True
    assert configuration.eligibility.unresolved_corporate_action_blocks is True

    assert configuration.regime.component_weights == {
        "broad_trend": Decimal("30"),
        "breadth": Decimal("20"),
        "sector_participation": Decimal("15"),
        "volume_participation": Decimal("10"),
        "volatility_direction": Decimal("15"),
        "macro_overlay": Decimal("10"),
    }
    assert configuration.regime.bullish_total_minimum == Decimal("35")
    assert configuration.regime.bearish_total_maximum == Decimal("-35")
    assert configuration.regime.mixed_strategy_minimum_absolute_total == Decimal("20")
    assert configuration.regime.breadth_bullish_above_sma_fraction == Decimal("0.60")
    assert configuration.regime.breadth_bearish_above_sma_fraction == Decimal("0.40")
    assert configuration.regime.participation_bullish_ratio == Decimal("1.50")
    assert configuration.regime.participation_bearish_ratio == Decimal("0.67")
    assert configuration.regime.sector_alignment_count == 7
    assert configuration.regime.volatility_change_minimum == Decimal("0.05")

    assert tuple(rule.strategy_id for rule in configuration.strategies.rules) == (
        "bullish_breakout",
        "bullish_pullback",
        "bearish_breakdown",
        "bearish_failed_rally",
        "news_continuation",
    )
    assert configuration.strategies.relative_volume_minimum == Decimal("1.50")
    assert configuration.strategies.pullback_tolerance == Decimal("0.01")
    assert configuration.strategies.price_extension_minimum == Decimal("0.0025")
    assert configuration.strategies.mixed_direction_minimum == Decimal("20")
    assert configuration.strategies.catalyst_lookback_completed_sessions == 2
    assert configuration.strategies.news_regime_opposition_block_threshold == Decimal(
        "35"
    )

    assert configuration.scoring.family_caps == {
        "market_direction": Decimal("25"),
        "price_structure": Decimal("30"),
        "participation_liquidity": Decimal("20"),
        "relative_performance": Decimal("15"),
        "catalyst": Decimal("10"),
    }
    assert configuration.scoring.candidate_threshold == Decimal("70.000000")
    assert configuration.scoring.score_quantum == Decimal("0.000001")
    assert configuration.scoring.relative_volume_standard_minimum == Decimal("1.50")
    assert configuration.scoring.price_extension_minimum == Decimal("0.0025")
    assert configuration.scoring.relative_volume_high_minimum == Decimal("2.00")
    assert configuration.scoring.relative_strength_bullish_standard_minimum == Decimal(
        "70"
    )
    assert configuration.scoring.relative_strength_bullish_exceptional_minimum == Decimal(
        "85"
    )
    assert configuration.scoring.relative_strength_bearish_standard_maximum == Decimal(
        "30"
    )
    assert configuration.scoring.relative_strength_bearish_exceptional_maximum == Decimal(
        "15"
    )
    assert configuration.scoring.component_points == {
        "established_trend": Decimal("15"),
        "aligned_regime": Decimal("10"),
        "neutral_reversal_regime": Decimal("5"),
        "mixed_compatible_regime": Decimal("5"),
        "price_trigger": Decimal("20"),
        "price_extension": Decimal("5"),
        "correct_vwap_side": Decimal("5"),
        "eligibility_liquidity": Decimal("5"),
        "relative_volume_standard": Decimal("10"),
        "relative_volume_high": Decimal("15"),
        "relative_strength_standard": Decimal("10"),
        "relative_strength_exceptional": Decimal("15"),
        "compatible_catalyst": Decimal("10"),
    }
    assert (
        configuration.strategies.mixed_direction_minimum
        == configuration.regime.mixed_strategy_minimum_absolute_total
    )
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

    with pytest.raises(ConfigurationError, match="does not match version one"):
        load_scanner_configuration(copied)


@pytest.mark.parametrize("entry_index", range(len(EXPECTED_SYMBOLS)))
@pytest.mark.parametrize(
    "field",
    (
        "security_type",
        "exchange_family",
        "sector_code",
        "role",
        "candidate_enabled",
        "active_from",
        "active_to",
    ),
)
def test_rejects_self_rehashed_universe_metadata_changes(
    tmp_path: Path, entry_index: int, field: str
) -> None:
    copied = _copy_configuration(tmp_path)

    def mutate(payload: dict[str, Any]) -> None:
        entries = payload["entries"]
        assert isinstance(entries, list)
        entry = entries[entry_index]
        assert isinstance(entry, dict)
        entry[field] = _alternate_universe_value(field, entry[field])

    _mutate_and_rehash(copied / "eligible-universe-v1.json", mutate)

    with pytest.raises(ConfigurationError):
        load_scanner_configuration(copied)


@pytest.mark.parametrize(("field", "replacement"), ELIGIBILITY_SEMANTIC_MUTATIONS)
def test_rejects_self_rehashed_eligibility_changes(
    tmp_path: Path, field: str, replacement: object
) -> None:
    copied = _copy_configuration(tmp_path)
    _mutate_and_rehash(
        copied / "eligibility-policy-v1.json",
        lambda payload: payload.__setitem__(field, replacement),
    )

    with pytest.raises(ConfigurationError, match="version one"):
        load_scanner_configuration(copied)


@pytest.mark.parametrize(("field", "replacement"), REGIME_THRESHOLD_MUTATIONS)
def test_rejects_self_rehashed_regime_threshold_changes(
    tmp_path: Path, field: str, replacement: object
) -> None:
    copied = _copy_configuration(tmp_path)
    _mutate_and_rehash(
        copied / "market-regime-v1.json",
        lambda payload: payload.__setitem__(field, replacement),
    )

    expected_message = (
        "mixed thresholds"
        if field == "mixed_strategy_minimum_absolute_total"
        else "version one"
    )
    with pytest.raises(ConfigurationError, match=expected_message):
        load_scanner_configuration(copied)


@pytest.mark.parametrize(
    "weight",
    (
        "broad_trend",
        "breadth",
        "sector_participation",
        "volume_participation",
        "volatility_direction",
        "macro_overlay",
    ),
)
def test_rejects_self_rehashed_regime_weight_changes(
    tmp_path: Path, weight: str
) -> None:
    copied = _copy_configuration(tmp_path)

    def mutate(payload: dict[str, Any]) -> None:
        weights = payload["component_weights"]
        assert isinstance(weights, dict)
        balancing_key = "macro_overlay" if weight != "macro_overlay" else "broad_trend"
        weights[weight] = str(Decimal(str(weights[weight])) + 1)
        weights[balancing_key] = str(Decimal(str(weights[balancing_key])) - 1)

    _mutate_and_rehash(copied / "market-regime-v1.json", mutate)

    with pytest.raises(ConfigurationError, match="version one"):
        load_scanner_configuration(copied)


@pytest.mark.parametrize(("field", "replacement"), STRATEGY_THRESHOLD_MUTATIONS)
def test_rejects_self_rehashed_strategy_threshold_changes(
    tmp_path: Path, field: str, replacement: object
) -> None:
    copied = _copy_configuration(tmp_path)
    _mutate_and_rehash(
        copied / "scanner-strategies-v1.json",
        lambda payload: payload.__setitem__(field, replacement),
    )

    expected_message = (
        "mixed thresholds" if field == "mixed_direction_minimum" else "version one"
    )
    with pytest.raises(ConfigurationError, match=expected_message):
        load_scanner_configuration(copied)


@pytest.mark.parametrize(("field", "replacement"), SCORING_THRESHOLD_MUTATIONS)
def test_rejects_self_rehashed_scoring_threshold_changes(
    tmp_path: Path, field: str, replacement: object
) -> None:
    copied = _copy_configuration(tmp_path)
    _mutate_and_rehash(
        copied / "candidate-scoring-v1.json",
        lambda payload: payload.__setitem__(field, replacement),
    )

    with pytest.raises(ConfigurationError, match="version one"):
        load_scanner_configuration(copied)


@pytest.mark.parametrize(
    "family",
    (
        "market_direction",
        "price_structure",
        "participation_liquidity",
        "relative_performance",
        "catalyst",
    ),
)
def test_rejects_self_rehashed_family_cap_changes(tmp_path: Path, family: str) -> None:
    copied = _copy_configuration(tmp_path)

    def mutate(payload: dict[str, Any]) -> None:
        caps = payload["family_caps"]
        assert isinstance(caps, dict)
        balancing_key = "catalyst" if family != "catalyst" else "market_direction"
        caps[family] = str(Decimal(str(caps[family])) + 1)
        caps[balancing_key] = str(Decimal(str(caps[balancing_key])) - 1)

    _mutate_and_rehash(copied / "candidate-scoring-v1.json", mutate)

    with pytest.raises(ConfigurationError, match="version one"):
        load_scanner_configuration(copied)


@pytest.mark.parametrize("component", COMPONENT_POINT_KEYS)
def test_rejects_self_rehashed_component_contribution_changes(
    tmp_path: Path, component: str
) -> None:
    copied = _copy_configuration(tmp_path)

    def mutate(payload: dict[str, Any]) -> None:
        points = payload["component_points"]
        assert isinstance(points, dict)
        points[component] = str(Decimal(str(points[component])) + 1)

    _mutate_and_rehash(copied / "candidate-scoring-v1.json", mutate)

    with pytest.raises(ConfigurationError, match="version one"):
        load_scanner_configuration(copied)


def test_rejects_cross_policy_mixed_threshold_mismatch(tmp_path: Path) -> None:
    copied = _copy_configuration(tmp_path)
    _mutate_and_rehash(
        copied / "scanner-strategies-v1.json",
        lambda payload: payload.__setitem__("mixed_direction_minimum", "19"),
    )

    with pytest.raises(ConfigurationError, match="mixed thresholds"):
        load_scanner_configuration(copied)


@pytest.mark.parametrize(
    ("filename", "mapping_field", "nested_field"),
    (
        ("market-regime-v1.json", "component_weights", "broad_trend"),
        ("candidate-scoring-v1.json", "family_caps", "market_direction"),
        ("candidate-scoring-v1.json", "component_points", "price_trigger"),
    ),
)
def test_rejects_nested_numeric_json_decimals(
    tmp_path: Path, filename: str, mapping_field: str, nested_field: str
) -> None:
    copied = _copy_configuration(tmp_path)

    def mutate(payload: dict[str, Any]) -> None:
        nested = payload[mapping_field]
        assert isinstance(nested, dict)
        nested[nested_field] = 1.5

    _mutate_and_rehash(copied / filename, mutate)

    with pytest.raises(ConfigurationError, match="decimal string"):
        load_scanner_configuration(copied)


@pytest.mark.parametrize("value", ("NaN", "Infinity", "-Infinity"))
def test_rejects_nonfinite_decimal_strings(tmp_path: Path, value: str) -> None:
    copied = _copy_configuration(tmp_path)
    _mutate_and_rehash(
        copied / "market-regime-v1.json",
        lambda payload: payload.__setitem__("bullish_total_minimum", value),
    )

    with pytest.raises(ConfigurationError, match="finite decimal string"):
        load_scanner_configuration(copied)


@pytest.mark.parametrize("token", ("NaN", "Infinity", "-Infinity"))
def test_normalizes_nonfinite_json_number_errors(tmp_path: Path, token: str) -> None:
    copied = _copy_configuration(tmp_path)
    path = copied / "market-regime-v1.json"
    text = path.read_text(encoding="utf-8")
    path.write_text(
        text.replace(
            '"bullish_total_minimum": "35"',
            f'"bullish_total_minimum": {token}',
        )
    )

    with pytest.raises(ConfigurationError) as error:
        load_scanner_configuration(copied)

    assert str(error.value) == "market-regime-v1.json has invalid canonical content"


def test_normalizes_unicode_decode_errors_without_absolute_paths(tmp_path: Path) -> None:
    copied = _copy_configuration(tmp_path)
    (copied / "eligible-universe-v1.json").write_bytes(b"\xff\xfe")

    with pytest.raises(ConfigurationError) as error:
        load_scanner_configuration(copied)

    assert str(error.value) == "cannot read configuration eligible-universe-v1.json"
    assert str(copied) not in str(error.value)


def test_normalizes_missing_file_errors_without_absolute_paths(tmp_path: Path) -> None:
    missing = tmp_path / "does-not-exist"

    with pytest.raises(ConfigurationError) as error:
        load_scanner_configuration(missing)

    assert str(error.value) == "cannot read configuration eligible-universe-v1.json"
    assert str(missing) not in str(error.value)


def test_rejects_nested_unknown_fields_even_with_matching_hash(tmp_path: Path) -> None:
    copied = _copy_configuration(tmp_path)

    def mutate(payload: dict[str, Any]) -> None:
        caps = payload["family_caps"]
        assert isinstance(caps, dict)
        caps["unapproved_family"] = "0"

    _mutate_and_rehash(copied / "candidate-scoring-v1.json", mutate)

    with pytest.raises(ConfigurationError, match="unknown field"):
        load_scanner_configuration(copied)


def test_rejects_nested_duplicate_json_keys(tmp_path: Path) -> None:
    copied = _copy_configuration(tmp_path)
    path = copied / "market-regime-v1.json"
    text = path.read_text(encoding="utf-8")
    path.write_text(
        text.replace(
            '"broad_trend": "30",',
            '"broad_trend": "30", "broad_trend": "30",',
            1,
        ),
        encoding="utf-8",
    )

    with pytest.raises(ConfigurationError, match="duplicate JSON key"):
        load_scanner_configuration(copied)


def _alternate_universe_value(field: str, current: object) -> object:
    alternatives: dict[str, object] = {
        "security_type": (
            "common_stock" if current == "unleveraged_etf" else "unleveraged_etf"
        ),
        "exchange_family": "XNYS" if current != "XNYS" else "XNAS",
        "sector_code": "materials" if current != "materials" else "energy",
        "role": "candidate" if current != "candidate" else "sector_benchmark",
        "candidate_enabled": False,
        "active_from": "2025-01-01",
        "active_to": "2030-01-01",
    }
    return alternatives[field]


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
