# Milestone 3: Provider-Neutral Market Data And Replay Specification

Date: July 18, 2026
Status: Approved
Roadmap milestone: [Milestone 3: Provider-neutral market data and replay](../development-roadmap.md)

## Purpose

Establish project-owned market-data contracts, deterministic fixture ingestion,
validation, quarantine, freshness, caching, rate-limit boundaries, and replay
before any external provider or brokerage credential enters the application.

Milestone 3 makes downstream scanner, catalyst, options, and risk development
possible entirely from recorded fixtures. It does not connect to Schwab or any
other network provider. Schwab becomes an optional read-only implementation of
the same contracts in Milestone 11.

## Approved Decisions

- Every network adapter is deferred to Milestone 11.
- Milestone 3 defines capability-specific provider protocols and complete local
  fixture implementations.
- Replays run through an in-process library and standard-library CLI; no replay
  API or frontend is added.
- Fixture datasets use a versioned JSON manifest and ordered NDJSON streams.
- Replay preserves recorded arrival order and advances an injected virtual clock
  by ingestion time.
- Accepted observations use the existing audited market-data snapshot path.
- Rejected observations use a dedicated append-only quarantine table.
- Conservative freshness defaults are versioned and tested at exact boundaries.
- Cache and rate-limit behavior is deterministic and never replaces source
  timestamps with cache-access timestamps.

## Goals

- Define immutable normalized contracts for quotes, candles, option chains, and
  corporate actions.
- Keep provider payloads and terminology outside downstream domain code.
- Represent source, observation time, ingestion time, exchange session date,
  quality, schema version, and configuration version explicitly.
- Validate malformed, incomplete, stale, future-dated, duplicate, and
  out-of-order events consistently.
- Quarantine rejected events with stable reason codes and sanitized evidence.
- Replay regular, degraded, stale, halted, split, wide-spread, and provider-loss
  scenarios deterministically.
- Add idempotent repository persistence for accepted and quarantined events.
- Define cache and rate-limit boundaries suitable for future provider adapters.
- Provide a reusable conformance suite that future Schwab adapters must pass.

## Non-Goals

- Schwab OAuth, tokens, market data, accounts, or orders.
- Any external HTTP, WebSocket, streaming, or bulk-data provider.
- Real-time data collection or background ingestion workers.
- Scanner, strategy, scoring, catalyst, options-analysis, or risk decisions.
- User-facing replay controls or dashboard expansion.
- Provider selection, provider fallback, or production data entitlements.
- Trade approval, simulation, broker preview, or order submission.

## Architecture

Use a typed normalization pipeline with five boundaries:

1. Capability-specific provider protocols return provider-shaped events.
2. Normalizers convert events into project-owned immutable values.
3. Validators assign explicit quality outcomes and reason codes.
4. Sinks persist accepted snapshots or append sanitized quarantine records.
5. Replay orchestrates fixture events using an injected virtual clock.

The replay engine depends on protocols rather than SQLAlchemy. An in-memory sink
supports deterministic tests and downstream development. A repository sink owns
transactional persistence and audit writes.

Suggested package shape:

