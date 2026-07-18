# Milestone 2 Market Calendar

Milestone 2 provides deterministic XNYS session state, entry-window decisions,
schedule planning, and a read-only market-status panel. The application remains
paper-only, provider-free, and broker-free. It cannot access accounts, submit
orders, or expose trading controls.

## Calendar And Time Scope

- `XNYS` regular sessions are authoritative. Pre-market and after-hours sessions
  are not included.
- Calendar calculations use the IANA zone `America/New_York`; the interface
  labels those values ET.
- The user display zone is `America/Chicago`; the interface labels those values
  CT.
- UTC offsets are resolved for each date, so daylight-saving transitions do not
  rely on fixed EST or CST offsets.
- Holidays and early closes come from the pinned `exchange_calendars` dependency
  through a project-owned adapter.

The version-one entry policy is `entry-window-v1`. For a normal 9:30 AM-4:00 PM
ET session, entry is allowed from 9:45 AM inclusive until 3:30 PM exclusive. For
a 9:30 AM-1:00 PM ET early-close session, entry is allowed from 9:45 AM
inclusive until 12:30 PM exclusive. Weekends, exchange holidays, unavailable
calendar state, stale responses, and times outside the window prohibit entry.

Milestone 2 exposes this decision for inspection only. The schedule planner
returns deterministic job definitions and run times; it does not start a worker,
sleep, poll, enqueue work, or execute jobs.

## Start On macOS

Docker Desktop for Mac is the supported full-stack development path. From the
repository root:

```bash
cp .env.example .env
docker compose up --build -d
./scripts/verify-foundation.sh
```

Open `http://127.0.0.1:8080`. Paper mode must remain the first safety signal.
The status panel shows market state, entry-window availability, and applicable
session times in both ET and CT.

If the Docker CLI is not in the shell path, prepend Docker Desktop's CLI path for
the current terminal session:

```bash
export PATH="/Applications/Docker.app/Contents/Resources/bin:$PATH"
```

Stop the stack without deleting the named data volume:

```bash
docker compose down
```

`MARKET_TRADER_DISPLAY_TIMEZONE` defaults to `America/Chicago`. The standard
smoke script verifies that default. Unknown IANA timezone names fail application
configuration instead of silently falling back.

## Backend Verification

Create the environment and install development dependencies if needed:

```bash
cd apps/api
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -e '.[dev]'
```

Run focused calendar, market-state, scheduler, and API tests:

```bash
pytest \
  tests/test_xnys_calendar.py \
  tests/test_market_state_service.py \
  tests/test_schedule_planner.py \
  tests/test_market_state_api.py \
  -q
```

Run the complete backend checks:

```bash
pytest -q
ruff check src tests migrations
mypy src
```

Frontend verification uses Node.js 20.19 or newer, or Node.js 22.12 or newer:

```bash
cd apps/web
npm ci
npm test -- --run
npm run lint
npm run build
```

## Calendar Dependency Review

`exchange_calendars` is bounded to major version 4. A dependency update must be
reviewed before merging because upstream holiday or exceptional-closure data can
change schedule output. After any update:

1. Review upstream release notes and calendar-data corrections.
2. Run the complete backend suite and focused adapter tests.
3. Confirm fixed holiday, early-close, and daylight-saving fixtures still match
   the expected exchange sessions.
4. Verify the Docker smoke test still reports XNYS, `America/New_York`, and
   `America/Chicago`.

Do not replace fixed test dates with values derived from the current day. The
fixtures intentionally make calendar behavior reproducible across machines and
years.

## Safety Boundary

This milestone adds no market-data or news provider, Schwab OAuth, account
access, scanner execution, approval workflow, broker connection, order preview,
or order submission. `MARKET_TRADER_TRADING_MODE=live` remains rejected during
configuration. Later milestones must consume the calendar decision as an input
to their own reviewed, auditable, fail-closed workflows.
