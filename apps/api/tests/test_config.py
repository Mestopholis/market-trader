from collections.abc import Iterator

import pytest
from pytest import MonkeyPatch

from market_trader.config import TradingMode, get_settings


@pytest.fixture(autouse=True)
def clear_settings_cache() -> Iterator[None]:
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def test_defaults_to_paper_mode(monkeypatch: MonkeyPatch) -> None:
    monkeypatch.delenv("MARKET_TRADER_TRADING_MODE", raising=False)
    get_settings.cache_clear()

    settings = get_settings()

    assert settings.trading_mode is TradingMode.PAPER


def test_live_mode_is_rejected_in_foundation(monkeypatch: MonkeyPatch) -> None:
    monkeypatch.setenv("MARKET_TRADER_TRADING_MODE", "live")
    get_settings.cache_clear()

    try:
        get_settings()
    except ValueError as error:
        assert "Live trading is unavailable" in str(error)
    else:
        raise AssertionError("foundation configuration accepted live trading")


def test_defaults_display_timezone_to_chicago(monkeypatch: MonkeyPatch) -> None:
    monkeypatch.delenv("MARKET_TRADER_DISPLAY_TIMEZONE", raising=False)

    assert get_settings().display_timezone == "America/Chicago"


def test_rejects_unknown_display_timezone(monkeypatch: MonkeyPatch) -> None:
    monkeypatch.setenv("MARKET_TRADER_DISPLAY_TIMEZONE", "Not/A_Timezone")

    try:
        get_settings()
    except ValueError as error:
        assert "display timezone" in str(error).lower()
    else:
        raise AssertionError("invalid display timezone was accepted")
