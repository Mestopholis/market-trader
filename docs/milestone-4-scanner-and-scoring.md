# Milestone 4 Scanner And Scoring

Milestone 4 provides a fixed 30-symbol universe, deterministic eligibility,
market-regime classification, five explainable strategy evaluations, candidate
scoring, offline fixture replay, and atomic persistence. The scanner can run
without a database or network connection.

The application remains paper-only. This milestone contains no Schwab client,
credential, account access, approval action, option selection, sizing, or order
submission path.

## Backend Setup

Python 3.12 or 3.13 is supported on macOS and Linux. From the repository root:

```bash
cd apps/api
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -e '.[dev]'
```

Source and fixture timestamps are aware UTC. Exchange sessions use XNYS and
`America/New_York`. User-facing examples use `America/Chicago`, which selects CST
or CDT for the date. Do not replace either timezone with a fixed UTC offset.

## Offline Validation And Scanning

Validate the bullish production fixture and its frozen hashes, counts, reasons,
regime, and result digest:

```bash
cd apps/api
./.venv/bin/python -m market_trader.scanner.cli validate \
  fixtures/scanner/bullish
```

Run the same dataset through the database-free scanner:

```bash
./.venv/bin/python -m market_trader.scanner.cli scan \
  fixtures/scanner/bullish
```

The four production fixture groups are `bullish`, `bearish`,
`neutral-mixed-blocked`, and `boundaries-and-conflicts`. Both commands print one
compact, sorted JSON object. Exit code `2` means the dataset, configuration,
temporal bounds, hashes, or expected result are invalid. Exit code `3` means an
unexpected scanner or persistence failure. Diagnostics are sanitized.

## Persistent SQLite Scan

Persistent scans do not create universe symbols automatically. Migrate a local
database and seed the checked-in universe through the audited symbol repository:

```bash
cd apps/api
export SCANNER_DB='sqlite:///./data/milestone4.db'
mkdir -p data
MARKET_TRADER_DATABASE_URL="$SCANNER_DB" ./.venv/bin/alembic upgrade head
```

```bash
MARKET_TRADER_DATABASE_URL="$SCANNER_DB" ./.venv/bin/python - <<'PY'
import os
from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy.orm import Session

from market_trader.db.engine import create_engine_from_url
from market_trader.repositories.symbols import SymbolCreate, SymbolRepository
from market_trader.scanner.configuration import load_scanner_configuration

database_url = os.environ["MARKET_TRADER_DATABASE_URL"]
configuration = load_scanner_configuration(Path("config/scanner"))
engine = create_engine_from_url(database_url)
now = datetime.now(UTC)
with Session(engine) as session, session.begin():
    repository = SymbolRepository(session)
    for entry in configuration.universe.entries:
        if repository.get_symbol_by_display_symbol(entry.display_symbol) is None:
            repository.create_symbol(SymbolCreate(
                display_symbol=entry.display_symbol,
                instrument_type=entry.security_type,
                exchange=entry.exchange_family,
                is_active=True,
                first_observed_at=now,
                last_observed_at=now,
                metadata_payload={"schema_version": 1},
                metadata_schema_version=1,
                correlation_id=f"local-seed-{entry.display_symbol}",
            ))
engine.dispose()
PY
```

Scan persistently, then repeat the identical command:

```bash
./.venv/bin/python -m market_trader.scanner.cli scan \
  fixtures/scanner/bullish \
  --database-url "$SCANNER_DB"
```

The memory and database paths return the same run key and result digest. An exact
rerun returns the existing run without duplicate decisions, signals, candidates,
or scanner audit events. A stable-key digest conflict or missing symbol/snapshot
rolls back the complete transaction.

## Inspect Stored Decisions

Use read-only SQLite queries against the local database:

```bash
sqlite3 data/milestone4.db \
  'SELECT run_key, session_date, regime_state, regime_score, status FROM scanner_runs;'

sqlite3 data/milestone4.db \
  'SELECT status, COUNT(*) FROM eligibility_decisions GROUP BY status;'

sqlite3 data/milestone4.db \
  'SELECT strategy_id, direction, status, score FROM signals WHERE scanner_run_id IS NOT NULL ORDER BY strategy_id;'

sqlite3 data/milestone4.db \
  'SELECT strategy_id, direction, score, status FROM candidates WHERE scanner_run_id IS NOT NULL;'

sqlite3 data/milestone4.db \
  "SELECT event_type, COUNT(*) FROM journal_events WHERE event_type LIKE 'scanner_%' OR event_type = 'eligibility_decision.recorded' GROUP BY event_type;"
```

The run, eligibility decisions, five strategy outcomes per eligible symbol,
qualified candidates, and audit events share one transaction. Existing Milestone
1 decision APIs remain valid and leave scanner lineage columns null.

## Interpret Results

- Regime states are `bullish`, `bearish`, `neutral`, `mixed`, or `blocked`.
  A blocked regime is not neutral and blocks dependent strategy gates.
- Eligibility is `eligible`, `ineligible`, or `blocked`. Missing, stale,
  conflicting, halted, unavailable-provider, unsupported-adjustment, and
  unresolved-action inputs fail closed.
- Every eligible symbol receives exactly five strategy outcomes: `passed`,
  `failed`, `blocked`, or `not_applicable`.
- Candidates are created only from passing signals with all required gates true
  and a final score of at least `70.000000`.
- Scores are bounded from 0 to 100. Family caps and evidence lineage prevent
  duplicate evidence from increasing a score.
- A candidate is analysis output only. It has no quantity, order side, contract,
  approval, or execution authority.

## Configuration Changes

Scanner configuration lives in `apps/api/config/scanner`. Each file has an exact
version and content hash. To change a policy:

1. Change only the intended rule and review its safety boundary.
2. Assign the reviewed version according to the project versioning policy.
3. Recalculate the canonical content hash and update the file.
4. Regenerate fixtures with
   `./.venv/bin/python scripts/generate_scanner_fixtures.py`.
5. Review every changed stream hash, reason summary, count, regime score, and
   result digest. Do not accept digest churn without explaining the rule change.
6. Run `./.venv/bin/pytest tests/scanner -q` before committing.

Configuration hashes are part of scanner input and run identity. A manifest with
unknown versions or mismatched hashes is rejected before evaluation.

## Fixture Authoring

Fixtures must remain synthetic, fixed in 2026, ordered by nondecreasing ingestion
time, and bounded by their explicit `as_of`. Keep source timestamps in UTC and use
the XNYS calendar for normal, daylight-saving, holiday, and early-close sessions.
Never include credentials, authorization headers, cookies, account identifiers,
provider tokens, article bodies, or customer data.

The generator writes provider-neutral NDJSON, stream hashes, record counts, and
expected scanner results. Tests never regenerate expected values. Checked-in
manifest changes are review checkpoints, and replaying each fixture twice must
produce an identical result digest.

## Container Verification

From the repository root:

```bash
cp .env.example .env
docker compose up --build -d
./scripts/verify-foundation.sh
docker compose down
```

The non-root API image packages `/app/config/scanner` and
`/app/fixtures/scanner`. The smoke script validates the bullish fixture entirely
offline. It does not read a provider URL, Schwab credential, account, approval, or
order setting.
