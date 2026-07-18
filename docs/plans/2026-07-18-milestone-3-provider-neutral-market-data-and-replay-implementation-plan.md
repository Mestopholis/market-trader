# Milestone 3 Provider-Neutral Market Data And Replay Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Build deterministic, provider-neutral market-data normalization, quality enforcement, fixture replay, and idempotent persistence without adding any network provider or Schwab credentials.

**Architecture:** Provider adapters emit project-owned `ProviderEvent` values into a typed normalization pipeline for quotes, candles, option chains, and corporate actions. The pipeline sanitizes first, applies structural validation, ordering, idempotency, and versioned freshness rules, then sends accepted or rejected outcomes through an `IngestionSink`; replay uses the same path with a virtual clock. The default sink is in memory, while an explicitly configured repository sink stores accepted snapshots or append-only quarantine records and audit events transactionally.

**Tech Stack:** Python 3.12+, standard-library `dataclasses`, `Decimal`, `Protocol`, `json`, `hashlib`, and `argparse`; SQLAlchemy 2; Alembic; `exchange-calendars`; pytest, Ruff, and mypy.

**Approved detail:** Freshness policy `market-data-freshness-v1` permits source timestamps up to five seconds ahead of ingestion time. A completed daily XNYS candle remains current through the next exchange session's close plus 90 seconds, computed through `ExchangeCalendar`; equality at every boundary is valid.

**Working directory:** Run backend commands from `apps/api` unless a step says otherwise.

---

### Task 1: Add Shared Market-Data Contracts And Provider Capabilities

**Files:**
- Create: `apps/api/src/market_trader/market_data/__init__.py`
- Create: `apps/api/src/market_trader/market_data/models.py`
- Create: `apps/api/src/market_trader/market_data/providers.py`
- Test: `apps/api/tests/market_data/test_provider_contracts.py`

**Step 1: Write the failing contract tests**

Cover immutable provider events, UTC enforcement, immutable capabilities, and an explicit unsupported response. Start with:

```python
from datetime import UTC, datetime

import pytest

from market_trader.market_data.models import DataKind, ProviderEvent
from market_trader.market_data.providers import ProviderCapabilities, UnsupportedCapability


def test_provider_event_rejects_naive_timestamps() -> None:
    with pytest.raises(ValueError, match="timezone-aware"):
        ProviderEvent(
            source="fixture",
            event_id="quote-1",
            data_kind=DataKind.QUOTE,
            observed_at=datetime(2026, 7, 17, 14, 30),
            ingested_at=datetime(2026, 7, 17, 14, 30, tzinfo=UTC),
            payload={"symbol": "SPY"},
            fixture_schema_version=1,
            configuration_version="fixture-v1",
            correlation_id="corr-1",
        )


def test_capabilities_do_not_silently_claim_unsupported_data() -> None:
    capabilities = ProviderCapabilities(
        quotes=True,
        candles=True,
        option_chains=False,
        corporate_actions=False,
    )
    assert capabilities.option_chains is False
    assert UnsupportedCapability(DataKind.OPTION_CHAIN).data_kind is DataKind.OPTION_CHAIN
```

Also define runtime-checkable protocols for quote retrieval, ranged candle retrieval, constrained option-chain retrieval, corporate-action retrieval, and provider status. Protocol return types must be `tuple[ProviderEvent, ...] | UnsupportedCapability`, never an empty tuple to represent unsupported behavior.

**Step 2: Run the test and verify RED**

Run: `./.venv/bin/pytest tests/market_data/test_provider_contracts.py -v`

Expected: FAIL during import because `market_trader.market_data` does not exist.

**Step 3: Implement the minimal shared contracts**

Define these stable enums and dataclasses:

```python
class DataKind(StrEnum):
    QUOTE = "quote"
    CANDLE = "candle"
    OPTION_CHAIN = "option_chain"
    CORPORATE_ACTION = "corporate_action"
    PROVIDER_STATE = "provider_state"


class QualityState(StrEnum):
    VALID = "valid"
    DEGRADED = "degraded"
    STALE = "stale"
    QUARANTINED = "quarantined"


@dataclass(frozen=True)
class ProviderEvent:
    source: str
    event_id: str
    data_kind: DataKind
    observed_at: datetime
    ingested_at: datetime
    payload: Mapping[str, object]
    fixture_schema_version: int
    configuration_version: str
    correlation_id: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "observed_at", ensure_utc(self.observed_at))
        object.__setattr__(self, "ingested_at", ensure_utc(self.ingested_at))
        object.__setattr__(self, "payload", MappingProxyType(dict(self.payload)))
```

Add request dataclasses for each ranged provider protocol, `ProviderCapabilities`, `ProviderHealth`, and `UnsupportedCapability`. Keep all objects project-owned; no vendor field names may appear outside fixture payloads and normalizers.

**Step 4: Run focused verification and verify GREEN**

Run: `./.venv/bin/pytest tests/market_data/test_provider_contracts.py -v`

Expected: PASS.

Run: `./.venv/bin/ruff check src/market_trader/market_data tests/market_data/test_provider_contracts.py`

Expected: PASS.

**Step 5: Commit**

```bash
git add apps/api/src/market_trader/market_data apps/api/tests/market_data/test_provider_contracts.py
git commit -m "feat: add provider-neutral market data contracts"
```

---

### Task 2: Normalize Quotes With Stable Quality Reasons

**Files:**
- Modify: `apps/api/src/market_trader/market_data/models.py`
- Create: `apps/api/src/market_trader/market_data/normalizers.py`
- Test: `apps/api/tests/market_data/test_quote_normalization.py`

**Step 1: Write failing quote-normalization tests**

Use string inputs so every monetary field crosses the boundary as `Decimal`. Test a valid quote, a locked quote, a crossed quote, missing top-of-book fields, negative price/size, and a binary float. Assert stable reasons rather than exception text:

