import hashlib
import json
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import cast


class OptionsAnalysisConfigurationError(ValueError):
    pass


@dataclass(frozen=True)
class OptionsAnalysisPolicy:
    version: str
    content_hash: str
    dte_min: int
    dte_max: int
    contract_multiplier: Decimal
    cent_increment: Decimal
    require_standard_deliverable: bool
    long_delta_min: Decimal
    long_delta_max: Decimal
    short_delta_min: Decimal
    short_delta_max: Decimal
    min_open_interest: int
    min_volume: int
    max_leg_relative_width: Decimal
    max_spread_relative_width: Decimal
    pin_warning_distance: Decimal
    pin_block_distance: Decimal
    minimum_remaining_sessions: int
    ranking: tuple[str, ...]


_REQUIRED_KEYS = frozenset(
    {
        "cent_increment",
        "content_hash",
        "contract_multiplier",
        "dte_max",
        "dte_min",
        "long_delta_max",
        "long_delta_min",
        "max_leg_relative_width",
        "max_spread_relative_width",
        "min_open_interest",
        "min_volume",
        "minimum_remaining_sessions",
        "pin_block_distance",
        "pin_warning_distance",
        "ranking",
        "require_standard_deliverable",
        "short_delta_max",
        "short_delta_min",
        "version",
    }
)


def load_options_analysis_policy(path: Path | str) -> OptionsAnalysisPolicy:
    try:
        raw = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise OptionsAnalysisConfigurationError("options-analysis policy is malformed") from error
    if not isinstance(raw, dict):
        raise OptionsAnalysisConfigurationError("options-analysis policy must be an object")
    unknown = set(raw).difference(_REQUIRED_KEYS)
    missing = _REQUIRED_KEYS.difference(raw)
    if unknown:
        raise OptionsAnalysisConfigurationError("unknown policy keys")
    if missing:
        raise OptionsAnalysisConfigurationError("missing policy keys")
    expected_hash = _content_hash(raw)
    content_hash = _string(raw["content_hash"], "content_hash")
    if content_hash != expected_hash:
        raise OptionsAnalysisConfigurationError("policy content hash does not match")
    policy = OptionsAnalysisPolicy(
        version=_string(raw["version"], "version"),
        content_hash=content_hash,
        dte_min=_integer(raw["dte_min"], "dte_min"),
        dte_max=_integer(raw["dte_max"], "dte_max"),
        contract_multiplier=_decimal(raw["contract_multiplier"], "contract_multiplier"),
        cent_increment=_decimal(raw["cent_increment"], "cent_increment"),
        require_standard_deliverable=_boolean(
            raw["require_standard_deliverable"], "require_standard_deliverable"
        ),
        long_delta_min=_decimal(raw["long_delta_min"], "long_delta_min"),
        long_delta_max=_decimal(raw["long_delta_max"], "long_delta_max"),
        short_delta_min=_decimal(raw["short_delta_min"], "short_delta_min"),
        short_delta_max=_decimal(raw["short_delta_max"], "short_delta_max"),
        min_open_interest=_integer(raw["min_open_interest"], "min_open_interest"),
        min_volume=_integer(raw["min_volume"], "min_volume"),
        max_leg_relative_width=_decimal(
            raw["max_leg_relative_width"], "max_leg_relative_width"
        ),
        max_spread_relative_width=_decimal(
            raw["max_spread_relative_width"], "max_spread_relative_width"
        ),
        pin_warning_distance=_decimal(raw["pin_warning_distance"], "pin_warning_distance"),
        pin_block_distance=_decimal(raw["pin_block_distance"], "pin_block_distance"),
        minimum_remaining_sessions=_integer(
            raw["minimum_remaining_sessions"], "minimum_remaining_sessions"
        ),
        ranking=tuple(_strings(raw["ranking"], "ranking")),
    )
    _validate(policy)
    return policy


def _content_hash(raw: dict[str, object]) -> str:
    payload = dict(raw)
    payload.pop("content_hash", None)
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def _string(value: object, name: str) -> str:
    if not isinstance(value, str) or not value:
        raise OptionsAnalysisConfigurationError(f"{name} must be a nonempty string")
    return value


def _integer(value: object, name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int | str):
        raise OptionsAnalysisConfigurationError(f"{name} must be an integer")
    try:
        parsed = int(value)
    except ValueError as error:
        raise OptionsAnalysisConfigurationError(f"{name} must be an integer") from error
    if str(parsed) != str(value):
        raise OptionsAnalysisConfigurationError(f"{name} must be an integer")
    return parsed


def _decimal(value: object, name: str) -> Decimal:
    if not isinstance(value, str):
        raise OptionsAnalysisConfigurationError(f"{name} must be a decimal string")
    try:
        parsed = Decimal(value)
    except InvalidOperation as error:
        raise OptionsAnalysisConfigurationError(f"{name} must be a decimal string") from error
    if not parsed.is_finite():
        raise OptionsAnalysisConfigurationError(f"{name} must be finite")
    return parsed


def _boolean(value: object, name: str) -> bool:
    if not isinstance(value, bool):
        raise OptionsAnalysisConfigurationError(f"{name} must be a boolean")
    return value


def _strings(value: object, name: str) -> list[str]:
    if not isinstance(value, list) or not all(isinstance(item, str) and item for item in value):
        raise OptionsAnalysisConfigurationError(f"{name} must be a nonempty string list")
    return cast(list[str], value)


def _validate(policy: OptionsAnalysisPolicy) -> None:
    if policy.version != "options-analysis-policy-v1":
        raise OptionsAnalysisConfigurationError("unsupported policy version")
    if policy.dte_min != 30 or policy.dte_max != 60:
        raise OptionsAnalysisConfigurationError("policy must use 30 through 60 DTE")
    if policy.contract_multiplier != Decimal("100"):
        raise OptionsAnalysisConfigurationError("policy must use 100-share contracts")
    if not policy.require_standard_deliverable:
        raise OptionsAnalysisConfigurationError("policy must require standard deliverables")
    if not (Decimal(0) < policy.pin_block_distance < policy.pin_warning_distance):
        raise OptionsAnalysisConfigurationError("pin-risk distances are invalid")
    if not (Decimal(0) < policy.long_delta_min <= policy.long_delta_max <= Decimal(1)):
        raise OptionsAnalysisConfigurationError("long delta band is invalid")
    if not (Decimal(0) < policy.short_delta_min <= policy.short_delta_max <= Decimal(1)):
        raise OptionsAnalysisConfigurationError("short delta band is invalid")
    if policy.min_open_interest < 0 or policy.min_volume < 0:
        raise OptionsAnalysisConfigurationError("liquidity floors are invalid")
    if policy.minimum_remaining_sessions < 1:
        raise OptionsAnalysisConfigurationError("remaining sessions must be positive")
