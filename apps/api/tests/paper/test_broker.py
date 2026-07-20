from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path

from market_trader.paper.broker import DeterministicPaperBroker
from market_trader.paper.models import (
    PaperBrokerScenario,
    PaperOrderIntent,
    PaperOrderStatus,
    PaperOrderType,
    PaperPositionStatus,
    PaperPreview,
)

AS_OF = datetime(2026, 7, 20, 15, 30, tzinfo=UTC)


def test_broker_executes_all_scenarios_deterministically() -> None:
    broker = DeterministicPaperBroker()
    intent = _intent()
    preview = _preview(intent)

    first = {
        scenario: broker.execute(intent=intent, preview=preview, scenario=scenario, as_of=AS_OF)
        for scenario in PaperBrokerScenario
    }
    second = {
        scenario: broker.execute(intent=intent, preview=preview, scenario=scenario, as_of=AS_OF)
        for scenario in PaperBrokerScenario
    }

    assert first == second
    assert first[PaperBrokerScenario.ACCEPTED_UNFILLED].order.status is PaperOrderStatus.WORKING
    assert first[PaperBrokerScenario.ACCEPTED_UNFILLED].order.filled_quantity == 0
    assert first[PaperBrokerScenario.FULL_FILL].order.status is PaperOrderStatus.FILLED
    assert first[PaperBrokerScenario.FULL_FILL].order.filled_quantity == 4
    assert first[PaperBrokerScenario.PARTIAL_FILL].order.status is PaperOrderStatus.PARTIALLY_FILLED
    assert first[PaperBrokerScenario.PARTIAL_FILL].order.filled_quantity == 2
    assert first[PaperBrokerScenario.REJECT].order.status is PaperOrderStatus.REJECTED
    assert first[PaperBrokerScenario.CANCEL].order.status is PaperOrderStatus.CANCELED
    assert first[PaperBrokerScenario.CANCEL_REPLACE].order.status is PaperOrderStatus.REPLACED
    assert first[PaperBrokerScenario.TIMEOUT].order.status is PaperOrderStatus.TIMED_OUT
    assigned_position = first[PaperBrokerScenario.ASSIGNMENT].position
    assert assigned_position is not None
    assert assigned_position.status is PaperPositionStatus.ASSIGNED


def test_broker_uses_stable_references_fill_prices_and_utc_events() -> None:
    result = DeterministicPaperBroker().execute(
        intent=_intent(side="sell"),
        preview=_preview(_intent(side="sell")),
        scenario=PaperBrokerScenario.FULL_FILL,
        as_of=AS_OF,
    )

    assert result.order.order_id == "paper-order-intent-1-full_fill"
    assert result.order.simulated_broker_reference == "sim-paper-order-intent-1-full_fill"
    assert result.order.broker_reference is None
    assert result.order.average_fill_price == Decimal("1.10")
    assert result.events
    assert all(event.occurred_at.tzinfo is UTC for event in result.events)
    assert all(event.correlation_id == "corr-paper" for event in result.events)
    assert all(
        event.payload["source_order_id"] == "paper-order-intent-1-full_fill"
        for event in result.events
    )
    assert all(
        event.payload["simulated_broker_reference"] == "sim-paper-order-intent-1-full_fill"
        for event in result.events
    )


def test_broker_bounds_reason_codes() -> None:
    result = DeterministicPaperBroker().execute(
        intent=_intent(),
        preview=_preview(_intent()),
        scenario=PaperBrokerScenario.REJECT,
        as_of=AS_OF,
    )

    reason_codes: list[str] = []
    for event in result.events:
        raw_reason_codes = event.payload.get("reason_codes", [])
        if isinstance(raw_reason_codes, list):
            reason_codes.extend(code for code in raw_reason_codes if isinstance(code, str))
    assert reason_codes == ["paper_reject"]
    assert all(len(code) <= 64 for code in reason_codes)


def test_broker_has_no_randomness_or_network_imports() -> None:
    source = Path("src/market_trader/paper/broker.py").read_text()

    assert "random" not in source
    assert "requests" not in source
    assert "httpx" not in source
    assert "socket" not in source
    assert "urllib" not in source


def _intent(*, side: str = "buy") -> PaperOrderIntent:
    return PaperOrderIntent(
        intent_key="intent-1",
        approval_id="approval-1",
        proposed_trade_id="proposed-1",
        risk_decision_key="risk-1",
        symbol="MSFT",
        side=side,
        order_type=PaperOrderType.LIMIT,
        quantity=4,
        limit_price=Decimal("1.20"),
        time_in_force="day",
        source_keys=("approval:approval-1", "risk_decision:risk-1"),
        correlation_id="corr-paper",
        created_at=AS_OF,
        payload={"schema_version": 1},
    )


def _preview(intent: PaperOrderIntent) -> PaperPreview:
    return PaperPreview(
        preview_key="preview-1",
        approval_id=intent.approval_id,
        intent_key=intent.intent_key,
        quote_observed_at=AS_OF,
        quote_expires_at=AS_OF + timedelta(minutes=1),
        bid=Decimal("1.10"),
        ask=Decimal("1.30"),
        limit_price=intent.limit_price,
        estimated_maximum_loss=Decimal("480.00"),
        reserved_risk=Decimal("480.00"),
        warnings=(),
        preview_digest="preview-digest-1",
        source_keys=("preview:preview-1",),
        as_of=AS_OF,
    )
