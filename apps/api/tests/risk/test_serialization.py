from datetime import UTC, datetime
from decimal import Decimal

from market_trader.risk.models import (
    BuyingPowerSnapshot,
    RiskInput,
    ShareProposal,
)
from market_trader.risk.serialization import canonical_record, stable_digest, stable_key

AS_OF = datetime(2026, 7, 20, 15, 30, tzinfo=UTC)


def _risk_input(
    *,
    entry_price: Decimal = Decimal("200.00"),
    policy_hash: str = "abc123",
    display_note: str = "display one",
) -> RiskInput:
    return RiskInput(
        decision_key="risk:input:1",
        proposal=ShareProposal(
            proposal_key="proposal:shares:aapl",
            symbol="AAPL",
            entry_price=entry_price,
            stop_price=Decimal("190.00"),
            direction="long",
            display_note="proposal display text",
        ),
        buying_power=BuyingPowerSnapshot(
            settled_cash=Decimal("5000.00"),
            unsettled_cash=Decimal("0.00"),
            reserved_cash=Decimal("0.00"),
            observed_at=AS_OF,
            snapshot_digest="bp-digest",
        ),
        positions=(),
        working_orders=(),
        locks=(),
        open_tax_lots=(),
        closed_trade_lots=(),
        policy_version="risk-policy-v1",
        policy_hash=policy_hash,
        as_of=AS_OF,
        display_note=display_note,
    )


def test_canonical_record_sorts_nested_mappings_and_preserves_decimal_strings() -> None:
    record = canonical_record({"b": Decimal("1.20"), "a": {"z": 1, "c": Decimal("2.00")}})

    assert list(record.keys()) == ["a", "b"]  # type: ignore[attr-defined]
    assert record["a"] == {"c": "2.00", "z": 1}  # type: ignore[index]
    assert record["b"] == "1.20"  # type: ignore[index]


def test_stable_digest_excludes_display_fields_from_identity() -> None:
    digest_one = stable_digest(_risk_input(display_note="display one"))
    digest_two = stable_digest(_risk_input(display_note="display two"))

    assert digest_one == digest_two


def test_stable_digest_changes_for_prices_and_policy_hashes() -> None:
    baseline = stable_digest(_risk_input())

    assert stable_digest(_risk_input(entry_price=Decimal("200.01"))) != baseline
    assert stable_digest(_risk_input(policy_hash="different-hash")) != baseline


def test_stable_key_is_ordered_sha256_identity() -> None:
    assert stable_key("risk", "AAPL", "risk-policy-v1") == stable_key(
        "risk",
        "AAPL",
        "risk-policy-v1",
    )
    assert stable_key("risk", "AAPL", "risk-policy-v1") != stable_key(
        "risk-policy-v1",
        "AAPL",
        "risk",
    )
