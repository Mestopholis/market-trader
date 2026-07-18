from datetime import UTC, datetime

from market_trader.domain.time import ensure_utc


def stored_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return ensure_utc(value)
