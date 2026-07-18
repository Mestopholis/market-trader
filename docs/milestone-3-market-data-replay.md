# Milestone 3 Market Data And Replay

Milestone 3 provides provider-neutral quote, candle, option-chain, corporate-action,
and provider-state contracts. Recorded fixtures can drive deterministic validation
and replay without a database or network connection. Persistent replay is explicit,
transactional, and idempotent.

The application remains paper-only. This milestone contains no Schwab credentials,
SDK, network client, account access, or order behavior.

## Backend Setup

Python 3.12 or 3.13 is supported on macOS and Linux. From the repository root:

```bash
cd apps/api
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -e '.[dev]'
```

Fixture and source timestamps are aware UTC. Exchange sessions are calculated in
`America/New_York`. User-facing examples use `America/Chicago`, which automatically
selects CST or CDT for the date; do not use a fixed UTC offset for Chicago time.

## Offline Validation And Replay

Validate the regular-session fixture and its expected counts and digest:

```bash
cd apps/api
./.venv/bin/python -m market_trader.market_data.cli validate \
  fixtures/market_data/regular-session
```

Replay into an in-memory sink. This is also database-free:

```bash
./.venv/bin/python -m market_trader.market_data.cli replay \
  fixtures/market_data/quality-boundaries
```

Both commands print one compact JSON object. Exit code `2` identifies a fixture or
manifest error. Exit code `3` identifies a persistence or repository error. Error
output is sanitized and does not include raw malformed payloads.

## Persistent SQLite Replay

The regular-session dataset references `SPY`, `QQQ`, and `IWM`. Persistent replay
does not auto-create symbols. Migrate a dedicated local database and seed those
symbols through the repository so creation is audited:

```bash
cd apps/api
export MARKET_DATA_DB='sqlite:///./data/milestone3.db'
mkdir -p data
MARKET_TRADER_DATABASE_URL="$MARKET_DATA_DB" ./.venv/bin/alembic upgrade head
```

Seed the symbols once:

```bash
MARKET_TRADER_DATABASE_URL="$MARKET_DATA_DB" ./.venv/bin/python - <<'PY'
import os
from datetime import UTC, datetime

from sqlalchemy.orm import Session

from market_trader.db.engine import create_engine_from_url
from market_trader.repositories.symbols import SymbolCreate, SymbolRepository

engine = create_engine_from_url(os.environ["MARKET_TRADER_DATABASE_URL"])
now = datetime.now(UTC)
with Session(engine) as session:
    repository = SymbolRepository(session)
    for display_symbol in ("SPY", "QQQ", "IWM"):
        if repository.get_symbol_by_display_symbol(display_symbol) is None:
            repository.create_symbol(SymbolCreate(
                display_symbol=display_symbol,
                instrument_type="equity",
                exchange="ARCX",
                is_active=True,
                first_observed_at=now,
                last_observed_at=now,
                metadata_payload={"schema_version": 1},
                metadata_schema_version=1,
                correlation_id=f"local-seed-{display_symbol}",
            ))
    session.commit()
engine.dispose()
PY
```

Replay explicitly into the database, then repeat the same command to verify
idempotence:

```bash
./.venv/bin/python -m market_trader.market_data.cli replay \
  fixtures/market_data/regular-session \
  --database-url "$MARKET_DATA_DB"
```

Both runs return the fixture's canonical digest. The second run creates no duplicate
snapshot, quarantine, or audit rows. An unknown symbol aborts and rolls back the
whole replay.

## Inspect Stored Outcomes

Use SQLite's read-only queries against the local development database:

```bash
sqlite3 data/milestone3.db \
  'SELECT data_kind, quality_state, COUNT(*) FROM market_data_snapshots GROUP BY 1,2;'

sqlite3 data/milestone3.db \
  'SELECT data_kind, reason_codes, COUNT(*) FROM market_data_quarantine GROUP BY 1,2;'

sqlite3 data/milestone3.db \
  "SELECT event_type, subject_type, subject_id FROM journal_events WHERE event_type LIKE 'market_data_%' ORDER BY occurred_at;"
```

Snapshot writes and their audit events share one transaction. Quarantine rows are
append-only, contain sanitized payloads and stable reason codes, and may exist without
a known symbol row.

## Quality States

- `valid`: Structurally valid and within the versioned freshness boundary.
- `degraded`: Usable with an explicit limitation, such as a locked market,
  unsupported deliverable, throttled provider, partial service, or recovery state.
- `stale`: Older than the applicable quote, candle, or option-chain boundary. Stale
  critical data blocks downstream use.
- `quarantined`: Malformed, incomplete, conflicting, out of order, or too far in the
  future. Inspect `reason_codes`; do not silently repair or promote it.
- `deduplicated`: The ingestion key and payload digest were already processed. No new
  persistence or audit write is made.

`provider_unavailable` blocks provider-dependent work. `provider_throttled`,
`provider_partial`, and `provider_recovering` remain explicit degraded states until an
`available` observation is received. Replay does not retry or contact a provider.

## Add Or Change A Fixture

1. Keep events synthetic, ordered by nondecreasing `ingested_at`, and fixed in time.
2. Use aware UTC timestamps, stable event IDs, and payload schema version `1`.
3. Do not include credentials, account identifiers, cookies, headers, or tokens.
4. Calculate each final stream hash with
   `shasum -a 256 fixtures/market_data/<dataset>/<stream>.ndjson` and update its manifest.
5. Run the CLI once, review outcome counts and reasons, and intentionally update the
   manifest's expected digest only when the behavior change is approved.
6. Run `pytest tests/market_data/test_fixture_conformance.py -q` and the credential-key
   scan documented in the implementation plan.

Never generate expected hashes or digests implicitly during tests. A changed digest is
a review checkpoint, not an automatically accepted update.

## Container Verification

From the repository root:

```bash
cp .env.example .env
docker compose up --build -d
./scripts/verify-foundation.sh
docker compose down
```

The smoke script validates the packaged regular-session fixture inside the non-root API
container. No network market-data source is used.
