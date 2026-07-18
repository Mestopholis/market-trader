# Milestone 2: Market Calendar and Scheduling Specification

Date: July 18, 2026
Status: Approved
Roadmap milestone: [Milestone 2: Market calendar and scheduling foundation](../development-roadmap.md)

## Purpose

Make every time-sensitive Market Trader decision exchange-calendar aware,
timezone explicit, deterministic, and fail-closed. Milestone 2 establishes the
clock, calendar, market-state, entry-window, and schedule-planning contracts that
later market-data, scanner, risk, and paper-execution milestones will consume.

Milestone 2 also adds a compact read-only market-status panel so the calendar
foundation can be inspected through the running application. It must not connect
to a market-data provider, execute background jobs, expose trading controls, or
submit orders.

## Context

Milestone 1 established UTC-aware domain primitives, versioned persistence,
append-only audit records, and repository boundaries. The application currently
shows paper mode, environment, version, and database health, while the backend
exposes only health diagnostics.

The user operates in Chicago. Trading-session rules remain authoritative in the
exchange timezone, `America/New_York`, while the user interface displays both
Eastern Time and Central Time using `America/Chicago`. Fixed UTC offsets or the
labels EST and CST must not be used as year-round timezone substitutes because
both regions observe daylight-saving time.

## Goals

- Add a maintained U.S. equity exchange calendar supporting holidays, early
  closes, and daylight-saving transitions.
- Hide third-party calendar and pandas types behind project-owned contracts.
- Add injectable production and frozen clocks.
- Derive deterministic session dates and market states from aware UTC timestamps.
- Add a versioned entry-window policy that opens 15 minutes after the session
  open and closes 30 minutes before the session close.
- Add deterministic schedule-planning interfaces for scans, refreshes,
  end-of-day work, and recovery work.
- Expose a read-only market-state API and compact status panel.
- Represent stale, invalid, or unavailable calendar state as blocking.

## Non-Goals

- External market-data, news, options, or broker providers.
- Schwab OAuth, account access, order preview, or order submission.
- A background worker, task queue, timer loop, or process scheduler.
- Scanner, scoring, risk, approval, or execution behavior.
- Production scan and refresh frequencies.
- User-editable trading windows or calendar administration.
- A full dashboard, calendar browser, or upcoming-job management screen.
- Live mode or any executable trading control.

## Design Approach

Use `exchange_calendars` with the `XNYS` calendar behind a project-owned
`ExchangeCalendar` protocol. The adapter is responsible for converting library
values into standard-library dates and aware UTC datetimes before returning them
to application code.

