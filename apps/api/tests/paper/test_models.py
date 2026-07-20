from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any

import pytest
from pydantic import ValidationError

from market_trader.paper.models import (
    ApprovalCard,
    ApprovalCardState,
    LifecycleEvent,
    PaperAction,
    PaperBrokerOrder,
    PaperBrokerScenario,
    PaperOrderIntent,
    PaperOrderStatus,
    PaperOrderType,
    PaperPosition,
    PaperPositionStatus,
    PaperPreview,
)

AS_OF = datetime(2026, 7, 20, 15, 30, tzinfo=UTC)


def _approval_card(**overrides: object) -> ApprovalCard:
    values: dict[str, Any] = {
        "card_key": "approval-card:candidate-aapl",
        "state": ApprovalCardState.READY,
        "candidate_key": "candidate:aapl",
        "symbol": "aapl",
        "direction": "bullish",
        "proposal_kind": "shares",
        "quantity": 3,
        "limit_price": Decimal("185.25"),
        "maximum_loss": Decimal("150.00"),
        "risk_decision_key": "risk:aapl:approved",
        "risk_status": "approved",
        "risk_input_digest": "a" * 64,
        "risk_result_digest": "b" * 64,
        "source_keys": ("risk:aapl", "scanner:aapl"),
        "allowed_actions": (PaperAction.APPROVE, PaperAction.MODIFY, PaperAction.REJECT),
        "expires_at": AS_OF + timedelta(minutes=5),
        "as_of": AS_OF,
        "warnings": ("Review spread liquidity",),
    }
    values.update(overrides)
    return ApprovalCard(**values)


def _order_intent(**overrides: object) -> PaperOrderIntent:
    values: dict[str, Any] = {
        "intent_key": "paper-intent:approval-1",
        "approval_id": "approval:1",
        "proposed_trade_id": "proposed:1",
        "risk_decision_key": "risk:aapl:approved",
        "symbol": "aapl",
        "side": "buy",
        "order_type": PaperOrderType.LIMIT,
        "quantity": 3,
        "limit_price": Decimal("185.25"),
        "time_in_force": "day",
        "source_keys": ("approval:1", "risk:aapl"),
        "correlation_id": "corr:paper:1",
        "created_at": AS_OF,
        "payload": {"scenario": PaperBrokerScenario.FULL_FILL.value},
    }
    values.update(overrides)
    return PaperOrderIntent(**values)


def _preview(**overrides: object) -> PaperPreview:
    values: dict[str, Any] = {
        "preview_key": "paper-preview:approval-1",
        "approval_id": "approval:1",
        "intent_key": "paper-intent:approval-1",
        "quote_observed_at": AS_OF,
        "quote_expires_at": AS_OF + timedelta(seconds=30),
        "bid": Decimal("185.20"),
        "ask": Decimal("185.30"),
        "limit_price": Decimal("185.25"),
        "estimated_maximum_loss": Decimal("150.00"),
        "reserved_risk": Decimal("150.00"),
        "warnings": ("Paper preview only",),
        "preview_digest": "c" * 64,
        "source_keys": ("quote:aapl", "risk:aapl"),
        "as_of": AS_OF,
    }
    values.update(overrides)
    return PaperPreview(**values)


def test_approval_card_normalizes_traceability_and_actions() -> None:
    card = _approval_card(source_keys=("scanner:aapl", "risk:aapl", "risk:aapl"))

    assert card.symbol == "AAPL"
    assert card.source_keys == ("risk:aapl", "scanner:aapl")
    assert card.allowed_actions == (
        PaperAction.APPROVE,
        PaperAction.MODIFY,
        PaperAction.REJECT,
    )
    assert card.expires_at.tzinfo is UTC
    assert card.paper_mode is True


def test_order_intent_is_limit_only_and_rejects_live_or_broker_payloads() -> None:
    intent = _order_intent()

    assert intent.symbol == "AAPL"
    assert intent.order_type is PaperOrderType.LIMIT
    assert intent.quantity == 3

    with pytest.raises(ValidationError, match="limit orders only"):
        _order_intent(order_type="market")

    for unsafe_payload in (
        {"live_mode": True},
        {"schwab_account_id": "123"},
        {"broker": {"credential": "secret"}},
        {"token": "not-safe"},
    ):
        with pytest.raises(ValidationError, match="paper lifecycle payload contains forbidden key"):
            _order_intent(payload=unsafe_payload)