```python
def test_locked_quote_is_degraded() -> None:
    result = normalize_quote(
        provider_event(
            payload={
                "symbol": "SPY",
                "bid": "625.10",
                "ask": "625.10",
                "bid_size": 100,
                "ask_size": 200,
            }
        )
    )

    assert result.accepted is not None
    assert result.accepted.metadata.quality_state is QualityState.DEGRADED
    assert result.accepted.metadata.quality_reasons == ("locked_market",)
    assert result.accepted.bid == Decimal("625.10")


@pytest.mark.parametrize(
    ("payload_update", "reason"),
    [
        ({"ask": "624.99"}, "crossed_market"),
        ({"bid": None}, "missing_top_of_book"),
        ({"bid_size": -1}, "negative_value"),
        ({"bid": 625.1}, "binary_float_not_allowed"),
    ],
)
def test_invalid_quote_is_rejected(payload_update: dict[str, object], reason: str) -> None:
    result = normalize_quote(provider_event(payload_update=payload_update))
    assert result.rejection is not None
    assert reason in result.rejection.reason_codes
```

**Step 2: Run the test and verify RED**

Run: `./.venv/bin/pytest tests/market_data/test_quote_normalization.py -v`

Expected: FAIL because `normalize_quote` and normalized quote models are missing.

**Step 3: Implement quote models and normalization**

Add immutable `ObservationMetadata`, `NormalizedQuote`, `RejectedObservation`, and generic `NormalizationResult[T]`. `ObservationMetadata` includes source, event ID, UTC source and ingestion times, optional session date, normalized schema version, configuration version, correlation ID, state, and a sorted tuple of reason codes.

Parse only JSON strings and integers into exact values. Reject booleans where integers are required, reject floats, retain optional last trade and venue/condition values, and use these reason codes:

```text
binary_float_not_allowed
crossed_market
invalid_decimal
missing_field
missing_top_of_book
negative_value
locked_market
```

Keep wide spreads structurally valid; Milestone 6 will define liquidity policy.

**Step 4: Run focused verification and verify GREEN**

Run: `./.venv/bin/pytest tests/market_data/test_quote_normalization.py -v`

Expected: PASS.

Run: `./.venv/bin/mypy src/market_trader/market_data/models.py src/market_trader/market_data/normalizers.py`

Expected: PASS.

**Step 5: Commit**

```bash
git add apps/api/src/market_trader/market_data/models.py apps/api/src/market_trader/market_data/normalizers.py apps/api/tests/market_data/test_quote_normalization.py
git commit -m "feat: normalize provider-neutral quotes"
```

---

### Task 3: Normalize One-Minute And Daily Candles

**Files:**
- Modify: `apps/api/src/market_trader/market_data/models.py`
- Modify: `apps/api/src/market_trader/market_data/normalizers.py`
- Test: `apps/api/tests/market_data/test_candle_normalization.py`

**Step 1: Write failing candle tests**

Cover one-minute and daily intervals, inclusive start/exclusive end, exact `Decimal` OHLC/VWAP, optional trade count, adjusted state, malformed ranges, inconsistent OHLC, negative volume, and completed bars more than five seconds ahead of ingestion:

```python
def test_normalizes_completed_one_minute_candle() -> None:
    result = normalize_candle(candle_event())
    assert result.accepted is not None
    assert result.accepted.interval is CandleInterval.ONE_MINUTE
    assert result.accepted.adjustment is AdjustmentState.UNADJUSTED
    assert result.accepted.high >= result.accepted.open
    assert result.accepted.end - result.accepted.start == timedelta(minutes=1)


def test_rejects_inconsistent_ohlc() -> None:
    result = normalize_candle(candle_event(payload_update={"high": "624.00"}))
    assert result.rejection is not None
    assert result.rejection.reason_codes == ("inconsistent_ohlc",)
```

**Step 2: Run the test and verify RED**

Run: `./.venv/bin/pytest tests/market_data/test_candle_normalization.py -v`

Expected: FAIL because candle models and `normalize_candle` are missing.

**Step 3: Implement candle normalization**

Add `CandleInterval`, `AdjustmentState`, and `NormalizedCandle`. Require `1m` candles to span exactly one minute. Require daily candles to carry a session date and span the provider's explicit start/end without assuming 24 UTC hours. Validate:

```python
if end <= start:
    reject("invalid_time_range")
if high < max(open_, close, low) or low > min(open_, close, high):
    reject("inconsistent_ohlc")
if volume < 0 or (trade_count is not None and trade_count < 0):
    reject("negative_value")
if end > event.ingested_at + timedelta(seconds=5):
    reject("future_timestamp")
```

Use the same exact-number parser as quotes. Do not read the host clock.

**Step 4: Run focused verification and verify GREEN**

Run: `./.venv/bin/pytest tests/market_data/test_candle_normalization.py -v`

Expected: PASS.

**Step 5: Commit**

```bash
git add apps/api/src/market_trader/market_data apps/api/tests/market_data/test_candle_normalization.py
git commit -m "feat: normalize market data candles"
```

---

### Task 4: Normalize Option Chains And Contract Quality

**Files:**
- Modify: `apps/api/src/market_trader/market_data/models.py`
- Modify: `apps/api/src/market_trader/market_data/normalizers.py`
- Test: `apps/api/tests/market_data/test_option_chain_normalization.py`

**Step 1: Write failing option-chain tests**

Test a complete standard chain, provider-marked partial chain, unsupported deliverable, locked contract, duplicate identity, crossed contract, expiration before observation session, missing identity, and negative values. Optional analytics must be transported unchanged as `Decimal` and never calculated.

```python
def test_partial_chain_is_degraded_and_blocking_for_complete_consumers() -> None:
    result = normalize_option_chain(option_chain_event(completeness="partial"))
    assert result.accepted is not None
    assert result.accepted.metadata.quality_state is QualityState.DEGRADED
    assert "partial_chain" in result.accepted.metadata.quality_reasons
    assert result.accepted.is_complete is False


def test_duplicate_contract_identity_rejects_whole_chain() -> None:
    event = option_chain_event(duplicate_first_contract=True)
    result = normalize_option_chain(event)
    assert result.rejection is not None
    assert result.rejection.reason_codes == ("duplicate_contract",)
```

