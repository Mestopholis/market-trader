from datetime import UTC, datetime, timedelta
from decimal import Decimal

from market_trader.market_data.cache import CacheState, InMemoryMarketDataCache
from market_trader.market_data.models import (
    NormalizedQuote,
    ObservationMetadata,
    QualityState,
)

NOW = datetime(2026, 7, 17, 14, 30, tzinfo=UTC)


def test_cache_hit_preserves_value_and_source_timestamps() -> None:
    quote = normalized_quote()
    cache: InMemoryMarketDataCache[NormalizedQuote] = InMemoryMarketDataCache()
    cache.put("quote:SPY", quote, expires_at=NOW + timedelta(seconds=15))

    result = cache.get("quote:SPY", now=NOW + timedelta(seconds=15))

    assert result.state is CacheState.HIT
    assert result.value is quote
    assert result.value.metadata.observed_at == NOW


def test_expired_cache_entry_is_explicit_not_a_miss() -> None:
    quote = normalized_quote()
    cache: InMemoryMarketDataCache[NormalizedQuote] = InMemoryMarketDataCache()
    cache.put("quote:SPY", quote, expires_at=NOW)

    result = cache.get("quote:SPY", now=NOW + timedelta(microseconds=1))

    assert result.state is CacheState.STALE
    assert result.value is quote
    assert result.expires_at == NOW


def test_missing_cache_entry_is_explicit() -> None:
    cache: InMemoryMarketDataCache[NormalizedQuote] = InMemoryMarketDataCache()

    result = cache.get("quote:SPY", now=NOW)

    assert result.state is CacheState.MISS
    assert result.value is None
    assert result.expires_at is None


def normalized_quote() -> NormalizedQuote:
    metadata = ObservationMetadata(
        source="fixture",
        event_id="quote-1",
        observed_at=NOW,
        ingested_at=NOW,
        session_date=None,
        normalized_schema_version=1,
        configuration_version="fixture-v1",
        correlation_id="corr-1",
        quality_state=QualityState.VALID,
        quality_reasons=(),
    )
    return NormalizedQuote(
        symbol="SPY",
        bid=Decimal("625.10"),
        ask=Decimal("625.20"),
        bid_size=100,
        ask_size=200,
        last=None,
        last_size=None,
        last_at=None,
        bid_venue=None,
        ask_venue=None,
        trade_venue=None,
        condition_codes=(),
        metadata=metadata,
    )
