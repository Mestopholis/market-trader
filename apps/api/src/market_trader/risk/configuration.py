from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import cast


class RiskConfigurationError(ValueError):
    """Raised when checked-in risk policy configuration is invalid."""


@dataclass(frozen=True)
class TradingWindow:
    label: str
    start: str
    end: str

    @property
    def start_minutes(self) -> int:
        return _time_to_minutes(self.start)

    @property
    def end_minutes(self) -> int:
        return _time_to_minutes(self.end)


@dataclass(frozen=True)
class RiskPolicy:
    version: str
    content_hash: str
    per_trade_risk_fraction: Decimal
    max_share_notional_fraction: Decimal
    max_spread_debit_fraction: Decimal
    max_total_reserved_risk_fraction: Decimal
    min_settled_cash_after_trade: Decimal
    contract_multiplier: Decimal
    allow_unsettled_cash: bool
    block_borrowed_buying_power: bool
    max_positions: int
    max_open_trades_per_day: int
    max_correlation_group_fraction: Decimal
    max_daily_loss_fraction: Decimal
    max_weekly_loss_fraction: Decimal
    max_drawdown_fraction: Decimal
    required_lock_types: tuple[str, ...]
    informational_lock_types: tuple[str, ...]
    blocked_trading_windows: tuple[TradingWindow, ...]
    wash_sale_window_days: int
    short_term_holding_period_days: int
    long_term_holding_period_days: int
    equivalent_symbol_groups: tuple[tuple[str, ...], ...]
    tax_disclaimer: str


_REQUIRED_KEYS = frozenset(
    {
        "allow_unsettled_cash",
        "block_borrowed_buying_power",
        "blocked_trading_windows",
        "content_hash",
        "contract_multiplier",
        "equivalent_symbol_groups",
        "informational_lock_types",
        "long_term_holding_period_days",
        "max_correlation_group_fraction",
        "max_daily_loss_fraction",
        "max_drawdown_fraction",
        "max_open_trades_per_day",
        "max_positions",
        "max_share_notional_fraction",
        "max_spread_debit_fraction",
        "max_total_reserved_risk_fraction",
        "max_weekly_loss_fraction",
        "min_settled_cash_after_trade",
        "per_trade_risk_fraction",
        "required_lock_types",
        "short_term_holding_period_days",
        "tax_disclaimer",
        "version",
        "wash_sale_window_days",
    }
)
_REQUIRED_LOCK_TYPES = frozenset({"daily_loss", "weekly_loss", "drawdown", "manual"})
_TIME_PATTERN = re.compile(r"\A(?:[01]\d|2[0-3]):[0-5]\d\Z")


def load_risk_policy(path: Path | str) -> RiskPolicy:
    try:
        raw = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise RiskConfigurationError("risk policy is malformed") from error
    if not isinstance(raw, dict):
        raise RiskConfigurationError("risk policy must be an object")

    unknown = set(raw).difference(_REQUIRED_KEYS)
    missing = _REQUIRED_KEYS.difference(raw)
    if unknown:
        raise RiskConfigurationError("unknown policy keys")
    if missing:
        raise RiskConfigurationError("missing policy keys")

    content_hash = _string(raw["content_hash"], "content_hash")
    expected_hash = _content_hash(cast(dict[str, object], raw))
    if content_hash != expected_hash:
        raise RiskConfigurationError("policy content hash does not match")

    policy = RiskPolicy(
        version=_string(raw["version"], "version"),
        content_hash=content_hash,
        per_trade_risk_fraction=_decimal(
            raw["per_trade_risk_fraction"], "per_trade_risk_fraction"
        ),
        max_share_notional_fraction=_decimal(
            raw["max_share_notional_fraction"], "max_share_notional_fraction"
        ),
        max_spread_debit_fraction=_decimal(
            raw["max_spread_debit_fraction"], "max_spread_debit_fraction"
        ),
        max_total_reserved_risk_fraction=_decimal(
            raw["max_total_reserved_risk_fraction"], "max_total_reserved_risk_fraction"
        ),
        min_settled_cash_after_trade=_decimal(
            raw["min_settled_cash_after_trade"], "min_settled_cash_after_trade"
        ),
        contract_multiplier=_decimal(raw["contract_multiplier"], "contract_multiplier"),
        allow_unsettled_cash=_boolean(raw["allow_unsettled_cash"], "allow_unsettled_cash"),
        block_borrowed_buying_power=_boolean(
            raw["block_borrowed_buying_power"], "block_borrowed_buying_power"
        ),
        max_positions=_integer(raw["max_positions"], "max_positions"),
        max_open_trades_per_day=_integer(
            raw["max_open_trades_per_day"], "max_open_trades_per_day"
        ),
        max_correlation_group_fraction=_decimal(
            raw["max_correlation_group_fraction"], "max_correlation_group_fraction"
        ),
        max_daily_loss_fraction=_decimal(
            raw["max_daily_loss_fraction"], "max_daily_loss_fraction"
        ),
        max_weekly_loss_fraction=_decimal(
            raw["max_weekly_loss_fraction"], "max_weekly_loss_fraction"
        ),
        max_drawdown_fraction=_decimal(raw["max_drawdown_fraction"], "max_drawdown_fraction"),
        required_lock_types=tuple(_strings(raw["required_lock_types"], "required_lock_types")),
        informational_lock_types=tuple(
            _strings(raw["informational_lock_types"], "informational_lock_types")
        ),
        blocked_trading_windows=tuple(
            _trading_windows(raw["blocked_trading_windows"], "blocked_trading_windows")
        ),
        wash_sale_window_days=_integer(raw["wash_sale_window_days"], "wash_sale_window_days"),
        short_term_holding_period_days=_integer(
            raw["short_term_holding_period_days"], "short_term_holding_period_days"
        ),
        long_term_holding_period_days=_integer(
            raw["long_term_holding_period_days"], "long_term_holding_period_days"
        ),
        equivalent_symbol_groups=tuple(
            _equivalent_symbol_groups(raw["equivalent_symbol_groups"])
        ),
        tax_disclaimer=_string(raw["tax_disclaimer"], "tax disclaimer"),
    )
    _validate(policy)
    return policy


