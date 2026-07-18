from datetime import UTC, datetime

from market_trader.domain.ids import new_domain_id
from market_trader.domain.time import ensure_utc, utc_now


def test_utc_now_returns_timezone_aware_utc_datetime() -> None:
    observed = utc_now()

    assert observed.tzinfo is UTC


def test_ensure_utc_rejects_naive_datetime() -> None:
    try:
        ensure_utc(datetime(2026, 7, 18, 12, 0, 0))
    except ValueError as error:
        assert "timezone-aware" in str(error)
    else:
        raise AssertionError("naive datetime was accepted")


def test_new_domain_id_uses_prefixed_uuid_shape() -> None:
    identifier = new_domain_id("evt")

    assert identifier.startswith("evt_")
    assert len(identifier) > len("evt_")
