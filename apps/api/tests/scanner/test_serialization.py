from datetime import UTC, date, datetime, timedelta, timezone
from decimal import Decimal

from market_trader.market_data.sanitization import (
    MAX_COLLECTION_ITEMS,
    MAX_STRING_LENGTH,
    canonical_json,
)
from market_trader.scanner.models import (
    Direction,
    EvidenceRef,
    FeatureSet,
    GateResult,
    PolicyVersions,
    ScannerInput,
    StrategyResult,
    StrategyStatus,
    SymbolInput,
)
from market_trader.scanner.serialization import canonical_record, stable_digest

AS_OF = datetime(2026, 7, 17, 15, 30, tzinfo=UTC)


def _reference(lineage: str, minute: int) -> EvidenceRef:
    observed_at = AS_OF - timedelta(minutes=minute)
    return EvidenceRef(
        lineage_id=lineage,
        source="fixture",
        event_id=f"event-{lineage}",
        ingestion_key=f"ing-{lineage}",
        payload_digest=str(minute) * 64,
        observed_at=observed_at,
        ingested_at=observed_at + timedelta(seconds=1),
    )


def test_differently_ordered_inputs_have_identical_json_and_digest() -> None:
    left = ScannerInput(
        as_of=AS_OF,
        session_date=date(2026, 7, 17),
        versions=PolicyVersions(),
        symbols=(
            SymbolInput(symbol="SPY", evidence=(_reference("z", 2), _reference("a", 1))),
            SymbolInput(symbol="AAPL", attributes={"role": "candidate", "exchange": "XNYS"}),
        ),
        supplemental_evidence=(_reference("macro-z", 4), _reference("breadth-a", 3)),
        configuration_hashes={"universe": "u", "scoring": "s"},
    )
    right = ScannerInput(
        as_of=AS_OF.astimezone(timezone(timedelta(hours=-5))),
        session_date=date(2026, 7, 17),
        versions=PolicyVersions(),
        symbols=(
            SymbolInput(symbol="AAPL", attributes={"exchange": "XNYS", "role": "candidate"}),
            SymbolInput(symbol="SPY", evidence=(_reference("a", 1), _reference("z", 2))),
        ),
        supplemental_evidence=(_reference("breadth-a", 3), _reference("macro-z", 4)),
        configuration_hashes={"scoring": "s", "universe": "u"},
    )

    left_record = canonical_record(left)
    right_record = canonical_record(right)

    assert canonical_json(left_record) == canonical_json(right_record)
    assert stable_digest(left) == stable_digest(right)
    assert len(stable_digest(left)) == 64


def test_serialization_uses_enum_values_and_six_decimal_scores() -> None:
    strategy = StrategyResult(
        signal_key="signal-1",
        symbol="SPY",
        strategy_id="bullish_breakout",
        policy_version="scanner-strategies-v1",
        direction=Direction.BULLISH,
        status=StrategyStatus.PASSED,
        score=Decimal("70"),
        gates=(GateResult(name="trigger", passed=True),),
    )

    record = canonical_record(strategy)

    assert isinstance(record, dict)
    assert record["direction"] == "bullish"
    assert record["status"] == "passed"
    assert record["score"] == "70.000000"


def test_serialization_sorts_mapping_keys_reasons_and_feature_values() -> None:
    features = FeatureSet(
        symbol="SPY",
        values={"z_value": Decimal("2.5"), "a_value": 3},
        reasons=("z_reason", "a_reason", "z_reason"),
        lineage=("lineage-z", "lineage-a"),
    )

    assert canonical_json(canonical_record(features)) == (
        '{"lineage":["lineage-a","lineage-z"],'
        '"reasons":["a_reason","z_reason"],"symbol":"SPY",'
        '"values":{"a_value":3,"z_value":"2.5"}}'
    )


def test_canonical_record_applies_sensitive_key_redaction() -> None:
    record = canonical_record(
        {
            "authorization": "Bearer secret",
            "nested": {"api_key": "secret-key", "safe": "visible"},
        }
    )

    assert record == {
        "authorization": "[REDACTED]",
        "nested": {"api_key": "[REDACTED]", "safe": "visible"},
    }


def test_canonical_record_bounds_long_strings_and_collections() -> None:
    record = canonical_record(
        {
            "description": "x" * (MAX_STRING_LENGTH + 1),
            "items": list(range(MAX_COLLECTION_ITEMS + 1)),
        }
    )

    assert isinstance(record, dict)
    assert record["description"] == "x" * MAX_STRING_LENGTH
    assert isinstance(record["items"], list)
    assert len(record["items"]) == MAX_COLLECTION_ITEMS
