from datetime import UTC, datetime
from decimal import Decimal

import pytest

from market_trader.options_analysis.models import (
    EvaluationState,
    TechnicalReference,
    WarningSeverity,
)


def test_technical_reference_requires_aware_utc_time() -> None:
    with pytest.raises(ValueError, match="timezone-aware"):
        TechnicalReference(
            underlying_price=Decimal("100.00"),
            technical_stop=Decimal("95.00"),
            snapshot_digest="a" * 64,
            observed_at=datetime(2026, 7, 20, 15, 0),
        )


def test_technical_reference_normalizes_an_aware_utc_time() -> None:
    reference = TechnicalReference(
        underlying_price=Decimal("100.00"),
        technical_stop=Decimal("95.00"),
        snapshot_digest="a" * 64,
        observed_at=datetime(2026, 7, 20, 10, 0, tzinfo=UTC),
    )

    assert reference.observed_at == datetime(2026, 7, 20, 10, 0, tzinfo=UTC)
    assert EvaluationState.ACCEPTED.value == "accepted"
    assert WarningSeverity.BLOCK.value == "block"
