from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

import pytest

from market_trader.broker.schwab.order_contracts import (
    SchwabContractLeg,
    SchwabOrderContractError,
    SchwabOrderContractRequest,
    build_schwab_validation_contract,
)
from market_trader.paper.models import PaperOrderIntent, PaperOrderType

NOW = datetime(2026, 7, 28, 15, 0, tzinfo=UTC)


def test_builds_long_share_limit_contract_without_submission_fields() -> None:
    contract = build_schwab_validation_contract(
        SchwabOrderContractRequest(strategy="shares", intent=_intent())
    )

    assert contract.strategy == "shares"
    assert contract.validation_only is True
    assert contract.submit_capable is False
    assert contract.payload == {
        "orderType": "LIMIT",
        "session": "NORMAL",
        "duration": "DAY",
        "price": "123.45",
        "orderStrategyType": "SINGLE",
        "orderLegCollection": [
            {
                "instruction": "BUY",
                "quantity": 3,
                "instrument": {"assetType": "EQUITY", "symbol": "MSFT"},
            }
        ],
    }
    serialized = contract.model_dump_json()
    assert "account" not in serialized.lower()
    assert "place_order" not in serialized.lower()
    assert "secret" not in serialized.lower()
    assert "token" not in serialized.lower()


def test_builds_vertical_debit_spread_contract_with_two_option_legs() -> None:
    contract = build_schwab_validation_contract(
        SchwabOrderContractRequest(
            strategy="bull_call",
            intent=_intent(symbol="SPY", quantity=1, limit_price=Decimal("2.10")),
            legs=(
                SchwabContractLeg(
                    symbol="SPY  260821C00650000",
                    instruction="BUY_TO_OPEN",
                    asset_type="OPTION",
                    quantity=1,
                ),
                SchwabContractLeg(
                    symbol="SPY  260821C00655000",
                    instruction="SELL_TO_OPEN",
                    asset_type="OPTION",
                    quantity=1,
                ),
            ),
        )
    )

    assert contract.strategy == "bull_call"
    assert contract.payload["orderStrategyType"] == "SINGLE"
    assert contract.payload["complexOrderStrategyType"] == "VERTICAL"
    assert contract.payload["orderLegCollection"] == [
        {
            "instruction": "BUY_TO_OPEN",
            "quantity": 1,
            "instrument": {"assetType": "OPTION", "symbol": "SPY  260821C00650000"},
        },
        {
            "instruction": "SELL_TO_OPEN",
            "quantity": 1,
            "instrument": {"assetType": "OPTION", "symbol": "SPY  260821C00655000"},
        },
    ]


@pytest.mark.parametrize("strategy", ["credit_spread", "naked_option", "short_shares"])
def test_rejects_unsupported_contract_strategies(strategy: str) -> None:
    with pytest.raises(SchwabOrderContractError, match="unsupported_strategy"):
        build_schwab_validation_contract(
            SchwabOrderContractRequest(strategy=strategy, intent=_intent())
        )


def test_rejects_live_submission_fields_in_contract_request() -> None:
    with pytest.raises(SchwabOrderContractError, match="live_submission_forbidden"):
        build_schwab_validation_contract(
            SchwabOrderContractRequest(
                strategy="shares",
                intent=_intent(
                    payload={
                        "schema_version": 1,
                        "submit": True,
                    }
                ),
            )
        )


def _intent(
    *,
    symbol: str = "MSFT",
    quantity: int = 3,
    limit_price: Decimal = Decimal("123.45"),
    payload: dict[str, object] | None = None,
) -> PaperOrderIntent:
    return PaperOrderIntent(
        intent_key="intent-a",
        approval_id="approval-a",
        proposed_trade_id="proposed-a",
        risk_decision_key="risk-a",
        symbol=symbol,
        side="buy",
        order_type=PaperOrderType.LIMIT,
        quantity=quantity,
        limit_price=limit_price,
        time_in_force="day",
        source_keys=("approval:approval-a",),
        correlation_id="corr-a",
        created_at=NOW,
        payload=payload or {"schema_version": 1},
    )