**Step 2: Run the test and verify RED**

Run: `./.venv/bin/pytest tests/market_data/test_option_chain_normalization.py -v`

Expected: FAIL because option-chain models and normalizer are missing.

**Step 3: Implement option-chain normalization**

Add immutable `NormalizedOptionContract` and `NormalizedOptionChain`, plus enums for put/call and standard/unsupported deliverables. Each contract carries its own sorted quality reasons. Reject the whole event for duplicate/incomplete identities, invalid expiration, negative values, or crossed markets. Retain unsupported deliverables explicitly with `unsupported_deliverable`; retain locked contracts with `locked_market`. A partial chain is accepted as degraded but its quality reason is blocking for complete-chain consumers.

**Step 4: Run focused verification and verify GREEN**

Run: `./.venv/bin/pytest tests/market_data/test_option_chain_normalization.py -v`

Expected: PASS.

Run: `./.venv/bin/ruff check src/market_trader/market_data tests/market_data`

Expected: PASS.

**Step 5: Commit**

```bash
git add apps/api/src/market_trader/market_data apps/api/tests/market_data/test_option_chain_normalization.py
git commit -m "feat: normalize option chain observations"
```

---

### Task 5: Normalize Supported Corporate Actions

**Files:**
- Modify: `apps/api/src/market_trader/market_data/models.py`
- Modify: `apps/api/src/market_trader/market_data/normalizers.py`
- Test: `apps/api/tests/market_data/test_corporate_action_normalization.py`

**Step 1: Write failing corporate-action tests**

Cover forward split, reverse split, stock dividend, and cash dividend. Test optional declaration/record/payment dates, positive split ratios, positive cash amount, ISO currency normalization, missing effective/ex-dividend date, and unknown action types.

```python
@pytest.mark.parametrize("action_type", ["split", "reverse_split", "stock_dividend"])
def test_normalizes_share_ratio_action(action_type: str) -> None:
    result = normalize_corporate_action(share_action_event(action_type))
    assert result.accepted is not None
    assert result.accepted.share_ratio == Decimal("2")
    assert result.accepted.cash_amount is None


def test_unknown_action_is_quarantined() -> None:
    result = normalize_corporate_action(action_event("spinoff"))
    assert result.rejection is not None
    assert result.rejection.reason_codes == ("unsupported_action_type",)
```

**Step 2: Run the test and verify RED**

Run: `./.venv/bin/pytest tests/market_data/test_corporate_action_normalization.py -v`

Expected: FAIL because corporate-action models and normalizer are missing.

**Step 3: Implement corporate-action normalization**

Add `CorporateActionType` and `NormalizedCorporateAction`. Enforce exactly one relevant value family: share actions require a positive ratio and no cash amount; cash dividends require a positive amount and three-letter currency and no ratio. Preserve facts only; do not adjust historical candles or calculate returns.

**Step 4: Run focused verification and verify GREEN**

Run: `./.venv/bin/pytest tests/market_data/test_corporate_action_normalization.py -v`

Expected: PASS.

Run: `./.venv/bin/mypy src/market_trader/market_data`

Expected: PASS.

**Step 5: Commit**

```bash
git add apps/api/src/market_trader/market_data apps/api/tests/market_data/test_corporate_action_normalization.py
git commit -m "feat: normalize corporate action observations"
```

---

### Task 6: Apply Versioned Freshness And Future-Timestamp Policy

**Files:**
- Create: `apps/api/src/market_trader/market_data/quality.py`
- Modify: `apps/api/src/market_trader/market_data/normalizers.py`
- Test: `apps/api/tests/market_data/test_freshness_policy.py`

**Step 1: Write failing boundary tests**

Use `FrozenClock` and the Milestone 2 `ExchangeCalendar`. Test exact equality and one microsecond late for quotes, one-minute candles, option chains, and corporate actions. Test observations exactly five seconds ahead and one microsecond beyond. For daily candles, use both a normal session and the July 3, 2026 early-close boundary:

```python
def test_quote_is_valid_at_boundary_and_stale_one_microsecond_later() -> None:
    observed = datetime(2026, 7, 17, 14, 30, tzinfo=UTC)
    policy = FreshnessPolicy.v1(exchange_calendar())
    assert policy.evaluate(DataKind.QUOTE, observed_at=observed, ingested_at=observed,
                           now=observed + timedelta(seconds=15)).state is QualityState.VALID
    assert policy.evaluate(DataKind.QUOTE, observed_at=observed, ingested_at=observed,
                           now=observed + timedelta(seconds=15, microseconds=1)).state is QualityState.STALE


def test_daily_candle_expires_after_next_session_close_plus_grace() -> None:
    policy = FreshnessPolicy.v1(exchange_calendar())
    result = policy.evaluate_daily_candle(
        session_date=date(2026, 7, 2),
        now=datetime(2026, 7, 6, 20, 1, 30, tzinfo=UTC),
    )
    assert result.state is QualityState.VALID
    assert result.valid_until == datetime(2026, 7, 6, 20, 1, 30, tzinfo=UTC)
```

July 3 is a holiday-observed closure in 2026, so the next XNYS session after July 2 is July 6. Add a separate known early-close session assertion using calendar output rather than hard-coded local offsets.

**Step 2: Run the test and verify RED**

Run: `./.venv/bin/pytest tests/market_data/test_freshness_policy.py -v`

Expected: FAIL because `FreshnessPolicy` is missing.

**Step 3: Implement `market-data-freshness-v1`**

Define immutable `FreshnessAssessment` and `FreshnessPolicy`. The boundaries are:

```python
QUOTE_MAX_AGE = timedelta(seconds=15)
ONE_MINUTE_CANDLE_GRACE = timedelta(seconds=90)
OPTION_CHAIN_MAX_AGE = timedelta(seconds=60)
CORPORATE_ACTION_MAX_AGE = timedelta(hours=24)
DAILY_CANDLE_GRACE = timedelta(seconds=90)
FUTURE_TOLERANCE = timedelta(seconds=5)
```

