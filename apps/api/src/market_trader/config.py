from enum import StrEnum
from functools import lru_cache
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import model_validator
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

    @model_validator(mode="after")
    def validate_safety_settings(self) -> "Settings":
        if self.trading_mode is TradingMode.LIVE:
            raise ValueError("Live trading is unavailable in the foundation release")
        try:
            ZoneInfo(self.display_timezone)
        except ZoneInfoNotFoundError as error:
            raise ValueError("Unknown display timezone") from error
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()