```text
apps/api/src/market_trader/market_data/
|-- __init__.py
|-- cache.py
|-- cli.py
|-- fixtures.py
|-- freshness.py
|-- models.py
|-- normalization.py
|-- provider.py
|-- quality.py
|-- rate_limit.py
|-- replay.py
`-- sinks.py
```

Exact module names may change in the implementation plan. Provider-shaped
fixture types must not leak into normalized models, repositories, or later
milestones.

## Provider Contracts

Define separate protocols for:

- Quote retrieval.
- Candle retrieval by symbol, interval, and time range.
- Option-chain retrieval by underlying and expiration constraints.
- Corporate-action retrieval by symbol and effective-date range.
- Provider capability and health reporting.

Do not require one provider to implement unsupported capabilities silently.
Capabilities are explicit and immutable. Calling an unavailable capability
returns a project-owned unsupported result rather than an empty successful
dataset.

The fixture provider implements every contract. Milestone 11 may implement
Schwab capabilities independently. If Schwab lacks comprehensive corporate
actions or another required contract, that absence remains explicit until a
separately reviewed source is added.

## Shared Observation Metadata

Every normalized observation contains:

- Source identifier.
- Stable provider or fixture event identifier.
- Aware UTC `observed_at` timestamp from the data source.
- Aware UTC `ingested_at` timestamp from the ingestion boundary.
- Exchange session date when applicable.
- Normalized schema version.
- Configuration version identifier.
- Correlation identifier.
- Quality state and stable quality reason codes.

The host timezone must not affect results. Naive timestamps are rejected.
Monetary and ratio values use `Decimal`; binary floating-point values must not
cross the normalization boundary.

## Quote Contract

A normalized quote contains:

- Symbol identity.
- Bid and ask prices.
- Bid and ask sizes.
- Optional last-trade price, size, and timestamp.
- Optional bid, ask, and trade venue identifiers.
- Source condition codes preserved as normalized strings.
- Shared observation metadata.

Negative values, missing top-of-book sides, or an ask below the bid are invalid.
A locked market may be retained with an explicit degraded reason. A wide spread
is not malformed by itself; it remains measurable input for later liquidity
rules. Halted or non-updating quotes become stale according to freshness policy.

## Candle Contract

A normalized candle contains:

- Symbol identity.
- Explicit interval.
- Inclusive start and exclusive end timestamps.
- Open, high, low, and close prices.
- Volume.
- Optional VWAP and trade count.
- Explicit adjusted or unadjusted state.
- Shared observation metadata.

High must be at least every other price and low must be no greater than every
other price. Volume and trade count cannot be negative. Completed-candle inputs
cannot end after the ingestion clock beyond the approved future tolerance.

Milestone 3 requires one-minute and daily interval fixtures. The models may
represent other intervals without defining production collection frequencies.

## Option-Chain Contract

A normalized option chain contains an underlying symbol, chain observation
metadata, completeness state, and immutable contracts. Each contract contains:

- Stable option symbol or provider-neutral contract identity.
- Expiration date.
- Strike price.
- Put or call type.
- Standard or unsupported deliverable state.
- Bid and ask prices and sizes.
- Optional last trade.
- Optional volume and open interest.
- Optional implied volatility and Greeks.
- Per-contract quality reasons.

Milestone 3 transports optional analytics fields but does not calculate or act
on them. Unsupported or adjusted deliverables are represented explicitly and
cannot be mistaken for standard contracts. Duplicate contract identities,
invalid expirations, negative values, crossed markets, or incomplete identities
are rejected. A provider-marked partial chain is degraded and blocking for
consumers that require a complete chain.

## Corporate-Action Contract

Version one supports typed records for:

- Forward and reverse stock splits.
- Stock dividends represented by a split-style share ratio.
- Cash dividends with amount and currency.

Records include provider identity, symbol, declaration date when supplied,
effective or ex-dividend date, record and payment dates when supplied, and the
relevant ratio or cash amount. Unknown action types are quarantined until a
reviewed schema supports them. Milestone 3 does not adjust historical data or
calculate returns; it only preserves explicit adjustment state and action facts.

## Quality States

Normalized ingestion uses four states:

- `valid`: complete and within all required boundaries.
- `degraded`: normalized but missing only explicitly noncritical information or
  carrying a recognized condition such as a locked market or partial dataset.
- `stale`: structurally valid but outside the approved freshness boundary.
- `quarantined`: malformed, unsupported, conflicting, unsafe, or otherwise
  unsuitable for normalized consumption.

Only `valid` and explicitly permitted `degraded` observations enter the primary
snapshot path. `stale` and `quarantined` events are blocking and use the
quarantine path. A consumer must never infer validity from payload presence.

Reason codes are project-owned strings, versioned with quality policy, and may
include multiple reasons. Human-readable provider details may be logged only
after sanitization and must not become API contracts.

## Freshness Policy

Freshness policy version one is identified as `market-data-freshness-v1`.

- Quotes remain valid through 15 seconds after `observed_at`.
- One-minute candles remain valid through 90 seconds after candle end.
- Option chains remain valid through 60 seconds after chain `observed_at`.
- Corporate-action results remain valid through 24 hours after `ingested_at`.
- Equality at the freshness boundary is valid; any later instant is stale.

Daily-candle freshness is based on its completed session and must be defined in
the implementation plan using the exchange calendar rather than a fixed UTC
offset. Freshness evaluation receives an injected clock and performs no host
clock reads.

All critical stale data is blocking. Cache presence, replay speed, database
write time, or frontend access time cannot extend validity.

## Future-Timestamp Tolerance

Provider observations later than the ingestion clock are invalid beyond a small
versioned tolerance for transport and clock skew. The implementation plan must
choose and test the exact tolerance; it must not exceed five seconds in version
one. Events within tolerance retain their original observation timestamp.

## Ordering, Duplicates, And Idempotency

Track an arrival watermark by source, data kind, and instrument or underlying.

- Replay preserves manifest stream order; it does not sort by observation time.
- An observation older than the accepted watermark is out of order and
  quarantined.
- Equal timestamps with distinct event identities are evaluated independently.
- Exact duplicate events are deduplicated by stable ingestion key and canonical
  sanitized payload digest.
- Replaying a dataset cannot duplicate snapshots, quarantine records, or audit
  events.

Idempotency must remain deterministic across processes and database restores.
Random database identifiers may exist internally but cannot affect replay result
digests or normalized equality.

## Fixture Dataset Format

Each dataset directory contains one JSON manifest and one or more NDJSON files.
The manifest contains:

- Dataset identifier and description.
- Fixture schema version.
- Source and configuration version.
- Ordered stream filenames and data kinds.
- SHA-256 digest and expected event count for each stream.
- Expected accepted, degraded, stale, quarantined, and deduplicated counts.
- Optional expected replay result digest.

Each NDJSON line contains one event with:

- Stable `event_id`.
- Data kind.
- `ingested_at` and `observed_at` timestamps.
- Provider-shaped payload.

Ingestion timestamps must be nondecreasing in recorded arrival order. Observation
timestamps may move backward so out-of-order behavior can be tested. Fixtures
must use fixed dates and must not derive values from the current day.

## Required Fixture Scenarios

- Normal regular-session quotes, one-minute candles, and option chains.
- Freshness equality and one-unit-past-boundary cases.
- Halted or non-updating symbols.
- Wide, locked, crossed, and incomplete markets.
- Split, reverse split, stock dividend, and cash dividend records.
- Standard and unsupported option deliverables.
- Missing fields, invalid values, malformed JSON, and unknown schemas.
- Duplicate, out-of-order, and future-dated events.
- Provider unavailable, throttled, partial, and recovery sequences.
- Daylight-saving and early-close session dates where candle/session behavior is
  relevant.

Fixtures must not contain production credentials, account identifiers, cookies,
or copied authorization headers.

## Replay Engine

The replay engine:

- Loads and validates the complete manifest before processing events.
- Verifies file hashes and event counts.
- Uses an injected replay clock.
- Advances the clock to each recorded ingestion timestamp.
- Processes streams in declared order without observation-time sorting.
- Sends every event through the production normalization and quality pipeline.
- Writes outcomes through an `IngestionSink` protocol.
- Returns immutable counts, reason summaries, and a deterministic result digest.

The in-memory sink is the default for tests and downstream development. The
repository sink persists accepted and rejected outcomes transactionally.

## CLI Contract

Provide these commands without adding a CLI framework dependency:

```text
python -m market_trader.market_data.cli validate <dataset>
python -m market_trader.market_data.cli replay <dataset>
```

`validate` performs manifest, hash, schema, timestamp, and expected-outcome
checks without database writes. `replay` uses the repository sink by explicit
configuration and prints a concise machine-readable summary. Both commands use
nonzero exit status for dataset or infrastructure failures.

No command contacts a network provider. No command exposes credentials or full
unsanitized rejected payloads.

## Persistence And Migration

Milestone 3 adds an Alembic migration that:

- Adds a stable ingestion key and data-kind field to market-data snapshots.
- Adds uniqueness needed for idempotent ingestion.
- Creates an append-only market-data quarantine table.
- Adds indexes for source, data kind, symbol or instrument identity, ingestion
  time, quality reason, and correlation identifier.

A quarantine record contains:

- Stable identifier and ingestion key.
- Source and event identifier.
- Data kind.
- Observation and ingestion timestamps when parseable.
- Symbol or instrument identity when parseable.
- Sanitized raw JSON payload.
- Canonical sanitized payload digest.
- Stable quality reason codes.
- Fixture and normalized schema versions.
- Configuration version and correlation identifier.

Accepted snapshot and audit writes occur in the same transaction. Quarantine and
its audit event also occur in one transaction. Repository APIs do not expose
update or delete operations for quarantine records.

## Sanitization

Sanitization occurs before persistence, diagnostics, digest calculation, or
replay summaries. It recursively removes or replaces configured secret fields,
including authorization headers, API keys, access tokens, refresh tokens,
cookies, client secrets, and common case or separator variants.

Payload digests are calculated from canonical sanitized JSON. Unknown binary or
non-JSON input is represented by bounded metadata and a digest rather than raw
bytes. Sanitization failures are infrastructure failures and cannot fall back to
storing the original payload.

## Cache Boundary

Define a typed cache protocol and deterministic in-memory implementation.

- Cache keys include source, capability, normalized request identity, and
  relevant configuration version.
- Cache entries retain the source observation and freshness timestamps.
- Cache reads never rewrite `observed_at`, `ingested_at`, or `valid_until`.
- Expired entries return an explicit stale result rather than a cache miss that
  could hide why data is unavailable.
- Cache behavior uses an injected clock.

Milestone 3 does not add a distributed cache or persist cache entries.

## Rate-Limit Boundary

Define a deterministic rate-limit protocol with states:

- `allowed`.
- `delayed`, including the earliest retry time.
- `exhausted`, including a stable reason and reset time when known.

Use an injected clock and a local deterministic implementation for tests. A
future provider adapter translates HTTP 429 or provider quota metadata into this
contract. Rate limiting must not silently serve stale data as fresh.

## Failure Handling

Dataset-level failures abort before event processing:

- Missing or malformed manifest.
- Unknown fixture schema.
- Hash or event-count mismatch.
- Invalid stream order or ingestion timeline.

Event-level data failures are sanitized, quarantined, counted, and replay
continues. Infrastructure failures stop replay and roll back the active
transaction batch:

- Database or migration failure.
- Sanitization failure.
- Corrupt local storage.
- Unexpected sink or audit failure.

Project-owned errors and reason codes cross package boundaries. Raw parser,
SQLAlchemy, or future provider exceptions must not become API contracts.

## Audit Requirements

Every accepted or quarantined persisted event carries a correlation identifier.
Audit records include only bounded normalized metadata, ingestion key, source,
data kind, quality state, and reason codes. They do not duplicate full market
payloads or sanitized quarantine payloads.

Replay summaries include dataset identifier, configuration version, policy
versions, outcome counts, and result digest so a run can be reconstructed without
depending on random database identifiers.

## Testing Strategy

Unit tests cover:

- Every normalized model invariant.
- Decimal and aware UTC normalization.
- Exact freshness and future-tolerance boundaries.
- Quality-state and reason-code assignment.
- Ordering, duplicate, cache, and rate-limit behavior.
- Recursive secret sanitization.

Replay tests:

- Run every required dataset through the in-memory sink.
- Replay each dataset twice and require identical outcomes and digests.
- Prove recorded order is preserved and out-of-order observations are not sorted
  away.
- Prove stale and malformed critical data remains blocking.

Repository and migration tests:

- Upgrade a Milestone 2 database and migrate a clean database.
- Replay twice without duplicate snapshots, quarantine records, or audit events.
- Verify transaction rollback on sink and audit failures.
- Verify quarantine cannot be updated or deleted through repository APIs.

Provider conformance tests define reusable behavior for the fixture provider and
future Schwab adapter. No Milestone 3 test reads the host clock or network.

## Operational Documentation

Add a Milestone 3 runbook covering:

- Fixture authoring and sanitization.
- Manifest hash generation and review.
- CLI validation and replay commands on macOS/Linux.
- Database migration and quarantine inspection.
- Dependency and schema update review.
- Proof that no network provider or credential is configured.

Docker smoke verification must remain paper-only and confirm a representative
fixture can be validated without network access.

## Acceptance Criteria

Milestone 3 is complete when:

- Quotes, candles, option chains, and corporate actions use project-owned typed
  contracts.
- Downstream code can run entirely from fixture providers.
- Every required dataset validates and replays deterministically.
- Exact freshness boundaries are tested and stale critical data blocks use.
- Malformed, incomplete, unsupported, future-dated, and out-of-order payloads
  are sanitized and quarantined with stable reasons.
- Replaying a dataset is idempotent in memory and in SQLite.
- Cache and rate-limit boundaries preserve source timestamps and fail explicitly.
- Migration, repository, audit, static, frontend, Docker, and safety checks pass.
- No network adapter, credential, account path, or order behavior exists.

## Explicitly Deferred

- Schwab read-only market data and OAuth: Milestone 11.
- Candidate generation and scoring: Milestone 4.
- News, filings, and event providers: Milestone 5.
- Option analysis and spread construction: Milestone 6.
- Risk and sizing decisions: Milestone 7.
- Market-data dashboard expansion: Milestone 8.
- Background ingestion and operational hardening: later reviewed milestones.
- Account data, approvals, execution, and all live behavior: later milestones as
  ordered by the roadmap.
