from datetime import UTC, datetime, timedelta, timezone
from decimal import Decimal

from market_trader.catalysts.models import CatalystProviderEvent, EventFamily
from market_trader.catalysts.serialization import canonical_record, stable_digest
from market_trader.market_data.sanitization import canonical_json

AS_OF = datetime(2026, 7, 17, 15, 30, tzinfo=UTC)


def _event(*, reverse: bool, local_time: bool = False) -> CatalystProviderEvent:
    structured = (
        {"consensus": Decimal("1.20"), "actual": Decimal("1.25")}
        if reverse
        else {"actual": Decimal("1.25"), "consensus": Decimal("1.20")}
    )
    published_at = (
        AS_OF.astimezone(timezone(-timedelta(hours=5))) if local_time else AS_OF
    )
    return CatalystProviderEvent(
        source_id="recorded-earnings-v1",
        provider_event_id="earnings-aapl-2026-q2",
        event_family=EventFamily.EARNINGS,
        provider_schema_version=1,
        published_at=published_at,
        ingested_at=published_at,
        scheduled_for=None,
        symbol_identity="AAPL",
        structured_fields=structured,
        external_text={"headline": "Synthetic result"},
        source_reference="fixture://earnings/aapl-2026-q2",
        correlation_id="corr-1",
    )


def test_differently_ordered_inputs_have_identical_json_and_digest() -> None:
    left = _event(reverse=False)
    right = _event(reverse=True, local_time=True)

    assert canonical_json(canonical_record(left)) == canonical_json(canonical_record(right))
    assert stable_digest(left) == stable_digest(right)
    assert len(stable_digest(left)) == 64


def test_serialization_uses_enum_values_utc_and_decimal_strings() -> None:
    record = canonical_record(_event(reverse=False))

    assert isinstance(record, dict)
    assert record["event_family"] == "earnings"
    assert record["published_at"] == "2026-07-17T15:30:00+00:00"
    assert record["structured_fields"] == {"actual": "1.25", "consensus": "1.20"}


def test_serialization_redacts_sensitive_mapping_keys() -> None:
    record = canonical_record(
        {
            "authorization": "Bearer secret",
            "nested": {"approval_id": "approve-1", "safe": "visible"},
        }
    )

    assert record == {
        "authorization": "[REDACTED]",
        "nested": {"approval_id": "[REDACTED]", "safe": "visible"},
    }