def _content_hash(raw: dict[str, object]) -> str:
    payload = dict(raw)
    payload.pop("content_hash", None)
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def _validate(policy: RiskPolicy) -> None:
    if policy.version != "risk-policy-v1":
        raise RiskConfigurationError("unsupported policy version")
    for name in (
        "per_trade_risk_fraction",
        "max_share_notional_fraction",
        "max_spread_debit_fraction",
        "max_total_reserved_risk_fraction",
        "contract_multiplier",
        "max_correlation_group_fraction",
        "max_daily_loss_fraction",
        "max_weekly_loss_fraction",
        "max_drawdown_fraction",
    ):
        if getattr(policy, name) <= 0:
            raise RiskConfigurationError(f"{name} must be positive")
    if policy.min_settled_cash_after_trade < 0:
        raise RiskConfigurationError("min_settled_cash_after_trade must be non-negative")
    if policy.contract_multiplier != Decimal("100"):
        raise RiskConfigurationError("contract multiplier must be 100")
    for name in (
        "max_positions",
        "max_open_trades_per_day",
        "wash_sale_window_days",
        "short_term_holding_period_days",
        "long_term_holding_period_days",
    ):
        if getattr(policy, name) <= 0:
            raise RiskConfigurationError(f"{name} must be positive")
    if policy.long_term_holding_period_days <= policy.short_term_holding_period_days:
        raise RiskConfigurationError("holding-period windows must be ordered")
    if not _REQUIRED_LOCK_TYPES.issubset(set(policy.required_lock_types)):
        raise RiskConfigurationError("missing required lock types")
    if set(policy.required_lock_types).intersection(policy.informational_lock_types):
        raise RiskConfigurationError("lock type classifications must not overlap")
    _validate_non_overlapping_windows(policy.blocked_trading_windows)
    if "not tax advice" not in policy.tax_disclaimer.casefold():
        raise RiskConfigurationError("tax disclaimer must state this is not tax advice")


def _string(value: object, name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise RiskConfigurationError(f"{name} must be a nonempty string")
    return value


def _decimal(value: object, name: str) -> Decimal:
    if not isinstance(value, str):
        raise RiskConfigurationError(f"{name} must be a decimal string")
    try:
        parsed = Decimal(value)
    except InvalidOperation as error:
        raise RiskConfigurationError(f"{name} must be a decimal string") from error
    if not parsed.is_finite():
        raise RiskConfigurationError(f"{name} must be finite")
    return parsed


def _integer(value: object, name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise RiskConfigurationError(f"{name} must be an integer")
    return value


def _boolean(value: object, name: str) -> bool:
    if not isinstance(value, bool):
        raise RiskConfigurationError(f"{name} must be a boolean")
    return value


def _strings(value: object, name: str) -> list[str]:
    if not isinstance(value, list) or not value:
        raise RiskConfigurationError(f"{name} must be a nonempty string list")
    if not all(isinstance(item, str) and item.strip() for item in value):
        raise RiskConfigurationError(f"{name} must be a nonempty string list")
    return cast(list[str], value)


def _trading_windows(value: object, name: str) -> list[TradingWindow]:
    if not isinstance(value, list):
        raise RiskConfigurationError(f"{name} must be a list")
    windows = []
    for item in value:
        if not isinstance(item, dict) or set(item) != {"label", "start", "end"}:
            raise RiskConfigurationError(f"{name} entries must contain label, start, end")
        window = TradingWindow(
            label=_string(item["label"], "window label"),
            start=_time_string(item["start"], "window start"),
            end=_time_string(item["end"], "window end"),
        )
        if window.start_minutes >= window.end_minutes:
            raise RiskConfigurationError("trading window start must be before end")
        windows.append(window)
    return sorted(windows, key=lambda window: (window.start_minutes, window.end_minutes))


def _time_string(value: object, name: str) -> str:
    text = _string(value, name)
    if _TIME_PATTERN.fullmatch(text) is None:
        raise RiskConfigurationError(f"{name} must be HH:MM")
    return text


def _time_to_minutes(value: str) -> int:
    hour, minute = value.split(":", maxsplit=1)
    return int(hour) * 60 + int(minute)


def _validate_non_overlapping_windows(windows: tuple[TradingWindow, ...]) -> None:
    previous: TradingWindow | None = None
    for window in windows:
        if previous is not None and previous.end_minutes > window.start_minutes:
            raise RiskConfigurationError("blocked trading windows must not overlap")
        previous = window


def _equivalent_symbol_groups(value: object) -> list[tuple[str, ...]]:
    if not isinstance(value, list):
        raise RiskConfigurationError("equivalent symbol groups must be a list")
    groups = []
    for group in value:
        if not isinstance(group, list) or len(group) < 2:
            raise RiskConfigurationError(
                "equivalent symbol group must contain at least two symbols"
            )
        if not all(isinstance(symbol, str) and symbol.strip() for symbol in group):
            raise RiskConfigurationError("equivalent symbol group contains an invalid symbol")
        groups.append(tuple(sorted({symbol.upper() for symbol in group})))
    return sorted(groups, key=lambda group: group[0])