For daily candles, ask `ExchangeCalendar` for the session after the candle's completed session and use that session's market close plus 90 seconds as `valid_until`. Corporate actions age from `ingested_at`; all other kinds age from their specified source timestamp. Mark stale only when `now > valid_until`. Return `future_timestamp` when the relevant source time exceeds ingestion by more than five seconds. Apply this policy after structural normalization and route stale results as rejected outcomes with `QualityState.STALE`.

**Step 4: Run focused verification and verify GREEN**

Run: `./.venv/bin/pytest tests/market_data/test_freshness_policy.py tests/market_data/test_*_normalization.py -v`

Expected: PASS.

**Step 5: Commit**

```bash
git add apps/api/src/market_trader/market_data apps/api/tests/market_data
git commit -m "feat: enforce versioned market data freshness"
```

---

### Task 7: Sanitize Payloads And Produce Stable Ingestion Digests

**Files:**
- Create: `apps/api/src/market_trader/market_data/sanitization.py`
- Test: `apps/api/tests/market_data/test_sanitization.py`

**Step 1: Write failing sanitization tests**

Test nested dictionaries/lists, case-insensitive secret keys, authorization and cookie values, bounded strings, unsupported binary values, canonical key ordering, and digest stability across dictionary insertion order:

```python
def test_sanitizes_before_canonical_digest() -> None:
    left = {"symbol": "SPY", "Authorization": "Bearer secret", "nested": {"cookie": "x"}}
    right = {"nested": {"cookie": "different"}, "Authorization": "other", "symbol": "SPY"}

    sanitized_left = sanitize_payload(left)
    sanitized_right = sanitize_payload(right)

    assert sanitized_left["Authorization"] == "[REDACTED]"
    assert canonical_digest(sanitized_left) == canonical_digest(sanitized_right)


def test_ingestion_key_is_stable_and_source_scoped() -> None:
    assert ingestion_key("fixture", "event-1") == ingestion_key("fixture", "event-1")
    assert ingestion_key("fixture", "event-1") != ingestion_key("other", "event-1")
```

**Step 2: Run the test and verify RED**

Run: `./.venv/bin/pytest tests/market_data/test_sanitization.py -v`

Expected: FAIL because sanitization functions are missing.

**Step 3: Implement sanitization and canonical JSON**

Recursively sanitize before diagnostics, persistence, or hashing. Redact keys containing `authorization`, `cookie`, `token`, `secret`, `password`, `api_key`, or `account`. Bound strings to 2,048 characters and collections to 1,000 entries. Represent bytes and unknown objects with type, length when known, and SHA-256 digest rather than raw content. Serialize canonical JSON with sorted keys, compact separators, UTF-8, and no NaN. Build the ingestion key from `source`, `event_id`, and fixture schema version; use the sanitized payload digest separately to detect an event-ID conflict.

**Step 4: Run focused verification and verify GREEN**

Run: `./.venv/bin/pytest tests/market_data/test_sanitization.py -v`

Expected: PASS.

Run: `./.venv/bin/ruff check src/market_trader/market_data/sanitization.py tests/market_data/test_sanitization.py`

Expected: PASS.

**Step 5: Commit**

```bash
git add apps/api/src/market_trader/market_data/sanitization.py apps/api/tests/market_data/test_sanitization.py
git commit -m "feat: sanitize and fingerprint market payloads"
```

---

### Task 8: Add Deterministic Cache And Rate-Limit Boundaries

**Files:**
- Create: `apps/api/src/market_trader/market_data/cache.py`
- Create: `apps/api/src/market_trader/market_data/rate_limit.py`
- Test: `apps/api/tests/market_data/test_cache.py`
- Test: `apps/api/tests/market_data/test_rate_limit.py`

**Step 1: Write failing cache tests**

Define a typed cache protocol and deterministic in-memory implementation. Assert that retrieval preserves the original observation and ingestion timestamps, and expired entries return explicit stale state rather than a miss:

```python
def test_expired_cache_entry_is_explicit_and_preserves_source_time() -> None:
    cache: InMemoryMarketDataCache[NormalizedQuote] = InMemoryMarketDataCache()
    cache.put("quote:SPY", quote, expires_at=NOW)
    result = cache.get("quote:SPY", now=NOW + timedelta(microseconds=1))
    assert result.state is CacheState.STALE
    assert result.value is quote
    assert result.value.metadata.observed_at == quote.metadata.observed_at
```

**Step 2: Run the cache test and verify RED**

Run: `./.venv/bin/pytest tests/market_data/test_cache.py -v`

Expected: FAIL because cache types are missing.

**Step 3: Implement the cache boundary**

Use `CacheState` values `hit`, `miss`, and `stale`. The cache accepts `now` explicitly on every read and never mutates stored observations or extends freshness. Do not persist cache entries.

**Step 4: Run the cache test and verify GREEN**

Run: `./.venv/bin/pytest tests/market_data/test_cache.py -v`

Expected: PASS.

**Step 5: Write failing deterministic rate-limit tests**

Test `allowed`, `throttled`, `unavailable`, and `recovering`, including exact retry boundaries and transition back to allowed. Inject `Clock`; do not sleep.

```python
def test_throttle_boundary_is_deterministic() -> None:
    limiter = InMemoryRateLimitBoundary(clock=clock)
    limiter.throttle("fixture", retry_at=NOW + timedelta(seconds=30))
    assert limiter.check("fixture").state is RateLimitState.THROTTLED
    clock.advance_to(NOW + timedelta(seconds=30))
    assert limiter.check("fixture").state is RateLimitState.ALLOWED
```

**Step 6: Run the rate-limit test and verify RED**

Run: `./.venv/bin/pytest tests/market_data/test_rate_limit.py -v`

Expected: FAIL because rate-limit types are missing.

**Step 7: Implement the rate-limit boundary**

Return immutable status objects with source, state, observed transition time, optional retry time, and stable reason code. Provider adapters decide how to call it; this boundary performs no network operation and no hidden waiting.

**Step 8: Run focused verification and verify GREEN**

