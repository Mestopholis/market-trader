from datetime import UTC, date, datetime

from market_trader.market_calendar.models import EntryWindow, ExchangeSession
from market_trader.market_calendar.policy import EntryWindowPolicy


def session(close_hour: int) -> ExchangeSession:
    return ExchangeSession(
        calendar="XNYS",
        session_date=date(2026, 7, 20),
        market_open=datetime(2026, 7, 20, 13, 30, tzinfo=UTC),
        market_close=datetime(2026, 7, 20, close_hour, 0, tzinfo=UTC),
        is_early_close=close_hour == 17,
    )


def test_normal_session_entry_window() -> None:
    window = EntryWindowPolicy.v1().window_for(session(20))

    assert window.opens_at == datetime(2026, 7, 20, 13, 45, tzinfo=UTC)
    assert window.closes_at == datetime(2026, 7, 20, 19, 30, tzinfo=UTC)
    assert window.policy_version == "entry-window-v1"


def test_early_close_preserves_thirty_minute_buffer() -> None:
    window = EntryWindowPolicy.v1().window_for(session(17))

    assert window.closes_at == datetime(2026, 7, 20, 16, 30, tzinfo=UTC)


def test_entry_start_is_inclusive_and_end_is_exclusive() -> None:
    policy = EntryWindowPolicy.v1()
    window = policy.window_for(session(20))

    assert policy.allows(window.opens_at, window)
    assert not policy.allows(window.closes_at, window)


def test_rejects_session_too_short_for_entry_window() -> None:
    short_session = ExchangeSession(
        calendar="XNYS",
        session_date=date(2026, 7, 20),
        market_open=datetime(2026, 7, 20, 13, 30, tzinfo=UTC),
        market_close=datetime(2026, 7, 20, 14, 0, tzinfo=UTC),
        is_early_close=True,
    )

    try:
        EntryWindowPolicy.v1().window_for(short_session)
    except ValueError as error:
        assert "entry window" in str(error).lower()
    else:
        raise AssertionError("empty entry window was accepted")


def test_entry_window_model_rejects_inverted_bounds() -> None:
    try:
        EntryWindow(
            opens_at=datetime(2026, 7, 20, 19, 30, tzinfo=UTC),
            closes_at=datetime(2026, 7, 20, 13, 45, tzinfo=UTC),
            policy_version="entry-window-v1",
        )
    except ValueError as error:
        assert "entry window" in str(error).lower()
    else:
        raise AssertionError("inverted entry window was accepted")
