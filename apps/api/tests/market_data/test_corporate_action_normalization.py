from datetime import UTC, date, datetime
from decimal import Decimal

import pytest

from market_trader.market_data.models import CorporateActionType, DataKind, ProviderEvent
from market_trader.market_data.normalizers import normalize_corporate_action


@pytest.mark.parametrize(
    "action_type",
    ["split", "reverse_split", "stock_dividend"],
)
def test_normalizes_share_ratio_action(action_type: str) -> None:
    result = normalize_corporate_action(
        action_event(action_type, payload_update={"share_ratio": "2"})
    )

    assert result.rejection is None
    assert result.accepted is not None
    assert result.accepted.action_type is CorporateActionType(action_type)
    assert result.accepted.share_ratio == Decimal("2")
    assert result.accepted.cash_amount is None
    assert result.accepted.effective_date == date(2026, 8, 1)
    assert result.accepted.declaration_date == date(2026, 7, 1)


def test_normalizes_cash_dividend_and_currency() -> None:
    result = normalize_corporate_action(
        action_event(
            "cash_dividend",
            payload_update={"cash_amount": "1.25", "currency": "usd"},
        )
    )

    assert result.accepted is not None
    assert result.accepted.cash_amount == Decimal("1.25")
    assert result.accepted.currency == "USD"
    assert result.accepted.share_ratio is None
    assert result.accepted.record_date == date(2026, 8, 4)
    assert result.accepted.payment_date == date(2026, 8, 15)


@pytest.mark.parametrize(
    ("action_type", "payload_update", "reason"),
    [
        ("spinoff", {}, "unsupported_action_type"),
        ("split", {"share_ratio": "0"}, "invalid_share_ratio"),
        ("split", {"share_ratio": "2", "cash_amount": "1"}, "conflicting_action_values"),
        ("cash_dividend", {"cash_amount": "0", "currency": "USD"}, "invalid_cash_amount"),
        ("cash_dividend", {"cash_amount": "1", "currency": "US"}, "invalid_currency"),
        ("cash_dividend", {"share_ratio": "2", "currency": "USD"}, "missing_cash_amount"),
        ("split", {}, "missing_share_ratio"),
        ("split", {"share_ratio": "2", "effective_date": None}, "missing_field"),
    ],
)
def test_invalid_action_is_quarantined(
    action_type: str,
    payload_update: dict[str, object],
    reason: str,
) -> None:
    result = normalize_corporate_action(action_event(action_type, payload_update=payload_update))

    assert result.accepted is None
    assert result.rejection is not None
    assert reason in result.rejection.reason_codes


def action_event(
    action_type: str,
    *,
    payload_update: dict[str, object] | None = None,
) -> ProviderEvent:
    observed = datetime(2026, 7, 17, 14, 30, tzinfo=UTC)
    payload: dict[str, object] = {
        "action_id": f"action-{action_type}",
        "symbol": "SPY",
        "action_type": action_type,
        "declaration_date": "2026-07-01",
        "effective_date": "2026-08-01",
        "record_date": "2026-08-04",
        "payment_date": "2026-08-15",
    }
    payload.update(payload_update or {})
    return ProviderEvent(
        source="fixture",
        event_id=f"event-{action_type}",
        data_kind=DataKind.CORPORATE_ACTION,
        observed_at=observed,
        ingested_at=observed,
        payload=payload,
        fixture_schema_version=1,
        configuration_version="fixture-v1",
        correlation_id="corr-1",
    )
