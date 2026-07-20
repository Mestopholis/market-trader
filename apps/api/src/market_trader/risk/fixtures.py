from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from pathlib import Path
from typing import Any, cast

from market_trader.risk.models import (
    BuyingPowerSnapshot,
    ClosedTradeLot,
    DebitSpreadProposal,
    PortfolioPosition,
    RiskDecisionStatus,
    RiskInput,
    RiskLockSnapshot,
    ShareProposal,
    TaxLot,
    WorkingOrderRisk,
)


class RiskFixtureError(ValueError):
    pass


@dataclass(frozen=True)
class RiskFixture:
    schema_version: int
    fixture_key: str
    group: str
    case_name: str
    content_hash: str
    policy_path: Path
    risk_input: RiskInput
    expected_status: RiskDecisionStatus


_REQUIRED_KEYS = frozenset(
    {
        "case_name",
        "content_hash",
        "expected_status",
        "fixture_key",
        "group",
        "input",
        "policy_path",
        "schema_version",
    }
)
_SENSITIVE_FRAGMENTS = (
    "broker",
    "cookie",
    "password",
    "secret",
    "token",
)


def load_risk_fixture(path: Path | str) -> RiskFixture:
    raw = _read_json(path)
    unknown = set(raw).difference(_REQUIRED_KEYS)
    missing = _REQUIRED_KEYS.difference(raw)
    if unknown:
        raise RiskFixtureError("unknown fixture keys")
    if missing:
        raise RiskFixtureError("missing fixture keys")
    if _content_hash(raw) != _string(raw["content_hash"], "content_hash"):
        raise RiskFixtureError("fixture content hash does not match")
    _reject_sensitive_keys(raw)
    schema_version = _integer(raw["schema_version"], "schema_version")
    if schema_version != 1:
        raise RiskFixtureError("unsupported fixture schema version")
    return RiskFixture(
        schema_version=schema_version,
        fixture_key=_string(raw["fixture_key"], "fixture_key"),
        group=_string(raw["group"], "group"),
        case_name=_string(raw["case_name"], "case_name"),
        content_hash=_string(raw["content_hash"], "content_hash"),
        policy_path=Path(_string(raw["policy_path"], "policy_path")),
        risk_input=_risk_input(_object(raw["input"], "input")),
        expected_status=RiskDecisionStatus(_string(raw["expected_status"], "expected_status")),
    )


def _read_json(path: Path | str) -> dict[str, object]:
    try:
        raw = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise RiskFixtureError("risk fixture is malformed") from error
    if not isinstance(raw, dict):
        raise RiskFixtureError("risk fixture must be an object")
    return cast(dict[str, object], raw)


def _content_hash(raw: Mapping[str, object]) -> str:
    payload = dict(raw)
    payload.pop("content_hash", None)
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def _reject_sensitive_keys(value: object, path: str = "") -> None:
    if isinstance(value, Mapping):
        for key, item in value.items():
            normalized = str(key).casefold().replace("-", "_")
            if any(fragment in normalized for fragment in _SENSITIVE_FRAGMENTS):
                raise RiskFixtureError(f"sensitive fixture key rejected: {path}{key}")
            _reject_sensitive_keys(item, f"{path}{key}.")
    elif isinstance(value, list):
        for index, item in enumerate(value):
            _reject_sensitive_keys(item, f"{path}{index}.")


def _risk_input(raw: Mapping[str, object]) -> RiskInput:
    return RiskInput(
        decision_key=_string(raw["decision_key"], "decision_key"),
        proposal=_proposal(_object(raw["proposal"], "proposal")),
        buying_power=_buying_power(_object(raw["buying_power"], "buying_power")),
        positions=tuple(_position(item) for item in _objects(raw["positions"], "positions")),
        working_orders=tuple(
            _working_order(item) for item in _objects(raw["working_orders"], "working_orders")
        ),
        locks=tuple(_lock(item) for item in _objects(raw["locks"], "locks")),
        open_tax_lots=tuple(
            _tax_lot(item) for item in _objects(raw["open_tax_lots"], "open_tax_lots")
        ),
        closed_trade_lots=tuple(
            _closed_lot(item) for item in _objects(raw["closed_trade_lots"], "closed_trade_lots")
        ),
        policy_version=_string(raw["policy_version"], "policy_version"),
        policy_hash=_string(raw["policy_hash"], "policy_hash"),
        as_of=_datetime(raw["as_of"], "as_of"),
        account_equity=_decimal(raw.get("account_equity", "0.00"), "account_equity"),
        daily_realized_loss=_decimal(
            raw.get("daily_realized_loss", "0.00"), "daily_realized_loss"
        ),
        weekly_realized_loss=_decimal(
            raw.get("weekly_realized_loss", "0.00"), "weekly_realized_loss"
        ),
        peak_equity=_decimal(raw["peak_equity"], "peak_equity")
        if raw.get("peak_equity") is not None
        else None,
        open_trades_today=_integer(raw.get("open_trades_today", 0), "open_trades_today"),
    )