Run: `./.venv/bin/pytest tests/market_data/test_cache.py tests/market_data/test_rate_limit.py -v`

Expected: PASS.

**Step 9: Commit**

```bash
git add apps/api/src/market_trader/market_data/cache.py apps/api/src/market_trader/market_data/rate_limit.py apps/api/tests/market_data/test_cache.py apps/api/tests/market_data/test_rate_limit.py
git commit -m "feat: add deterministic market data boundaries"
```

---

### Task 9: Load And Validate Versioned Fixture Datasets

**Files:**
- Create: `apps/api/src/market_trader/market_data/fixtures.py`
- Test: `apps/api/tests/market_data/test_fixture_loader.py`
- Create: `apps/api/tests/market_data/fixtures/minimal/manifest.json`
- Create: `apps/api/tests/market_data/fixtures/minimal/quotes.ndjson`

**Step 1: Write failing fixture-loader tests**

Test a valid manifest, ordered stream loading, SHA-256 mismatch, count mismatch, malformed JSON with line number, unknown fixture schema, wrong data kind, decreasing ingestion times, naive timestamps, undeclared stream files, and credentials detected in payloads.

```python
def test_loads_events_in_manifest_stream_and_line_order() -> None:
    dataset = FixtureDataset.load(FIXTURES / "minimal")
    assert [event.event_id for event in dataset.events] == ["quote-1", "quote-2"]


def test_rejects_decreasing_ingestion_time(tmp_path: Path) -> None:
    dataset_path = copy_fixture(tmp_path, "decreasing-ingestion")
    with pytest.raises(FixtureValidationError, match="nondecreasing"):
        FixtureDataset.load(dataset_path)
```

**Step 2: Run the test and verify RED**

Run: `./.venv/bin/pytest tests/market_data/test_fixture_loader.py -v`

Expected: FAIL because `FixtureDataset` is missing.

**Step 3: Implement strict manifest and NDJSON loading**

Use standard-library JSON and typed dataclasses. A manifest must define dataset ID, description, schema version `1`, source, configuration version, ordered streams, each stream's data kind/hash/count, and expected outcome counts. Read complete files, verify hashes and counts before producing events, preserve declared stream and line order, and validate timestamps with `datetime.fromisoformat` plus `ensure_utc`. Error messages include dataset, stream, and line but never full raw payloads.

**Step 4: Run focused verification and verify GREEN**

Run: `./.venv/bin/pytest tests/market_data/test_fixture_loader.py -v`

Expected: PASS.

Run: `./.venv/bin/mypy src/market_trader/market_data/fixtures.py`

Expected: PASS.

**Step 5: Commit**

```bash
git add apps/api/src/market_trader/market_data/fixtures.py apps/api/tests/market_data/test_fixture_loader.py apps/api/tests/market_data/fixtures
git commit -m "feat: validate recorded market data fixtures"
```

---

### Task 10: Build Replay Ordering, Idempotency, And In-Memory Sink

**Files:**
- Create: `apps/api/src/market_trader/market_data/pipeline.py`
- Create: `apps/api/src/market_trader/market_data/replay.py`
- Create: `apps/api/src/market_trader/market_data/sinks.py`
- Test: `apps/api/tests/market_data/test_replay.py`

**Step 1: Write failing replay tests**

Use a mutable test replay clock implementing `Clock`. Test that replay advances to ingestion time, never sorts by observation time, accepts equal observation timestamps with distinct event IDs, quarantines older observations by source/kind/identity watermark, deduplicates exact ingestion keys, rejects same key with a different sanitized payload digest as `event_identity_conflict`, and returns identical summaries/digests on repeated in-memory runs.

```python
def test_replay_preserves_arrival_order_and_quarantines_older_observation() -> None:
    result = ReplayEngine(clock=clock, sink=InMemoryIngestionSink()).replay(dataset)
    assert clock.visited == tuple(event.ingested_at for event in dataset.events)
    assert result.accepted == 1
    assert result.quarantined == 1
    assert result.reasons["out_of_order"] == 1


def test_replay_result_digest_ignores_random_storage_ids() -> None:
    first = replay(dataset)
    second = replay(dataset)
    assert first == second
    assert first.result_digest == second.result_digest
```

**Step 2: Run the test and verify RED**

Run: `./.venv/bin/pytest tests/market_data/test_replay.py -v`

Expected: FAIL because replay and sink modules are missing.

**Step 3: Implement pipeline dispatch and replay**

Define an `IngestionSink` protocol with accepted, rejected, and duplicate operations; immutable `ReplayResult`; and default `InMemoryIngestionSink`. Pipeline order is fixed:

1. Sanitize and calculate payload digest.
2. Calculate stable ingestion key.
3. Detect exact duplicate or event-identity conflict.
4. Dispatch to the kind-specific normalizer.
5. Apply freshness using the replay clock.
6. Compare accepted observation time with the arrival watermark `(source, data_kind, identity)`.
7. Persist accepted/degraded or rejected/stale outcome through the sink.
8. Update watermark only for accepted/degraded observations.

The replay clock may only advance, and manifest ingestion timestamps are the sole source of replay time. Build result digests from canonical ordered outcome records containing ingestion key, payload digest, state, and sorted reasons; exclude database IDs and wall-clock values.

**Step 4: Run focused verification and verify GREEN**

Run: `./.venv/bin/pytest tests/market_data/test_replay.py -v`

Expected: PASS.

Run: `./.venv/bin/pytest tests/market_data -v`

Expected: PASS.

**Step 5: Commit**

```bash
git add apps/api/src/market_trader/market_data apps/api/tests/market_data/test_replay.py
git commit -m "feat: add deterministic market data replay"
```

---

### Task 11: Migrate Stable Snapshot Keys And Append-Only Quarantine Storage

**Files:**
- Create: `apps/api/migrations/versions/20260718_0002_market_data_replay.py`
- Modify: `apps/api/src/market_trader/db/models.py`
- Modify: `apps/api/tests/test_migrations.py`
- Create: `apps/api/tests/market_data/test_quarantine_storage.py`

**Step 1: Write failing migration tests**

