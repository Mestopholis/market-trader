from dataclasses import dataclass
from decimal import Decimal

from market_trader.options_analysis.serialization import canonical_record, stable_digest


@dataclass(frozen=True)
class _CanonicalValue:
    amount: Decimal
    labels: tuple[str, ...]


def test_canonical_record_sorts_mapping_keys_and_encodes_decimal_as_string() -> None:
    record = canonical_record(
        {"z": Decimal("1.20"), "a": _CanonicalValue(Decimal("2"), ("b", "a"))}
    )

    assert record == {
        "a": {"amount": "2", "labels": ["b", "a"]},
        "z": "1.20",
    }


def test_stable_digest_is_independent_of_mapping_order() -> None:
    left = {"candidate": "cand-1", "price": Decimal("4.25")}
    right = {"price": Decimal("4.25"), "candidate": "cand-1"}

    assert stable_digest(left) == stable_digest(right)