def _proposal(raw: Mapping[str, object]) -> ShareProposal | DebitSpreadProposal:
    if "long_contract_id" in raw:
        return DebitSpreadProposal(
            proposal_key=_string(raw["proposal_key"], "proposal_key"),
            symbol=_string(raw["symbol"], "symbol"),
            long_contract_id=_string(raw["long_contract_id"], "long_contract_id"),
            short_contract_id=_string(raw["short_contract_id"], "short_contract_id"),
            expiration=_datetime(raw["expiration"], "expiration"),
            debit=_decimal(raw["debit"], "debit"),
            maximum_loss=_decimal(raw["maximum_loss"], "maximum_loss"),
            short_strike=_decimal(raw["short_strike"], "short_strike"),
            contracts=_integer(raw.get("contracts", 1), "contracts"),
        )
    return ShareProposal(
        proposal_key=_string(raw["proposal_key"], "proposal_key"),
        symbol=_string(raw["symbol"], "symbol"),
        entry_price=_decimal(raw["entry_price"], "entry_price"),
        stop_price=_decimal(raw["stop_price"], "stop_price"),
        direction=cast(Any, _string(raw["direction"], "direction")),
    )


def _buying_power(raw: Mapping[str, object]) -> BuyingPowerSnapshot:
    return BuyingPowerSnapshot(
        settled_cash=_decimal(raw["settled_cash"], "settled_cash"),
        unsettled_cash=_decimal(raw["unsettled_cash"], "unsettled_cash"),
        reserved_cash=_decimal(raw["reserved_cash"], "reserved_cash"),
        observed_at=_datetime(raw["observed_at"], "observed_at"),
        snapshot_digest=_string(raw["snapshot_digest"], "snapshot_digest"),
        borrowed_buying_power=_decimal(
            raw.get("borrowed_buying_power", "0.00"), "borrowed_buying_power"
        ),
    )


def _position(raw: Mapping[str, object]) -> PortfolioPosition:
    return PortfolioPosition(
        position_key=_string(raw["position_key"], "position_key"),
        symbol=_string(raw["symbol"], "symbol"),
        quantity=_integer(raw["quantity"], "quantity"),
        market_value=_decimal(raw["market_value"], "market_value"),
        maximum_loss=_decimal(raw["maximum_loss"], "maximum_loss"),
        correlation_group=_string(raw["correlation_group"], "correlation_group"),
    )


def _working_order(raw: Mapping[str, object]) -> WorkingOrderRisk:
    return WorkingOrderRisk(
        order_key=_string(raw["order_key"], "order_key"),
        symbol=_string(raw["symbol"], "symbol"),
        reserved_risk=_decimal(raw["reserved_risk"], "reserved_risk"),
        assignment_stress=_decimal(raw["assignment_stress"], "assignment_stress"),
        correlation_group=_string(raw["correlation_group"], "correlation_group"),
    )


def _lock(raw: Mapping[str, object]) -> RiskLockSnapshot:
    return RiskLockSnapshot(
        lock_id=_string(raw["lock_id"], "lock_id"),
        lock_type=_string(raw["lock_type"], "lock_type"),
        status=_string(raw["status"], "status"),
        reason=_string(raw["reason"], "reason"),
        activated_at=_datetime(raw["activated_at"], "activated_at"),
        source_event_id=_string(raw["source_event_id"], "source_event_id"),
    )


def _tax_lot(raw: Mapping[str, object]) -> TaxLot:
    return TaxLot(
        lot_key=_string(raw["lot_key"], "lot_key"),
        symbol=_string(raw["symbol"], "symbol"),
        opened_at=_datetime(raw["opened_at"], "opened_at"),
        quantity=_integer(raw["quantity"], "quantity"),
        cost_basis=_decimal(raw["cost_basis"], "cost_basis"),
        account_taxable=_boolean(raw["account_taxable"], "account_taxable"),
    )


def _closed_lot(raw: Mapping[str, object]) -> ClosedTradeLot:
    return ClosedTradeLot(
        lot_key=_string(raw["lot_key"], "lot_key"),
        symbol=_string(raw["symbol"], "symbol"),
        closed_at=_datetime(raw["closed_at"], "closed_at"),
        quantity=_integer(raw["quantity"], "quantity"),
        realized_pl=_decimal(raw["realized_pl"], "realized_pl"),
        loss_amount=_decimal(raw["loss_amount"], "loss_amount"),
        account_taxable=_boolean(raw["account_taxable"], "account_taxable"),
    )


def _object(value: object, name: str) -> Mapping[str, object]:
    if not isinstance(value, Mapping):
        raise RiskFixtureError(f"{name} must be an object")
    return cast(Mapping[str, object], value)


def _objects(value: object, name: str) -> list[Mapping[str, object]]:
    if not isinstance(value, list) or not all(isinstance(item, Mapping) for item in value):
        raise RiskFixtureError(f"{name} must be an object list")
    return cast(list[Mapping[str, object]], value)


def _string(value: object, name: str) -> str:
    if not isinstance(value, str) or not value:
        raise RiskFixtureError(f"{name} must be a nonempty string")
    return value


def _integer(value: object, name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise RiskFixtureError(f"{name} must be an integer")
    return value


def _boolean(value: object, name: str) -> bool:
    if not isinstance(value, bool):
        raise RiskFixtureError(f"{name} must be a boolean")
    return value


def _decimal(value: object, name: str) -> Decimal:
    if not isinstance(value, str):
        raise RiskFixtureError(f"{name} must be a decimal string")
    parsed = Decimal(value)
    if not parsed.is_finite():
        raise RiskFixtureError(f"{name} must be finite")
    return parsed


def _datetime(value: object, name: str) -> datetime:
    return datetime.fromisoformat(_string(value, name))
