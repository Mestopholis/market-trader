from enum import StrEnum
from functools import lru_cache

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

    @model_validator(mode="after")
    def reject_live_mode_during_foundation(self) -> "Settings":
        if self.trading_mode is TradingMode.LIVE:
            raise ValueError("Live trading is unavailable in the foundation release")
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()
