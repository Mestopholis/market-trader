from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from typing import Protocol

from market_trader.domain.time import ensure_utc


class CacheState(StrEnum):
    HIT = "hit"
    MISS = "miss"
    STALE = "stale"


@dataclass(frozen=True)
class CacheResult[Value]:
    state: CacheState
    value: Value | None
    expires_at: datetime | None


class MarketDataCache[Value](Protocol):
    def put(self, key: str, value: Value, *, expires_at: datetime) -> None: ...

    def get(self, key: str, *, now: datetime) -> CacheResult[Value]: ...


class InMemoryMarketDataCache[Value]:
    def __init__(self) -> None:
        self._entries: dict[str, tuple[Value, datetime]] = {}

    def put(self, key: str, value: Value, *, expires_at: datetime) -> None:
        self._entries[key] = (value, ensure_utc(expires_at))

    def get(self, key: str, *, now: datetime) -> CacheResult[Value]:
        now = ensure_utc(now)
        entry = self._entries.get(key)
        if entry is None:
            return CacheResult(state=CacheState.MISS, value=None, expires_at=None)
        value, expires_at = entry
        state = CacheState.STALE if now > expires_at else CacheState.HIT
        return CacheResult(state=state, value=value, expires_at=expires_at)