Add tests that upgrade a clean database to head and that first upgrade to `20260718_0001`, insert a representative Milestone 2 snapshot, then upgrade to head. Assert the existing row is backfilled with `data_kind="legacy"` and `ingestion_key="legacy:<snapshot-id>"`, and assert the new table/columns/indexes match ORM metadata.

```python
def test_market_data_migration_upgrades_existing_snapshot(tmp_path: Path) -> None:
    config = alembic_config(database_url(tmp_path))
    command.upgrade(config, "20260718_0001")
    insert_legacy_snapshot(database_url(tmp_path), snapshot_id="mds_existing")
    command.upgrade(config, "head")

    with create_engine(database_url(tmp_path)).connect() as connection:
        row = connection.execute(
            text("SELECT data_kind, ingestion_key FROM market_data_snapshots")
        ).one()
    assert row == ("legacy", "legacy:mds_existing")
```

**Step 2: Run the migration test and verify RED**

Run: `./.venv/bin/pytest tests/test_migrations.py -v`

Expected: FAIL because revision `20260718_0002` and quarantine storage do not exist.

**Step 3: Add ORM records and migration**

Add non-null `data_kind` and `ingestion_key` to `MarketDataSnapshotORM`; backfill existing rows before changing nullability. Add a unique index on snapshot ingestion key.

Create `MarketDataQuarantineORM` with:

```text
id, ingestion_key, source, event_id, data_kind,
observed_at, ingested_at, symbol_identity, instrument_identity,
sanitized_payload, payload_digest, reason_codes,
fixture_schema_version, normalized_schema_version,
configuration_version, correlation_id, created_at
```

Make `ingestion_key` unique. Index `(source, data_kind, symbol_identity, ingested_at)`, `reason_codes`, and `correlation_id`. On SQLite create `market_data_quarantine_no_update` and `market_data_quarantine_no_delete` triggers using the same `RAISE(ABORT, 'market_data_quarantine is append-only')` pattern as `journal_events`. Downgrade drops triggers, table, indexes, then the snapshot fields.

**Step 4: Run migration tests and verify GREEN**

Run: `./.venv/bin/pytest tests/test_migrations.py -v`

Expected: PASS, including `alembic command.check`.

**Step 5: Write failing append-only database tests**

Insert a quarantine row through SQLAlchemy, then attempt raw SQL UPDATE and DELETE in separate transactions. Both must raise `IntegrityError` containing `append-only`.

**Step 6: Run append-only test and verify RED or GREEN for the intended reason**

Run: `./.venv/bin/pytest tests/market_data/test_quarantine_storage.py -v`

Expected before triggers are correct: FAIL because mutation succeeds. Expected after the implementation in Step 3: PASS. If it is already green, temporarily remove one trigger locally to prove the test fails, then restore it before continuing.

**Step 7: Run focused verification**

Run: `./.venv/bin/pytest tests/test_migrations.py tests/market_data/test_quarantine_storage.py -v`

Expected: PASS.

**Step 8: Commit**

```bash
git add apps/api/migrations/versions/20260718_0002_market_data_replay.py apps/api/src/market_trader/db/models.py apps/api/tests/test_migrations.py apps/api/tests/market_data/test_quarantine_storage.py
git commit -m "feat: migrate market data quarantine storage"
```

---

### Task 12: Persist Replay Outcomes Transactionally And Idempotently

**Files:**
- Modify: `apps/api/src/market_trader/repositories/market_data.py`
- Modify: `apps/api/src/market_trader/market_data/sinks.py`
- Modify: `apps/api/tests/test_market_data_repository.py`
- Create: `apps/api/tests/market_data/test_repository_sink.py`

**Step 1: Write failing repository tests**

Update existing snapshot commands for `data_kind` and `ingestion_key`. Add tests for lookup by ingestion key, append-only quarantine creation, sanitized payload persistence, stable reason codes, and exactly one audit event for each new snapshot/quarantine row. Assert duplicate writes return the existing outcome without another audit event, while the same ingestion key with a different digest raises a typed conflict.

```python
def test_quarantine_and_audit_write_are_one_transaction(tmp_path: Path) -> None:
    engine = migrated_engine(tmp_path)
    with Session(engine) as session:
        repository = MarketDataRepository(session)
        repository.quarantine(quarantine_command())
        assert len(AuditRepository(session).list_for_subject("market_data_quarantine", ANY_ID)) == 1
        session.rollback()

    with Session(engine) as session:
        assert MarketDataRepository(session).get_quarantine_by_ingestion_key(KEY) is None
```

**Step 2: Run repository tests and verify RED**

Run: `./.venv/bin/pytest tests/test_market_data_repository.py tests/market_data/test_repository_sink.py -v`

Expected: FAIL because repository fields, quarantine methods, and repository sink are missing.

**Step 3: Extend `MarketDataRepository`**

Add domain records and create commands for snapshots and quarantine. `store_snapshot` and `quarantine` first query by ingestion key:

- Matching payload digest/outcome returns the existing record and appends no audit event.
- A different digest raises `IngestionConflictError` and does not overwrite data.
- A new record flushes its row and corresponding audit event in the caller's transaction.

Use audit event types `market_data_snapshot.stored` and `market_data_observation.quarantined`. Audit payloads include schema version, source, event ID, data kind, ingestion key, quality state/reasons, and sanitized payload digest, but not full rejected payloads.

**Step 4: Implement `RepositoryIngestionSink`**

Require a SQLAlchemy `Session` and resolve accepted symbols through `SymbolRepository.get_symbol_by_display_symbol`. Missing symbols raise `ReplayInfrastructureError("unknown symbol: <symbol>")`; Milestone 3 does not auto-discover or auto-create symbols. Convert normalized models to canonical JSON-safe payloads with decimals encoded as strings. Rejections may persist without a symbol row because quarantine stores parseable textual identity.

The sink must flush each event through the repository but leave commit/rollback ownership to the replay command or application service. Duplicate outcomes are counted without writes.

**Step 5: Run focused verification and verify GREEN**