The selected library provides a maintained, session-oriented exchange calendar
with UTC opens and closes. Its source is available at
[gerrymanoim/exchange_calendars](https://github.com/gerrymanoim/exchange_calendars).
Calendar rules are local package data; application behavior must not require a
runtime network request.

Alternatives considered:

- `pandas_market_calendars`. It provides useful schedule helpers but exposes a
  broader DataFrame-oriented API than this milestone needs.
- Custom NYSE holiday rules. This avoids a dependency but transfers exceptional
  closure, early-close, and rule-correction risk to the application.

The project-owned interface prevents either library choice from leaking into
domain services, API models, frontend contracts, or later milestones.

## Expected Backend Shape

The implementation should preserve boundaries similar to:

```text
apps/api/src/market_trader/
├── api/
│   └── market_state.py
├── calendar/
│   ├── adapter.py
│   ├── models.py
│   ├── policy.py
│   └── service.py
├── domain/
│   └── time.py
└── scheduling/
    ├── models.py
    └── planner.py
```

Exact names may change in the implementation plan, but third-party calendar and
pandas types must remain inside the adapter module.

## Time Conventions

- All calculations and machine-readable API timestamps use aware UTC datetimes.
- Naive datetimes are rejected at public service boundaries.
- The exchange timezone is the IANA zone `America/New_York`.
- The initial user display timezone is the IANA zone `America/Chicago`.
- The frontend labels exchange values as ET and user-local values as CT.
- UTC offsets must be derived from the applicable date, never hard-coded.
- A session date is the date assigned by the exchange calendar, not a date
  inferred by converting UTC to the host machine's timezone.
- The host operating-system timezone must not change service results.

`MARKET_TRADER_DISPLAY_TIMEZONE` should default to `America/Chicago`. Invalid or
unknown configured zones must stop configuration startup with a clear error.
`XNYS` remains the only supported exchange calendar in this milestone rather
than implying untested multi-exchange support.

## Clock Boundary

Define a `Clock` protocol whose `now()` method returns an aware UTC datetime.

- `SystemClock` is the production implementation.
- `FrozenClock` or an equivalent test implementation returns an explicitly
  supplied value and performs no wall-clock reads.
- Domain services receive a clock through dependency injection.
- Calendar and scheduler tests must not patch global datetime behavior, sleep,
  or depend on the machine clock.

The existing `utc_now()` helper may remain for persistence defaults, but
time-sensitive market behavior must use the injected clock.

## Calendar Contract

The project-owned `ExchangeCalendar` contract must support:

- Looking up a session by exchange session date.
- Resolving the session associated with an aware UTC timestamp.
- Determining whether a date is a session, weekend, or exchange holiday.
- Returning open and close timestamps for a session.
- Identifying an early close by comparing the session close with the calendar's
  regular close.
- Returning previous and next sessions.
- Returning sessions across a bounded date range for schedule planning.

The adapter must use explicit construction bounds suitable for application and
test dates rather than relying on a dependency's moving default date range.
Unsupported dates or dependency errors must be translated into project-owned
exceptions without leaking pandas values or internals.

## Session Model

The internal immutable session value contains:

- Exchange calendar identifier, fixed to `XNYS`.
- Exchange session date.
- UTC market-open timestamp.
- UTC market-close timestamp.
- `is_early_close` flag.

Regular-hours sessions are authoritative. Pre-market and after-hours trading
sessions are outside Milestone 2.

## Entry Window Policy

Version one of the entry policy is identified as `entry-window-v1`.

- Entry-window start is the actual session open plus 15 minutes.
- Entry-window end is the actual session close minus 30 minutes.
- The start boundary is inclusive.
- The end boundary is exclusive.
- A normal 9:30 AM-4:00 PM ET session therefore permits entries from 9:45 AM
  inclusive until 3:30 PM ET exclusive.
- A 9:30 AM-1:00 PM ET early-close session permits entries from 9:45 AM
  inclusive until 12:30 PM ET exclusive.
- Weekends, exchange holidays, unavailable state, and timestamps outside the
  window prohibit entry.

Milestone 2 exposes this decision but does not act on it. Later decisions that
depend on entry eligibility must record the policy version and relevant market
state in their existing auditable input snapshots.

## Market State Service

`MarketStateService` combines the injected clock, exchange calendar, entry
policy, and freshness policy into an immutable snapshot.

Supported states are:

- `closed`: the Eastern calendar date is not an exchange session.
- `pre_market`: the timestamp is before the current session open.
- `opening_buffer`: the session is open but the entry-window start has not been
  reached.
- `entry_open`: the timestamp is inside the approved entry window.
- `entry_closed`: the market remains open but the entry-window end has passed.
- `post_market`: the timestamp is at or after the session close on a session
  date.

`entry_allowed` is true only for `entry_open`. It is never inferred independently
by the API or frontend.

The snapshot includes the current session when one exists, the next session open,
the next state transition, the policy version, the observation timestamp, and a
freshness boundary. At exact boundaries, the new state takes effect immediately.
No minute or second rounding is permitted.

## Freshness Contract

Every market-state snapshot contains:

- `observed_at`: when the state was calculated.
- `next_transition`: the next known market-state boundary.
- `valid_until`: the earliest of the configured freshness interval and the next
  transition.

The initial freshness interval is 60 seconds. A snapshot must never remain valid
across a state transition. Consumers presented with a snapshot after
`valid_until` must treat it as stale and prohibit entry.

The API returns `Cache-Control: no-store`. The frontend refreshes every 30
seconds. If refresh fails, the last value may remain visible only until its
`valid_until`; after that point the panel changes to unavailable rather than
continuing to display an actionable state.

## API Contract

Add a read-only `GET /api/market-state` endpoint. The successful response uses
UTC ISO 8601 timestamps and includes:

- Market state and `entry_allowed`.
- Calendar identifier and policy version.
- Observation, freshness, and next-transition timestamps.
- Current exchange session date when applicable.
- Current session open and close when applicable.
- Entry-window open and close when applicable.
- Early-close indicator.
- Next session date and open timestamp.
- Exchange and display IANA timezone identifiers.

A representative response is:

```json
{
  "market_state": "entry_open",
  "entry_allowed": true,
  "calendar": "XNYS",
  "policy_version": "entry-window-v1",
  "observed_at": "2026-07-20T15:30:00Z",
  "valid_until": "2026-07-20T15:31:00Z",
  "next_transition": "2026-07-20T19:30:00Z",
  "session_date": "2026-07-20",
  "market_open": "2026-07-20T13:30:00Z",
  "market_close": "2026-07-20T20:00:00Z",
  "entry_window_open": "2026-07-20T13:45:00Z",
  "entry_window_close": "2026-07-20T19:30:00Z",
  "is_early_close": false,
  "next_session_date": "2026-07-21",
  "next_session_open": "2026-07-21T13:30:00Z",
  "calendar_timezone": "America/New_York",
  "display_timezone": "America/Chicago"
}
```

Nullable current-session fields are permitted for weekends and holidays.
Unavailable calendar state returns a structured HTTP 503 response with
`entry_allowed: false` and a stable public error code. Dependency exceptions,
stack traces, and host details must not appear in the response.

## Frontend Status Panel

Extend the existing foundation screen with one compact read-only market-status
section. It displays:

- Current market state in text.
- Whether the entry window is open or closed.
- Current time in ET and CT.
- Session open and close in ET and CT.
- Entry-window boundaries in ET and CT.
- Early-close status when applicable.
- Next known transition.

The frontend formats timestamps with `Intl.DateTimeFormat` using the timezone
identifiers from the API contract. It must not calculate market states, entry
eligibility, holidays, or early closes.

Loading, stale, and unavailable states are visually explicit. State must not be
communicated by color alone. The panel adds no buttons, approval actions, or
trading controls and remains subordinate to the permanent paper-mode banner.

## Scheduler Contracts

Milestone 2 defines a deterministic `SchedulePlanner`; it does not run jobs.

Project-owned schedule definitions support:

- Recurring runs constrained to the regular session or entry window.
- One-time runs offset from session open or close.
- Job kinds for `scan`, `refresh`, `end_of_day`, and `recovery`.
- Explicit schedule-policy versions.

The planner accepts a start-exclusive and end-inclusive UTC interval and returns
immutable `ScheduledRun` values. Each run contains:

- Job kind.
- Exchange session date.
- Scheduled UTC timestamp.
- Calendar and schedule-policy versions.
- Deterministic idempotency key derived from the definition and scheduled run.

This interval contract allows a later worker to identify runs that became due
during a delayed tick or restart. The later execution layer decides whether a
missed run executes, expires, or creates recovery work. Milestone 2 does not
persist scheduler watermarks, execute callbacks, retry work, or choose production
cadences.

## Failure Behavior

All ambiguous time behavior fails closed:

- Naive timestamps are rejected.
- Invalid display timezones stop configuration startup.
- Unsupported calendar ranges produce unavailable state.
- Calendar adapter errors produce unavailable state.
- Missing or stale snapshots prohibit entry.
- A frontend refresh failure becomes unavailable when the last snapshot expires.
- No fallback assumes Monday-Friday or regular 9:30 AM-4:00 PM hours.

The API and UI may expose a stable diagnostic category but must not expose
dependency internals. Calendar failure must not change the application's enforced
paper mode.

## Persistence and Audit

No database migration is expected. Calendar sessions, state snapshots, and
planned runs are deterministic derived values and are not persisted merely
because the status endpoint is polled.

Milestone 2 must not create high-volume audit events for status reads. Later
milestones persist the calendar identifier, policy version, session date,
observation timestamp, and relevant boundaries as part of any decision input that
depends on market state. This preserves reconstructability at the point where a
decision becomes material.

## Testing Requirements

Backend tests must use frozen clocks and fixed fixtures covering:

- A normal XNYS session.
- A weekend.
- A full exchange holiday.
- A 1:00 PM ET early close.
- Spring and fall daylight-saving transitions.
- Times immediately before, at, and after every state boundary.
- Previous and next session lookup.
- Aware UTC normalization and naive timestamp rejection.
- Unsupported ranges and adapter failure.
- Fresh and stale snapshots around `valid_until`.
- ET and CT conversion using their IANA zones.

Scheduler tests must cover:

- Recurring runs inside configured session windows.
- Normal and early-close close-relative runs.
- No generated runs on weekends or holidays.
- Deterministic idempotency keys.
- Delayed intervals spanning multiple expected runs.
- Representative scan, refresh, end-of-day, and recovery definitions.

API tests must override clock and calendar dependencies, assert exact values and
boundary behavior, verify `Cache-Control: no-store`, and verify structured
fail-closed responses.

Frontend tests must cover loading, normal session, early close, ET/CT labels,
periodic refresh, stale expiration, and unavailable state. Existing paper-mode,
health, migration, repository, backup/restore, lint, type-check, build, and Docker
verification must continue to pass.

Tests must not use network access, sleeps, the host timezone, or the current wall
clock. Upgrades to `exchange_calendars` require rerunning and reviewing fixed
calendar fixtures because calendar corrections may legitimately change schedules.

## Documentation Requirements

Implementation documentation must explain:

- The XNYS calendar scope and regular-hours-only boundary.
- ET versus CT display behavior.
- Entry-window boundary semantics, including early closes.
- How to run calendar, scheduler, API, and frontend tests on macOS.
- How calendar dependency updates are reviewed.
- That schedule planning does not execute jobs.
- That the application remains paper-only and provider-free.

## Security and Safety Requirements

- No credentials, provider keys, or network calendar services are introduced.
- Calendar errors, stale state, and ambiguous timestamps always prohibit entry.
- The frontend cannot override backend market state or entry eligibility.
- Live mode remains rejected by configuration.
- No API endpoint can launch a job or submit an order.
- Calendar and schedule objects are data, not executable instructions.
- Error responses do not reveal host paths, stack traces, or dependency details.

## macOS Local Development Notes

Use Python 3.12 or 3.13 in the backend virtual environment. Tests and application
commands must use POSIX syntax compatible with macOS and Linux CI. The local
machine timezone must not affect expected values.

Docker Desktop for Mac remains the container runtime. The complete stack must
still start with:

```bash
docker compose up --build -d
./scripts/verify-foundation.sh
```

## Acceptance Criteria

Milestone 2 is complete when:

- Fixed timestamps produce deterministic XNYS session and market-state results.
- Holidays, weekends, early closes, and DST transitions are covered by tests.
- Normal sessions allow entry from 9:45 AM inclusive until 3:30 PM ET exclusive.
- A 1:00 PM early-close session allows entry from 9:45 AM inclusive until
  12:30 PM ET exclusive.
- Exact entry-window boundaries behave as specified.
- ET and CT are both displayed with date-aware offsets.
- Stale or unavailable state always reports `entry_allowed: false`.
- Deterministic schedule plans cover scan, refresh, end-of-day, and recovery job
  kinds without executing work.
- The read-only status panel is accessible, responsive, and contains no trading
  controls.
- Existing Milestone 1 behavior and verification remain green.
- Documentation confirms that providers, background execution, Schwab access,
  approvals, and orders remain unavailable.

## Explicitly Deferred

- Provider-neutral market data and replay: Milestone 3.
- Scanner, regime, and scoring behavior: Milestone 4.
- Catalysts, news, and filings: Milestone 5.
- Options analysis: Milestone 6.
- Risk calculations and sizing enforcement: Milestone 7.
- Full dashboard expansion: Milestone 8.
- Running scheduler workers and paper execution: Milestone 9 or a separately
  reviewed prerequisite plan.
- Reliability hardening and persistent scheduler recovery: Milestone 10.
- Schwab OAuth and read-only integration: Milestone 11.
- Schwab order-contract validation: Milestone 12.
- Proxmox/PostgreSQL deployment: Milestone 13.
- Live-mode arming: Milestone 14.
