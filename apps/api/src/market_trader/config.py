from enum import StrEnum
from functools import lru_cache
from urllib.parse import urlparse
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class TradingMode(StrEnum):
    PAPER = "paper"
    LIVE = "live"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_prefix="MARKET_TRADER_",
        extra="ignore",
    )

    environment: str = "local"
    trading_mode: TradingMode = TradingMode.PAPER
    app_version: str = "0.1.0"
    database_url: str = "sqlite:///./data/market_trader.db"
    display_timezone: str = "America/Chicago"
    auth_username: str | None = None
    auth_password_hash: str | None = None
    session_secret: str | None = None
    session_ttl_seconds: int = 3600
    schwab_market_data_enabled: bool = False
    schwab_callback_url: str = "https://127.0.0.1:8182"
    schwab_client_id: str | None = None
    schwab_client_secret: str | None = Field(default=None, repr=False)
    schwab_token_encryption_key: str | None = Field(default=None, repr=False)
    schwab_accounts_trading_enabled: bool = False
    schwab_accounts_trading_client_id: str | None = None
    schwab_accounts_trading_client_secret: str | None = Field(default=None, repr=False)

    @model_validator(mode="after")
    def validate_safety_settings(self) -> "Settings":
        if self.trading_mode is TradingMode.LIVE:
            raise ValueError("Live trading is unavailable in the foundation release")
        try:
            ZoneInfo(self.display_timezone)
        except ZoneInfoNotFoundError as error:
            raise ValueError("Unknown display timezone") from error
        if self.schwab_market_data_enabled or self.schwab_accounts_trading_enabled:
            parsed_callback = urlparse(self.schwab_callback_url)
            if (
                parsed_callback.scheme != "https"
                or parsed_callback.hostname not in {"127.0.0.1", "localhost"}
                or parsed_callback.port != 8182
                or parsed_callback.path not in {"", "/"}
            ):
                raise ValueError(
                    "Schwab integrations require a loopback HTTPS callback on port 8182"
                )
        if self.schwab_market_data_enabled:
            missing = [
                name
                for name, value in (
                    ("MARKET_TRADER_SCHWAB_CLIENT_ID", self.schwab_client_id),
                    ("MARKET_TRADER_SCHWAB_CLIENT_SECRET", self.schwab_client_secret),
                    (
                        "MARKET_TRADER_SCHWAB_TOKEN_ENCRYPTION_KEY",
                        self.schwab_token_encryption_key,
                    ),
                )
                if not value
            ]
            if missing:
                joined = ", ".join(missing)
                raise ValueError(f"Schwab Market Data requires {joined}")
        if self.schwab_accounts_trading_enabled:
            missing = [
                name
                for name, value in (
                    (
                        "MARKET_TRADER_SCHWAB_ACCOUNTS_TRADING_CLIENT_ID",
                        self.schwab_accounts_trading_client_id,
                    ),
                    (
                        "MARKET_TRADER_SCHWAB_ACCOUNTS_TRADING_CLIENT_SECRET",
                        self.schwab_accounts_trading_client_secret,
                    ),
                    (
                        "MARKET_TRADER_SCHWAB_TOKEN_ENCRYPTION_KEY",
                        self.schwab_token_encryption_key,
                    ),
                )
                if not value
            ]
            if missing:
                joined = ", ".join(missing)
                raise ValueError(f"Schwab Accounts and Trading requires {joined}")
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()