Run: `./.venv/bin/pytest tests/test_market_data_repository.py tests/market_data/test_repository_sink.py -v`

Expected: PASS.

Run: `./.venv/bin/mypy src/market_trader/repositories/market_data.py src/market_trader/market_data/sinks.py`

Expected: PASS.

**Step 6: Commit**

```bash
git add apps/api/src/market_trader/repositories/market_data.py apps/api/src/market_trader/market_data/sinks.py apps/api/tests/test_market_data_repository.py apps/api/tests/market_data/test_repository_sink.py
git commit -m "feat: persist replay outcomes idempotently"
```

---

### Task 13: Add Representative Recorded Fixture Datasets And Conformance Tests

**Files:**
- Create: `apps/api/fixtures/market_data/regular-session/manifest.json`
- Create: `apps/api/fixtures/market_data/regular-session/quotes.ndjson`
- Create: `apps/api/fixtures/market_data/regular-session/candles.ndjson`
- Create: `apps/api/fixtures/market_data/regular-session/option-chains.ndjson`
- Create: `apps/api/fixtures/market_data/quality-boundaries/manifest.json`
- Create: `apps/api/fixtures/market_data/quality-boundaries/observations.ndjson`
- Create: `apps/api/fixtures/market_data/corporate-actions/manifest.json`
- Create: `apps/api/fixtures/market_data/corporate-actions/actions.ndjson`
- Create: `apps/api/fixtures/market_data/provider-recovery/manifest.json`
- Create: `apps/api/fixtures/market_data/provider-recovery/provider-state.ndjson`
- Create: `apps/api/tests/market_data/test_fixture_conformance.py`

**Step 1: Write failing conformance tests**

Parameterize every production fixture directory. Load, validate, replay twice into new in-memory sinks, and assert manifest counts and optional digest match exactly. Add scenario-presence assertions so a fixture cannot accidentally lose required coverage:

```python
@pytest.mark.parametrize("dataset_path", production_datasets())
def test_production_fixture_replays_deterministically(dataset_path: Path) -> None:
    dataset = FixtureDataset.load(dataset_path)
    first = replay_in_memory(dataset)
    second = replay_in_memory(dataset)
    assert first == second
    assert first.counts == dataset.manifest.expected_counts
    assert first.result_digest == dataset.manifest.expected_result_digest
```

The scenario inventory must include regular quotes/candles/chains; equality and one-microsecond-past freshness; halt/non-updating state; wide, locked, crossed, and incomplete markets; all four supported corporate actions; standard and unsupported option deliverables; missing/invalid/malformed/unknown schema data; duplicate/out-of-order/future events; provider unavailable/throttled/partial/recovery; DST and early-close candle dates.

**Step 2: Run the test and verify RED**

Run: `./.venv/bin/pytest tests/market_data/test_fixture_conformance.py -v`

Expected: FAIL because production fixtures are missing.

**Step 3: Create the smallest complete fixture corpus**

Keep values synthetic and fixed in 2026. Use source `recorded-fixture`, configuration `market-data-fixtures-v1`, and stable event IDs. Do not include real account identifiers, cookies, headers, tokens, or credentials. Group related scenarios into the four datasets above rather than creating a directory per edge case.

For intentionally malformed JSON, declare a separate validation-only fixture under `apps/api/tests/market_data/fixtures`; production fixture streams must be parseable so replay can reach event-level quarantine behavior. After each stream is final, calculate its digest with:

Run: `shasum -a 256 fixtures/market_data/<dataset>/<stream>.ndjson`

Expected: one SHA-256 value to place in the manifest. Do not use a script that rewrites manifests implicitly.

**Step 4: Record expected replay digests explicitly**

Run each dataset through the in-memory replay library once, inspect the machine-readable result, and place its digest/counts into the manifest. Then rerun the conformance tests; changing implementation behavior later must require an intentional fixture expectation review.

**Step 5: Run focused verification and verify GREEN**

Run: `./.venv/bin/pytest tests/market_data/test_fixture_conformance.py -v`

Expected: PASS.

Run: `rg -ni 'authorization|cookie|password|secret|api[_-]?key|account[_-]?id' fixtures/market_data`

Expected: no output.

**Step 6: Commit**

```bash
git add apps/api/fixtures/market_data apps/api/tests/market_data/test_fixture_conformance.py
git commit -m "test: add deterministic market data fixtures"
```

---

### Task 14: Add A Database-Free Validation And Explicit Replay CLI

**Files:**
- Create: `apps/api/src/market_trader/market_data/cli.py`
- Create: `apps/api/tests/market_data/test_cli.py`
- Modify: `apps/api/Dockerfile`

**Step 1: Write failing CLI tests**

Invoke `cli.main([...])` directly and use subprocess for one module-entry smoke test. Cover:

- `validate <dataset>` performs full load and in-memory replay validation with no database URL.
- `replay <dataset>` defaults to an in-memory sink.
- `replay <dataset> --database-url sqlite:///...` migrates/uses the database and repository sink.
- Persistent replay fails clearly for an unknown symbol and rolls back.
- Replaying twice after seeding symbols returns identical digest and adds no duplicate snapshot, quarantine, or audit rows.
- Dataset/infrastructure failures return nonzero status and sanitized JSON errors.

```python
def test_validate_prints_machine_readable_summary(capsys: pytest.CaptureFixture[str]) -> None:
    exit_code = main(["validate", str(REGULAR_SESSION)])
    payload = json.loads(capsys.readouterr().out)
    assert exit_code == 0
    assert payload["dataset_id"] == "regular-session"
    assert payload["result_digest"]
    assert "database" not in payload
```

**Step 2: Run the test and verify RED**

Run: `./.venv/bin/pytest tests/market_data/test_cli.py -v`

Expected: FAIL because the CLI is missing.

**Step 3: Implement the standard-library CLI**

Use `argparse`; add no runtime dependency. Both commands load and verify the complete manifest. `validate` and default `replay` use an in-memory sink. Only `--database-url` selects the repository sink. For persistent replay, run Alembic upgrade through existing `alembic_config`, open one session, replay, commit on success, and roll back on any exception. Print exactly one compact sorted JSON object to stdout. Print sanitized structured errors to stderr and return `2` for dataset errors or `3` for infrastructure errors.

