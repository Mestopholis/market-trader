# Milestone 5 Catalysts, Events, News, And Filings

Milestone 5 adds deterministic company news, earnings, SEC filing, economic
release, optional social, event-risk, cited-summary, and scanner catalyst
contracts. Production conformance fixtures run without a database or network.

The application remains paper-only. This milestone contains no Schwab client,
credential, account access, approval action, option selection, sizing, or order
submission path. External text and summaries cannot confirm catalysts, set
direction, satisfy scanner gates, or change scores.

## Backend Setup

Python 3.12 or 3.13 is supported on macOS and Linux. From the repository root:

```bash
cd apps/api
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -e '.[dev]'
```

Source timestamps are stored as aware UTC. Exchange sessions use XNYS and
`America/New_York`. User-facing examples use `America/Chicago`, which selects CST
or CDT for the date. Do not replace named timezones with fixed UTC offsets.

## Offline Validation And Replay

Validate a production fixture and its stream hashes, policy hashes, record counts,
reasons, and frozen result digest:

```bash
cd apps/api
./.venv/bin/python -m market_trader.catalysts.cli validate \
  fixtures/catalysts/company-and-earnings
```

Replay the same fixture entirely in memory:

```bash
./.venv/bin/python -m market_trader.catalysts.cli replay \
  fixtures/catalysts/company-and-earnings
```

The four production groups are `company-and-earnings`, `sec-and-amendments`,
`macro-risk-windows`, and `social-summary-and-failures`. Commands print one
compact, sorted JSON object. Exit `2` means dataset or policy validation failed,
`3` means persistence or infrastructure failed, and `4` means an explicit live
source was unavailable. Diagnostics do not echo provider payloads, database URLs,
SEC contact values, or external text.

## Persistent SQLite Replay

The company fixture references `AAPL`, so seed that symbol before persistence.
Migrations and all catalyst writes are performed before the transaction commits:

```bash
cd apps/api
export CATALYST_DB='sqlite:///./data/milestone5.db'
mkdir -p data
MARKET_TRADER_DATABASE_URL="$CATALYST_DB" ./.venv/bin/alembic upgrade head
```

```bash
MARKET_TRADER_DATABASE_URL="$CATALYST_DB" ./.venv/bin/python - <<'PY'
import os
from datetime import UTC, datetime

from sqlalchemy.orm import Session

from market_trader.db.engine import create_engine_from_url
from market_trader.repositories.symbols import SymbolCreate, SymbolRepository

engine = create_engine_from_url(os.environ["MARKET_TRADER_DATABASE_URL"])
now = datetime.now(UTC)
with Session(engine) as session, session.begin():
    repository = SymbolRepository(session)
    if repository.get_symbol_by_display_symbol("AAPL") is None:
        repository.create_symbol(SymbolCreate(
            display_symbol="AAPL",
            instrument_type="equity",
            exchange="XNAS",
            is_active=True,
            first_observed_at=now,
            last_observed_at=now,
            metadata_payload={"schema_version": 1},
            metadata_schema_version=1,
            correlation_id="milestone5-local-seed",
        ))
engine.dispose()
PY
```

Run the persistent replay twice:

```bash
./.venv/bin/python -m market_trader.catalysts.cli replay \
  fixtures/catalysts/company-and-earnings \
  --database-url "$CATALYST_DB"
```

An exact rerun returns the same result digest without duplicate source runs,
observations, decisions, summaries, or audit events. A stable-key digest conflict
or missing symbol rolls back the complete transaction.

## Inspect Stored Outcomes

Use read-only SQLite queries against the local database:

```bash
sqlite3 data/milestone5.db \
  'SELECT run_key, source_id, as_of, state, result_digest FROM catalyst_source_runs;'

sqlite3 data/milestone5.db \
  'SELECT source_id, event_family, event_category, published_at FROM catalyst_observations ORDER BY published_at;'

sqlite3 data/milestone5.db \
  'SELECT source_id, reasons, ingested_at FROM catalyst_quarantine ORDER BY ingested_at;'

sqlite3 data/milestone5.db \
  'SELECT scope, materiality, direction, confirmation, risk_state FROM catalyst_decisions;'

sqlite3 data/milestone5.db \
  'SELECT provider_id, generated_at, summary_key FROM catalyst_summaries;'

sqlite3 data/milestone5.db \
  "SELECT event_type, COUNT(*) FROM journal_events WHERE event_type LIKE 'catalyst_%' GROUP BY event_type;"
```

Observations and decisions retain stable identity, source references, policy
versions, timestamps, correlation identifiers, and digests. Quarantine records
contain bounded sanitized payloads. Summary segments must cite accepted
observations and remain non-authoritative.

## Explicit SEC And BLS Fetches

Network access is never used by `validate` or `replay`. A fetch requires an
explicit source and timezone-aware `--as-of` value. SEC also requires an
identified contact value for its user agent:

```bash
./.venv/bin/python -m market_trader.catalysts.cli fetch sec \
  --as-of '2026-07-19T15:00:00-05:00' \
  --sec-contact 'operator@example.com' \
  --symbols AAPL MSFT

./.venv/bin/python -m market_trader.catalysts.cli fetch bls \
  --as-of '2026-07-19T15:00:00-05:00'
```

The contact value is supplied at runtime and must not be committed. Adapters allow
only configured official HTTPS origins, bounded response sizes, no redirects,
source-specific rate limits, and bounded retries. Limit exhaustion, malformed
responses, or outages return a typed source failure. A later accepted event marks
recovery; unavailable required evidence remains blocking rather than becoming
neutral or confirmed. Fetches produce normalized counts and a digest but do not
persist automatically.

## Policy And Fixture Changes

Catalyst policy files live in `apps/api/config/catalysts`. Each declares an exact
version and content hash. Policy hashes are part of fixture validation and replay
identity. To change a rule:

1. Change only the reviewed rule and assign its reviewed version.
2. Recalculate the canonical content hash in the policy file.
3. Regenerate fixtures with
   `./.venv/bin/python scripts/generate_catalyst_fixtures.py`.
4. Review stream hashes, counts, scenarios, reason digest, and result digest.
5. Run `./.venv/bin/pytest tests/catalysts -q` before committing.

Fixtures must stay synthetic, ordered by nondecreasing replay time, and bounded by
their explicit `as_of`. Never include authorization headers, cookies, secrets,
tokens, account data, real article or filing text, customer data, approval data, or
order data. Injection-like fixture text is inert data and cannot become an
instruction.

## Timing And Risk Interpretation

- UTC is the stored and compared timestamp standard.
- XNYS sessions and earnings timing use `America/New_York`.
- Operator displays use `America/Chicago`; daylight-saving changes are handled by
  the timezone database.
- Missing or conflicting earnings schedules block symbol risk decisions.
- High-impact macro windows are market-wide and include both boundaries.
- Early closes and DST transitions are evaluated from the exchange calendar.
- Social-only evidence is unconfirmed and cannot satisfy catalyst requirements.

## Container Verification

From the repository root:

```bash
cp .env.example .env
docker compose up --build -d
./scripts/verify-foundation.sh
docker compose down
```

The non-root API image packages `/app/config/catalysts` and
`/app/fixtures/catalysts`. The smoke script validates the company-and-earnings
fixture offline. It does not require Schwab, FRED/BEA, news, social, or model
credentials and does not read account, approval, or order data.
