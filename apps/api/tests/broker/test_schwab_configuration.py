import pytest
from pydantic import ValidationError

from market_trader.config import Settings, TradingMode


def test_schwab_market_data_is_disabled_by_default() -> None:
    settings = _settings()

    assert settings.schwab_market_data_enabled is False
    assert settings.schwab_client_id is None
    assert settings.schwab_client_secret is None
    assert settings.schwab_token_encryption_key is None


def test_schwab_market_data_requires_local_credentials_when_enabled() -> None:
    with pytest.raises(ValidationError, match="Schwab Market Data requires"):
        _settings(schwab_market_data_enabled=True)


def test_schwab_market_data_accepts_loopback_callback_and_credentials() -> None:
    settings = _settings(
        schwab_market_data_enabled=True,
        schwab_callback_url="https://127.0.0.1:8182",
        schwab_client_id="synthetic-client-id",
        schwab_client_secret="synthetic-client-secret",
        schwab_token_encryption_key="synthetic-token-encryption-key-32",
    )

    assert settings.schwab_market_data_enabled is True
    assert settings.schwab_callback_url == "https://127.0.0.1:8182"
    assert "synthetic-client-secret" not in repr(settings)


def test_schwab_market_data_rejects_non_loopback_callback() -> None:
    with pytest.raises(ValidationError, match="loopback HTTPS callback"):
        _settings(
            schwab_market_data_enabled=True,
            schwab_callback_url="https://example.com/callback",
            schwab_client_id="synthetic-client-id",
            schwab_client_secret="synthetic-client-secret",
            schwab_token_encryption_key="synthetic-token-encryption-key-32",
        )


def test_live_mode_remains_unavailable_with_schwab_enabled() -> None:
    with pytest.raises(ValidationError, match="Live trading is unavailable"):
        _settings(
            trading_mode=TradingMode.LIVE,
            schwab_market_data_enabled=True,
            schwab_callback_url="https://127.0.0.1:8182",
            schwab_client_id="synthetic-client-id",
            schwab_client_secret="synthetic-client-secret",
            schwab_token_encryption_key="synthetic-token-encryption-key-32",
        )


def _settings(**values: object) -> Settings:
    return Settings(_env_file=None, **values)  # type: ignore[call-arg, arg-type]