Expose:

```text
python -m market_trader.market_data.cli validate <dataset>
python -m market_trader.market_data.cli replay <dataset>
python -m market_trader.market_data.cli replay <dataset> --database-url sqlite:///path.db
```

Do not read provider credentials and do not add any network client.

**Step 4: Package fixtures in the runtime container**

Add `COPY fixtures ./fixtures` to `apps/api/Dockerfile` after source/migration copies so operational validation can run against `/app/fixtures/market_data/...` as the non-root app user.

**Step 5: Run focused verification and verify GREEN**

Run: `./.venv/bin/pytest tests/market_data/test_cli.py -v`

Expected: PASS.

Run: `./.venv/bin/python -m market_trader.market_data.cli validate fixtures/market_data/regular-session`

Expected: exit 0 and one JSON summary with matching expected counts and digest.

**Step 6: Commit**

```bash
git add apps/api/src/market_trader/market_data/cli.py apps/api/tests/market_data/test_cli.py apps/api/Dockerfile
git commit -m "feat: add offline market data replay CLI"
```

---

### Task 15: Document, Smoke-Test, And Close Milestone 3

**Files:**
- Create: `docs/milestone-3-market-data-replay.md`
- Modify: `scripts/verify-foundation.sh`
- Modify: `docs/development-roadmap.md`
- Test: `apps/api/tests/test_container_configuration.py`

**Step 1: Write failing operational checks**

Extend `test_container_configuration.py` to assert the API Dockerfile copies fixture assets and still runs as non-root. Extend the smoke script expectation test, if present, or add a direct shell subprocess test that checks the validation command can execute from the API working directory.

Run: `cd apps/api && ./.venv/bin/pytest tests/test_container_configuration.py -v`

Expected: FAIL until Dockerfile and verification script expectations are aligned.

**Step 2: Write the operator runbook**

Document macOS/Linux commands for:

- Installing backend development dependencies.
- Validating and replaying fixtures in memory.
- Creating a local SQLite database, migrating it, and seeding required symbols.
- Explicit persistent replay and idempotent rerun.
- Inspecting snapshots, quarantine reasons, and associated audit events.
- Adding a fixture safely, calculating hashes, and reviewing expected digests.
- Interpreting stale, quarantined, duplicate, throttled, unavailable, and recovery states.
- Confirming that Milestone 3 contains no Schwab credentials or network access.

Use CST/CDT only for user-facing local examples and label it `America/Chicago`; all fixture/source timestamps remain aware UTC and exchange session labels remain Eastern.

**Step 3: Extend foundation verification**

After existing API/UI checks, run fixture validation inside the API container:

```bash
docker compose exec -T api \
  python -m market_trader.market_data.cli validate \
  /app/fixtures/market_data/regular-session >/dev/null
```

Keep the existing health and frontend checks unchanged.

**Step 4: Update roadmap status only after all verification passes**

Change Milestone 3 from `Planning in progress` to `Complete`. Add a concise completion note pointing to the approved spec, this implementation plan, and the operator runbook. Set the next planning action to Milestone 4; do not begin Milestone 4 implementation in this branch.

**Step 5: Run backend quality gates**

Run: `cd apps/api && ./.venv/bin/ruff check src tests`

Expected: PASS.

Run: `cd apps/api && ./.venv/bin/mypy src`

Expected: PASS.

Run: `cd apps/api && ./.venv/bin/pytest`

Expected: PASS with project coverage threshold maintained or improved.

**Step 6: Run frontend regression gates**

Run: `cd apps/web && npm test -- --run`

Expected: PASS.

Run: `cd apps/web && npm run build`

Expected: PASS. Use the repository-supported Node version if the host's Node version produces an engine warning.

**Step 7: Run container and smoke verification**

Run from repository root: `docker compose up --build -d`

Expected: services become healthy.

Run: `./scripts/verify-foundation.sh`

Expected: `Foundation verification passed at http://127.0.0.1:8080`.

Run: `docker compose down`

Expected: containers and network stop cleanly.

**Step 8: Inspect the complete change**

Run: `git status --short`

Expected: only intentional Milestone 3 files are modified or untracked.

Run: `git diff --check`

Expected: no output.

Run: `git diff --stat main...HEAD`

Expected: scoped Milestone 3 implementation, tests, fixtures, migration, and docs.

**Step 9: Commit documentation and milestone status**

```bash
git add docs/milestone-3-market-data-replay.md docs/development-roadmap.md scripts/verify-foundation.sh apps/api/tests/test_container_configuration.py
git commit -m "docs: complete milestone 3 market data replay"
```

**Step 10: Request final review**

Use `superpowers:requesting-code-review` against the approved specification and this plan. Resolve verified findings with `superpowers:receiving-code-review`, rerun the affected focused tests, then rerun the full quality gates before publishing the branch.

---

## Completion Checklist

- [ ] No Schwab SDK, credential, account, or network-provider code was added.
- [ ] All normalized timestamps are aware UTC and all monetary/ratio values are `Decimal` before serialization.
- [ ] Freshness boundaries, five-second future tolerance, daily exchange-calendar expiry, and blocking stale behavior are tested.
- [ ] Fixture order is preserved and replay time comes only from recorded ingestion timestamps.
- [ ] Exact duplicates are idempotent; conflicting and out-of-order events are quarantined deterministically.
- [ ] Sanitization occurs before diagnostics, persistence, and digest calculation.
- [ ] Snapshot and quarantine writes are atomic with their audit events.
- [ ] Quarantine storage is append-only and migration works from a Milestone 2 database.
- [ ] Cache and rate-limit boundaries retain source timestamps and make failure states explicit.
- [ ] Production fixture datasets cover every approved scenario and replay twice identically.
- [ ] CLI, backend, frontend, migration, container, and smoke checks pass.
- [ ] Roadmap marks only Milestone 3 complete and identifies Milestone 4 as the next planning task.