def test_models_reject_bad_numbers_and_naive_timestamps() -> None:
    with pytest.raises(ValidationError, match="quantity must be positive"):
        _approval_card(quantity=0)

    with pytest.raises(ValidationError, match="price must be finite"):
        _order_intent(limit_price=Decimal("NaN"))

    with pytest.raises(ValidationError, match="datetime must be timezone-aware"):
        _preview(quote_observed_at=datetime(2026, 7, 20, 15, 30))

    with pytest.raises(ValidationError, match="maximum loss must be non-negative"):
        _approval_card(maximum_loss=Decimal("-1.00"))


def test_preview_bounds_warnings_and_sorts_sources() -> None:
    preview = _preview(
        warnings=("x" * 260,),
        source_keys=("risk:aapl", "quote:aapl", "quote:aapl"),
    )

    assert preview.warnings == ("x" * 200,)
    assert preview.source_keys == ("quote:aapl", "risk:aapl")
    assert preview.bid == Decimal("185.20")


def test_broker_order_and_lifecycle_event_contracts() -> None:
    order = PaperBrokerOrder(
        order_id="order:1",
        intent_key="paper-intent:approval-1",
        status=PaperOrderStatus.PARTIALLY_FILLED,
        scenario=PaperBrokerScenario.PARTIAL_FILL,
        requested_quantity=3,
        filled_quantity=1,
        remaining_quantity=2,
        limit_price=Decimal("185.25"),
        average_fill_price=Decimal("185.24"),
        simulated_broker_reference="sim:order:1",
        correlation_id="corr:paper:1",
        source_keys=("approval:1", "risk:aapl"),
        created_at=AS_OF,
        updated_at=AS_OF + timedelta(seconds=2),
        terminal_at=None,
    )
    event = LifecycleEvent(
        event_key="paper-event:order-1:partial-fill",
        event_type="paper_order.partially_filled",
        subject_type="paper_order",
        subject_id=order.order_id,
        occurred_at=AS_OF + timedelta(seconds=2),
        correlation_id=order.correlation_id,
        source_keys=("order:1", "risk:aapl"),
        payload={"status": order.status.value, "simulated_broker_reference": "sim:order:1"},
    )

    assert order.filled_quantity == 1
    assert order.remaining_quantity == 2
    assert order.broker_reference is None
    assert event.payload["status"] == "partially_filled"


def test_position_contract_tracks_paper_state_without_external_broker_reference() -> None:
    position = PaperPosition(
        position_key="position:aapl",
        symbol="aapl",
        status=PaperPositionStatus.OPEN,
        quantity=3,
        average_price=Decimal("185.24"),
        realized_pl=Decimal("0.00"),
        unrealized_pl=Decimal("12.50"),
        source_order_ids=("order:1",),
        source_fill_ids=("fill:1",),
        risk_decision_key="risk:aapl:approved",
        opened_at=AS_OF,
        updated_at=AS_OF + timedelta(minutes=1),
        closed_at=None,
        exit_rules={"technical_stop": "180.00", "profit_target": "195.00"},
    )

    assert position.symbol == "AAPL"
    assert position.status is PaperPositionStatus.OPEN
    assert position.broker_reference is None
    assert position.exit_rules["technical_stop"] == "180.00"


def test_payload_depth_and_text_are_bounded() -> None:
    with pytest.raises(ValidationError, match="payload text is too long"):
        LifecycleEvent(
            event_key="paper-event:bad",
            event_type="paper_order.rejected",
            subject_type="paper_order",
            subject_id="order:1",
            occurred_at=AS_OF,
            correlation_id="corr:paper:1",
            source_keys=("order:1",),
            payload={"reason": "x" * 501},
        )

    with pytest.raises(ValidationError, match="payload nesting is too deep"):
        LifecycleEvent(
            event_key="paper-event:deep",
            event_type="paper_order.rejected",
            subject_type="paper_order",
            subject_id="order:1",
            occurred_at=AS_OF,
            correlation_id="corr:paper:1",
            source_keys=("order:1",),
            payload={"a": {"b": {"c": {"d": {"e": "too deep"}}}}},
        )
