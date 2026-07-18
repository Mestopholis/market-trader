from market_trader.config import TradingMode, get_settings


def test_defaults_to_paper_mode(monkeypatch) -> None:
    monkeypatch.delenv("MARKET_TRADER_TRADING_MODE", raising=False)
    get_settings.cache_clear()

    settings = get_settings()

    assert settings.trading_mode is TradingMode.PAPER


def test_live_mode_is_rejected_in_foundation(monkeypatch) -> None:
    monkeypatch.setenv("MARKET_TRADER_TRADING_MODE", "live")
    get_settings.cache_clear()

    try:
        get_settings()
    except ValueError as error:
        assert "Live trading is unavailable" in str(error)
    else:
        raise AssertionError("foundation configuration accepted live trading")
