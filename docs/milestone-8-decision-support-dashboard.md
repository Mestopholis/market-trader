# Milestone 8 Decision-Support Dashboard Expansion

Status: Complete  
Scope: read-only dashboard surfaces for paper-mode decision support

## What This Milestone Adds

Milestone 8 adds a compact dashboard that exposes the current market state,
scanner candidates, candidate trace details, risk summaries, journal events, and
aggregate analytics through read-only API routes and React views.

The dashboard is designed for inspection and traceability. It does not approve,
preview, submit, buy, sell, execute, connect a broker, clear locks, or arm live
mode.

The dashboard path covers:

- `GET /api/dashboard/overview` for paper mode, market state, source states,
  warnings, and recent candidate summaries;
- `GET /api/dashboard/candidates` for bounded scanner candidate rows, local
  filters, score components, states, and block reasons;
- `GET /api/dashboard/candidates/{candidate_key}` for scanner, catalyst,
  options, and risk trace sections with versions and digests;
- `GET /api/dashboard/risk` for latest checks, active locks, risk-state
  distribution, and the tax-warning disclaimer;
- `GET /api/dashboard/journal` for append-only event summaries with bounded,
  redacted payload text;
- `GET /api/dashboard/analytics` for candidate counts, strategy mix, block
  reasons, stale counts, and risk-status distribution.

## Local Startup

From the repository root:

```bash
cp .env.example .env
docker compose up --build -d
open http://127.0.0.1:8080
```

Stop the local stack with:

```bash
docker compose down
```

The container startup keeps `MARKET_TRADER_TRADING_MODE=paper`. The API
container applies Alembic migrations before serving FastAPI.

## Developer Verification

From `apps/api`:

```bash
./.venv/bin/ruff check src tests scripts
./.venv/bin/mypy src tests scripts
./.venv/bin/pytest -q
./.venv/bin/alembic upgrade head
```

From `apps/web`:

```bash
npm run lint
npm test
npm run build
```

From the repository root with Docker running:

```bash
docker compose up --build -d
./scripts/verify-foundation.sh
docker compose down
```

`scripts/verify-foundation.sh` verifies paper mode, health, market state, the
dashboard overview contract, the React root, and deterministic fixture
validation for market data, scanner, catalysts, options analysis, and risk.

## Dashboard Views

The paper-mode banner remains visible across the dashboard. Each panel renders
loading, stale, partial, unavailable, and empty states without exposing trading
actions.

The dashboard tabs are:

- `Overview`: source status, market state, candidate counts, warnings, and
  recent candidates.
- `Scanner`: candidate table with local display filters and score-component
  visibility.
- `Candidate Detail`: trace sections for scanner evidence, catalysts, options
  analysis, and risk decisions.
- `Risk`: latest checks, active locks, reservations, sizing context, exposure,
  and the required tax disclaimer.
- `Journal`: append-only event summaries with redacted payload text and
  correlation identifiers.
- `Analytics`: aggregate counts for states, strategies, block reasons, stale
  data, and risk statuses.

## Data-State Meanings

- `ready`: the dashboard has usable data for the view.
- `partial`: some downstream records are missing, but available sections remain
  inspectable.
- `stale`: the view is based on old source data and must not be treated as a
  fresh decision signal.
- `unavailable`: the view has no usable data or a dependency cannot provide a
  safe read model.

All API timestamps are aware UTC values. The UI labels market-time context
explicitly rather than relying on implicit local offsets.

## Fixture Expectations

The dashboard can render against an empty database and against deterministic
records produced by existing fixture pipelines. Missing downstream records must
surface as `partial`, `stale`, or `unavailable` states rather than hidden
success.

Fixture and journal payload summaries must remain bounded and redacted. Raw
payload-like fields containing secret, token, password, credential, or API-key
terms are rejected from dashboard DTOs.

## Safety Boundaries

Dashboard routes are GET-only and return no-store cache headers. Safety tests
assert that `/api/dashboard` exposes no POST, PUT, PATCH, or DELETE methods and
that dashboard OpenAPI contracts do not contain approval, broker, order,
credential, or live-mode action fields.

Frontend safety tests assert that rendered dashboard roles and labels do not
expose approval, preview, broker-connection, order-submission, lock-clearing, or
live-mode controls.

## Explicit Non-Capabilities

Milestone 8 does not implement:

- approval actions;
- broker credentials or OAuth;
- broker account reads;
- broker previews;
- paper order submission;
- live order submission;
- lock reset controls;
- live-mode arming;
- Schwab integration;
- tax advice.
