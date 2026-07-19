from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import date
from decimal import Decimal, InvalidOperation
from pathlib import Path
from types import MappingProxyType
from typing import Any, cast

from market_trader.market_data.sanitization import canonical_json
from market_trader.scanner.models import PolicyVersions

_FILES = MappingProxyType(
    {
        "universe": "eligible-universe-v1.json",
        "eligibility": "eligibility-policy-v1.json",
        "regime": "market-regime-v1.json",
        "strategies": "scanner-strategies-v1.json",
        "scoring": "candidate-scoring-v1.json",
    }
)
_VERSIONS = PolicyVersions()
_EXPECTED_SYMBOLS = (
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
_EXPECTED_UNIVERSE_METADATA = (
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
_SECTOR_CODES = frozenset(
    {
        "communication_services",
        "consumer_discretionary",
        "consumer_staples",
        "energy",
        "financials",
        "health_care",
        "industrials",
        "information_technology",
        "materials",
        "real_estate",
        "utilities",
    }
)
_HASH_PATTERN = re.compile(r"[0-9a-f]{64}")


class ConfigurationError(ValueError):
    """Raised when checked-in scanner configuration is not exact and valid."""


@dataclass(frozen=True)
class UniverseEntry:
    display_symbol: str
    security_type: str
    exchange_family: str
    sector_code: str | None
    role: str
    candidate_enabled: bool
    active_from: date
    active_to: date | None


@dataclass(frozen=True)
class UniversePolicy:
    version: str
    entries: tuple[UniverseEntry, ...]


@dataclass(frozen=True)
class EligibilityPolicy:
    version: str
    allowed_security_types: tuple[str, ...]
    minimum_adjusted_close: Decimal
    maximum_adjusted_close: Decimal
    price_bounds_inclusive: bool
    minimum_completed_daily_sessions: int
    dollar_volume_window_sessions: int
    minimum_median_dollar_volume: Decimal
    dollar_volume_minimum_inclusive: bool
    permitted_quality_states: tuple[str, ...]
    provider_unavailable_blocks: bool
    halt_blocks: bool
    non_updating_quote_blocks: bool
    unsupported_adjustment_blocks: bool
    unresolved_corporate_action_blocks: bool


@dataclass(frozen=True)
class RegimePolicy:
    version: str
    component_weights: Mapping[str, Decimal]
    bullish_total_minimum: Decimal
    bearish_total_maximum: Decimal
    mixed_strategy_minimum_absolute_total: Decimal
    breadth_bullish_above_sma_fraction: Decimal
    breadth_bearish_above_sma_fraction: Decimal
    participation_bullish_ratio: Decimal
    participation_bearish_ratio: Decimal
    sector_alignment_count: int
    volatility_change_minimum: Decimal


@dataclass(frozen=True)
class StrategyRule:
    strategy_id: str
    direction: str


@dataclass(frozen=True)
class StrategyPolicy:
    version: str
    feature_version: str
    evidence_version: str
    rules: tuple[StrategyRule, ...]
    relative_volume_minimum: Decimal
    pullback_tolerance: Decimal
    price_extension_minimum: Decimal
    mixed_direction_minimum: Decimal
    catalyst_lookback_completed_sessions: int
    news_regime_opposition_block_threshold: Decimal


@dataclass(frozen=True)
class ScoringPolicy:
    version: str
    family_caps: Mapping[str, Decimal]
    candidate_threshold: Decimal
    score_quantum: Decimal
    relative_volume_standard_minimum: Decimal
    relative_volume_high_minimum: Decimal
    price_extension_minimum: Decimal
    relative_strength_bullish_standard_minimum: Decimal
    relative_strength_bullish_exceptional_minimum: Decimal
    relative_strength_bearish_standard_maximum: Decimal
    relative_strength_bearish_exceptional_maximum: Decimal
    component_points: Mapping[str, Decimal]


@dataclass(frozen=True)
class ScannerConfiguration:
    universe: UniversePolicy
    eligibility: EligibilityPolicy
    regime: RegimePolicy
    strategies: StrategyPolicy
    scoring: ScoringPolicy
    content_hashes: Mapping[str, str]

    @property
    def versions(self) -> PolicyVersions:
        return PolicyVersions(
            universe=self.universe.version,
            eligibility=self.eligibility.version,
            features=self.strategies.feature_version,
            regime=self.regime.version,
            strategies=self.strategies.version,
            scoring=self.scoring.version,
            evidence=self.strategies.evidence_version,
            fixture=_VERSIONS.fixture,
        )


def load_scanner_configuration(path: Path | str) -> ScannerConfiguration:
    root = Path(path)
    payloads: dict[str, dict[str, object]] = {}
    hashes: dict[str, str] = {}
    for policy_name, filename in _FILES.items():
        payload, content_hash = _load_document(root / filename)
        payloads[policy_name] = payload
        hashes[policy_name] = content_hash

    configuration = ScannerConfiguration(
        universe=_parse_universe(payloads["universe"]),
        eligibility=_parse_eligibility(payloads["eligibility"]),
        regime=_parse_regime(payloads["regime"]),
        strategies=_parse_strategies(payloads["strategies"]),
        scoring=_parse_scoring(payloads["scoring"]),
        content_hashes=_immutable_mapping(hashes),
    )
    if configuration.versions != _VERSIONS:
        raise ConfigurationError("scanner configuration versions do not match version one")
    if (
        configuration.strategies.mixed_direction_minimum
        != configuration.regime.mixed_strategy_minimum_absolute_total
    ):
        raise ConfigurationError("strategy and regime mixed thresholds must match")
    _validate_version_one(configuration)
    return configuration


def _load_document(path: Path) -> tuple[dict[str, object], str]:
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        raise ConfigurationError(f"cannot read configuration {path.name}") from None
    try:
        raw = json.loads(text, object_pairs_hook=_unique_object)
    except json.JSONDecodeError:
        raise ConfigurationError(f"{path.name} is not valid JSON") from None
    if not isinstance(raw, dict):
        raise ConfigurationError(f"{path.name} must contain a JSON object")
    payload = cast(dict[str, object], raw)
    declared_hash = payload.get("content_hash")
    if not isinstance(declared_hash, str) or _HASH_PATTERN.fullmatch(declared_hash) is None:
        raise ConfigurationError(f"{path.name} content_hash must be 64 lowercase hex characters")
    hash_input = dict(payload)
    del hash_input["content_hash"]
    try:
        canonical = canonical_json(cast(Any, hash_input))
    except (TypeError, ValueError):
        raise ConfigurationError(f"{path.name} has invalid canonical content") from None
    calculated_hash = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
    if declared_hash != calculated_hash:
        raise ConfigurationError(f"{path.name} content_hash does not match its payload")
    return payload, declared_hash


def _parse_universe(payload: dict[str, object]) -> UniversePolicy:
    _require_keys(payload, {"version", "content_hash", "entries"}, "universe")
    _require_version(payload, _VERSIONS.universe, "universe")
    raw_entries = _list(payload["entries"], "universe.entries")
    entries: list[UniverseEntry] = []
    seen: set[str] = set()
    for index, raw_entry in enumerate(raw_entries):
        location = f"universe.entries[{index}]"
        entry = _object(raw_entry, location)
        _require_keys(
            entry,
            {
                "display_symbol",
                "security_type",
                "exchange_family",
                "sector_code",
                "role",
                "candidate_enabled",
                "active_from",
                "active_to",
            },
            location,
        )
        symbol = _string(entry["display_symbol"], f"{location}.display_symbol")
        if symbol in seen:
            raise ConfigurationError(f"duplicate symbol in universe: {symbol}")
        seen.add(symbol)
        security_type = _choice(
            entry["security_type"],
            {"common_stock", "unleveraged_etf"},
            f"{location}.security_type",
        )
        exchange_family = _choice(
            entry["exchange_family"], {"ARCX", "XNAS", "XNYS"}, f"{location}.exchange_family"
        )
        role = _choice(
            entry["role"],
            {"broad_benchmark", "sector_benchmark", "candidate"},
            f"{location}.role",
        )
        sector_code = _optional_choice(
            entry["sector_code"], _SECTOR_CODES, f"{location}.sector_code"
        )
        if role == "sector_benchmark" and sector_code is None:
            raise ConfigurationError(f"{location} is missing its benchmark sector role")
        if role == "broad_benchmark" and sector_code is not None:
            raise ConfigurationError(f"{location} broad benchmark cannot declare a sector")
        active_from = _date(entry["active_from"], f"{location}.active_from")
        active_to = _optional_date(entry["active_to"], f"{location}.active_to")
        if active_to is not None and active_to < active_from:
            raise ConfigurationError(f"{location} active date range is inverted")
        entries.append(
            UniverseEntry(
                display_symbol=symbol,
                security_type=security_type,
                exchange_family=exchange_family,
                sector_code=sector_code,
                role=role,
                candidate_enabled=_boolean(
                    entry["candidate_enabled"], f"{location}.candidate_enabled"
                ),
                active_from=active_from,
                active_to=active_to,
            )
        )
    return UniversePolicy(version=_VERSIONS.universe, entries=tuple(entries))


def _parse_eligibility(payload: dict[str, object]) -> EligibilityPolicy:
    keys = {
        "version",
        "content_hash",
        "allowed_security_types",
        "minimum_adjusted_close",
        "maximum_adjusted_close",
        "price_bounds_inclusive",
        "minimum_completed_daily_sessions",
        "dollar_volume_window_sessions",
        "minimum_median_dollar_volume",
        "dollar_volume_minimum_inclusive",
        "permitted_quality_states",
        "provider_unavailable_blocks",
        "halt_blocks",
        "non_updating_quote_blocks",
        "unsupported_adjustment_blocks",
        "unresolved_corporate_action_blocks",
    }
    _require_keys(payload, keys, "eligibility")
    _require_version(payload, _VERSIONS.eligibility, "eligibility")
    allowed_types = _string_tuple(payload["allowed_security_types"], "allowed_security_types")
    if len(set(allowed_types)) != len(allowed_types) or not set(allowed_types) <= {
        "common_stock",
        "unleveraged_etf",
    }:
        raise ConfigurationError("eligibility allowed_security_types are invalid")
    quality_states = _string_tuple(payload["permitted_quality_states"], "permitted_quality_states")
    if len(set(quality_states)) != len(quality_states) or not set(quality_states) <= {
        "valid",
        "degraded",
    }:
        raise ConfigurationError("eligibility permitted_quality_states are invalid")
    result = EligibilityPolicy(
        version=_VERSIONS.eligibility,
        allowed_security_types=allowed_types,
        minimum_adjusted_close=_decimal_string(
            payload["minimum_adjusted_close"], "minimum_adjusted_close"
        ),
        maximum_adjusted_close=_decimal_string(
            payload["maximum_adjusted_close"], "maximum_adjusted_close"
        ),
        price_bounds_inclusive=_boolean(
            payload["price_bounds_inclusive"], "price_bounds_inclusive"
        ),
        minimum_completed_daily_sessions=_positive_int(
            payload["minimum_completed_daily_sessions"], "minimum_completed_daily_sessions"
        ),
        dollar_volume_window_sessions=_positive_int(
            payload["dollar_volume_window_sessions"], "dollar_volume_window_sessions"
        ),
        minimum_median_dollar_volume=_decimal_string(
            payload["minimum_median_dollar_volume"], "minimum_median_dollar_volume"
        ),
        dollar_volume_minimum_inclusive=_boolean(
            payload["dollar_volume_minimum_inclusive"], "dollar_volume_minimum_inclusive"
        ),
        permitted_quality_states=quality_states,
        provider_unavailable_blocks=_boolean(
            payload["provider_unavailable_blocks"], "provider_unavailable_blocks"
        ),
        halt_blocks=_boolean(payload["halt_blocks"], "halt_blocks"),
        non_updating_quote_blocks=_boolean(
            payload["non_updating_quote_blocks"], "non_updating_quote_blocks"
        ),
        unsupported_adjustment_blocks=_boolean(
            payload["unsupported_adjustment_blocks"], "unsupported_adjustment_blocks"
        ),
        unresolved_corporate_action_blocks=_boolean(
            payload["unresolved_corporate_action_blocks"],
            "unresolved_corporate_action_blocks",
        ),
    )
    return result


def _parse_regime(payload: dict[str, object]) -> RegimePolicy:
    keys = {
        "version",
        "content_hash",
        "component_weights",
        "bullish_total_minimum",
        "bearish_total_maximum",
        "mixed_strategy_minimum_absolute_total",
        "breadth_bullish_above_sma_fraction",
        "breadth_bearish_above_sma_fraction",
        "participation_bullish_ratio",
        "participation_bearish_ratio",
        "sector_alignment_count",
        "volatility_change_minimum",
    }
    _require_keys(payload, keys, "regime")
    _require_version(payload, _VERSIONS.regime, "regime")
    weights = _decimal_mapping(
        payload["component_weights"],
        {
            "broad_trend",
            "breadth",
            "sector_participation",
            "volume_participation",
            "volatility_direction",
            "macro_overlay",
        },
        "component_weights",
    )
    if sum(weights.values(), Decimal()) != Decimal("100"):
        raise ConfigurationError("regime component weights must total 100")
    result = RegimePolicy(
        version=_VERSIONS.regime,
        component_weights=weights,
        bullish_total_minimum=_decimal_string(
            payload["bullish_total_minimum"], "bullish_total_minimum"
        ),
        bearish_total_maximum=_decimal_string(
            payload["bearish_total_maximum"], "bearish_total_maximum"
        ),
        mixed_strategy_minimum_absolute_total=_decimal_string(
            payload["mixed_strategy_minimum_absolute_total"],
            "mixed_strategy_minimum_absolute_total",
        ),
        breadth_bullish_above_sma_fraction=_decimal_string(
            payload["breadth_bullish_above_sma_fraction"],
            "breadth_bullish_above_sma_fraction",
        ),
        breadth_bearish_above_sma_fraction=_decimal_string(
            payload["breadth_bearish_above_sma_fraction"],
            "breadth_bearish_above_sma_fraction",
        ),
        participation_bullish_ratio=_decimal_string(
            payload["participation_bullish_ratio"], "participation_bullish_ratio"
        ),
        participation_bearish_ratio=_decimal_string(
            payload["participation_bearish_ratio"], "participation_bearish_ratio"
        ),
        sector_alignment_count=_positive_int(
            payload["sector_alignment_count"], "sector_alignment_count"
        ),
        volatility_change_minimum=_decimal_string(
            payload["volatility_change_minimum"], "volatility_change_minimum"
        ),
    )
    return result


def _parse_strategies(payload: dict[str, object]) -> StrategyPolicy:
    keys = {
        "version",
        "content_hash",
        "feature_version",
        "evidence_version",
        "rules",
        "relative_volume_minimum",
        "pullback_tolerance",
        "price_extension_minimum",
        "mixed_direction_minimum",
        "catalyst_lookback_completed_sessions",
        "news_regime_opposition_block_threshold",
    }
    _require_keys(payload, keys, "strategies")
    _require_version(payload, _VERSIONS.strategies, "strategies")
    feature_version = _string(payload["feature_version"], "feature_version")
    evidence_version = _string(payload["evidence_version"], "evidence_version")
    if feature_version != _VERSIONS.features or evidence_version != _VERSIONS.evidence:
        raise ConfigurationError("strategy applicable versions do not match version one")
    raw_rules = _list(payload["rules"], "rules")
    rules: list[StrategyRule] = []
    for index, raw_rule in enumerate(raw_rules):
        location = f"rules[{index}]"
        rule = _object(raw_rule, location)
        _require_keys(rule, {"strategy_id", "direction"}, location)
        rules.append(
            StrategyRule(
                strategy_id=_string(rule["strategy_id"], f"{location}.strategy_id"),
                direction=_choice(
                    rule["direction"], {"bullish", "bearish", "evidence"}, f"{location}.direction"
                ),
            )
        )
    return StrategyPolicy(
        version=_VERSIONS.strategies,
        feature_version=feature_version,
        evidence_version=evidence_version,
        rules=tuple(rules),
        relative_volume_minimum=_decimal_string(
            payload["relative_volume_minimum"], "relative_volume_minimum"
        ),
        pullback_tolerance=_decimal_string(payload["pullback_tolerance"], "pullback_tolerance"),
        price_extension_minimum=_decimal_string(
            payload["price_extension_minimum"], "price_extension_minimum"
        ),
        mixed_direction_minimum=_decimal_string(
            payload["mixed_direction_minimum"], "mixed_direction_minimum"
        ),
        catalyst_lookback_completed_sessions=_positive_int(
            payload["catalyst_lookback_completed_sessions"],
            "catalyst_lookback_completed_sessions",
        ),
        news_regime_opposition_block_threshold=_decimal_string(
            payload["news_regime_opposition_block_threshold"],
            "news_regime_opposition_block_threshold",
        ),
    )


def _parse_scoring(payload: dict[str, object]) -> ScoringPolicy:
    keys = {
        "version",
        "content_hash",
        "family_caps",
        "candidate_threshold",
        "score_quantum",
        "relative_volume_standard_minimum",
        "relative_volume_high_minimum",
        "price_extension_minimum",
        "relative_strength_bullish_standard_minimum",
        "relative_strength_bullish_exceptional_minimum",
        "relative_strength_bearish_standard_maximum",
        "relative_strength_bearish_exceptional_maximum",
        "component_points",
    }
    _require_keys(payload, keys, "scoring")
    _require_version(payload, _VERSIONS.scoring, "scoring")
    caps = _decimal_mapping(
        payload["family_caps"],
        {
            "market_direction",
            "price_structure",
            "participation_liquidity",
            "relative_performance",
            "catalyst",
        },
        "family_caps",
    )
    if sum(caps.values(), Decimal()) != Decimal("100"):
        raise ConfigurationError("scoring family caps must total 100")
    component_points = _decimal_mapping(
        payload["component_points"],
        {
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
        },
        "component_points",
    )
    return ScoringPolicy(
        version=_VERSIONS.scoring,
        family_caps=caps,
        candidate_threshold=_decimal_string(payload["candidate_threshold"], "candidate_threshold"),
        score_quantum=_decimal_string(payload["score_quantum"], "score_quantum"),
        relative_volume_standard_minimum=_decimal_string(
            payload["relative_volume_standard_minimum"],
            "relative_volume_standard_minimum",
        ),
        relative_volume_high_minimum=_decimal_string(
            payload["relative_volume_high_minimum"], "relative_volume_high_minimum"
        ),
        price_extension_minimum=_decimal_string(
            payload["price_extension_minimum"], "price_extension_minimum"
        ),
        relative_strength_bullish_standard_minimum=_decimal_string(
            payload["relative_strength_bullish_standard_minimum"],
            "relative_strength_bullish_standard_minimum",
        ),
        relative_strength_bullish_exceptional_minimum=_decimal_string(
            payload["relative_strength_bullish_exceptional_minimum"],
            "relative_strength_bullish_exceptional_minimum",
        ),
        relative_strength_bearish_standard_maximum=_decimal_string(
            payload["relative_strength_bearish_standard_maximum"],
            "relative_strength_bearish_standard_maximum",
        ),
        relative_strength_bearish_exceptional_maximum=_decimal_string(
            payload["relative_strength_bearish_exceptional_maximum"],
            "relative_strength_bearish_exceptional_maximum",
        ),
        component_points=component_points,
    )


def _validate_version_one(configuration: ScannerConfiguration) -> None:
    universe_metadata = tuple(
        (
            entry.display_symbol,
            entry.security_type,
            entry.exchange_family,
            entry.sector_code,
            entry.role,
        )
        for entry in configuration.universe.entries
    )
    expected_active_from = date(2026, 1, 1)
    if (
        universe_metadata != _EXPECTED_UNIVERSE_METADATA
        or tuple(entry.display_symbol for entry in configuration.universe.entries)
        != _EXPECTED_SYMBOLS
        or not all(entry.candidate_enabled for entry in configuration.universe.entries)
        or not all(
            entry.active_from == expected_active_from
            for entry in configuration.universe.entries
        )
        or not all(entry.active_to is None for entry in configuration.universe.entries)
    ):
        raise ConfigurationError("universe policy does not match version one")

    if configuration.eligibility != EligibilityPolicy(
        version=_VERSIONS.eligibility,
        allowed_security_types=("common_stock", "unleveraged_etf"),
        minimum_adjusted_close=Decimal("10.00"),
        maximum_adjusted_close=Decimal("1000.00"),
        price_bounds_inclusive=True,
        minimum_completed_daily_sessions=200,
        dollar_volume_window_sessions=20,
        minimum_median_dollar_volume=Decimal("25000000.00"),
        dollar_volume_minimum_inclusive=True,
        permitted_quality_states=("valid", "degraded"),
        provider_unavailable_blocks=True,
        halt_blocks=True,
        non_updating_quote_blocks=True,
        unsupported_adjustment_blocks=True,
        unresolved_corporate_action_blocks=True,
    ):
        raise ConfigurationError("eligibility policy does not match version one")

    if configuration.regime != RegimePolicy(
        version=_VERSIONS.regime,
        component_weights=_immutable_mapping(
            {
                "broad_trend": Decimal("30"),
                "breadth": Decimal("20"),
                "sector_participation": Decimal("15"),
                "volume_participation": Decimal("10"),
                "volatility_direction": Decimal("15"),
                "macro_overlay": Decimal("10"),
            }
        ),
        bullish_total_minimum=Decimal("35"),
        bearish_total_maximum=Decimal("-35"),
        mixed_strategy_minimum_absolute_total=Decimal("20"),
        breadth_bullish_above_sma_fraction=Decimal("0.60"),
        breadth_bearish_above_sma_fraction=Decimal("0.40"),
        participation_bullish_ratio=Decimal("1.50"),
        participation_bearish_ratio=Decimal("0.67"),
        sector_alignment_count=7,
        volatility_change_minimum=Decimal("0.05"),
    ):
        raise ConfigurationError("regime policy does not match version one")

    if configuration.strategies != StrategyPolicy(
        version=_VERSIONS.strategies,
        feature_version=_VERSIONS.features,
        evidence_version=_VERSIONS.evidence,
        rules=(
            StrategyRule("bullish_breakout", "bullish"),
            StrategyRule("bullish_pullback", "bullish"),
            StrategyRule("bearish_breakdown", "bearish"),
            StrategyRule("bearish_failed_rally", "bearish"),
            StrategyRule("news_continuation", "evidence"),
        ),
        relative_volume_minimum=Decimal("1.50"),
        pullback_tolerance=Decimal("0.01"),
        price_extension_minimum=Decimal("0.0025"),
        mixed_direction_minimum=Decimal("20"),
        catalyst_lookback_completed_sessions=2,
        news_regime_opposition_block_threshold=Decimal("35"),
    ):
        raise ConfigurationError("strategy policy does not match version one")

    if configuration.scoring != ScoringPolicy(
        version=_VERSIONS.scoring,
        family_caps=_immutable_mapping(
            {
                "market_direction": Decimal("25"),
                "price_structure": Decimal("30"),
                "participation_liquidity": Decimal("20"),
                "relative_performance": Decimal("15"),
                "catalyst": Decimal("10"),
            }
        ),
        candidate_threshold=Decimal("70.000000"),
        score_quantum=Decimal("0.000001"),
        relative_volume_standard_minimum=Decimal("1.50"),
        relative_volume_high_minimum=Decimal("2.00"),
        price_extension_minimum=Decimal("0.0025"),
        relative_strength_bullish_standard_minimum=Decimal("70"),
        relative_strength_bullish_exceptional_minimum=Decimal("85"),
        relative_strength_bearish_standard_maximum=Decimal("30"),
        relative_strength_bearish_exceptional_maximum=Decimal("15"),
        component_points=_immutable_mapping(
            {
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
        ),
    ):
        raise ConfigurationError("scoring policy does not match version one")


def _unique_object(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise ConfigurationError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def _require_keys(value: Mapping[str, object], expected: set[str], location: str) -> None:
    actual = set(value)
    unknown = actual - expected
    missing = expected - actual
    if unknown:
        raise ConfigurationError(f"{location} has unknown field: {sorted(unknown)[0]}")
    if missing:
        raise ConfigurationError(f"{location} is missing field: {sorted(missing)[0]}")


def _require_version(payload: Mapping[str, object], expected: str, location: str) -> None:
    actual = _string(payload["version"], f"{location}.version")
    if actual != expected:
        raise ConfigurationError(f"{location}.version must be {expected}")


def _object(value: object, location: str) -> dict[str, object]:
    if not isinstance(value, dict):
        raise ConfigurationError(f"{location} must be an object")
    return cast(dict[str, object], value)


def _list(value: object, location: str) -> list[object]:
    if not isinstance(value, list):
        raise ConfigurationError(f"{location} must be an array")
    return cast(list[object], value)


def _string(value: object, location: str) -> str:
    if not isinstance(value, str) or not value:
        raise ConfigurationError(f"{location} must be a nonempty string")
    return value


def _choice(value: object, choices: set[str] | frozenset[str], location: str) -> str:
    result = _string(value, location)
    if result not in choices:
        raise ConfigurationError(f"{location} has unsupported value: {result}")
    return result


def _optional_choice(
    value: object, choices: set[str] | frozenset[str], location: str
) -> str | None:
    if value is None:
        return None
    return _choice(value, choices, location)


def _boolean(value: object, location: str) -> bool:
    if not isinstance(value, bool):
        raise ConfigurationError(f"{location} must be a boolean")
    return value


def _positive_int(value: object, location: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise ConfigurationError(f"{location} must be a positive integer")
    return value


def _decimal_string(value: object, location: str) -> Decimal:
    if not isinstance(value, str):
        raise ConfigurationError(f"{location} must be a decimal string")
    try:
        result = Decimal(value)
    except InvalidOperation as exc:
        raise ConfigurationError(f"{location} must be a decimal string") from exc
    if not result.is_finite():
        raise ConfigurationError(f"{location} must be a finite decimal string")
    return result


def _decimal_mapping(
    value: object, expected_keys: set[str], location: str
) -> Mapping[str, Decimal]:
    raw = _object(value, location)
    _require_keys(raw, expected_keys, location)
    return _immutable_mapping(
        {key: _decimal_string(raw[key], f"{location}.{key}") for key in raw}
    )


def _string_tuple(value: object, location: str) -> tuple[str, ...]:
    return tuple(
        _string(item, f"{location}[{index}]")
        for index, item in enumerate(_list(value, location))
    )


def _date(value: object, location: str) -> date:
    raw = _string(value, location)
    try:
        return date.fromisoformat(raw)
    except ValueError as exc:
        raise ConfigurationError(f"{location} must be an ISO date") from exc


def _optional_date(value: object, location: str) -> date | None:
    if value is None:
        return None
    return _date(value, location)


def _immutable_mapping[T](values: Mapping[str, T]) -> Mapping[str, T]:
    return MappingProxyType(dict(values))
