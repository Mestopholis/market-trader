# Milestone 2: Market Calendar and Scheduling Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add deterministic XNYS session, market-state, entry-window, schedule-planning, API, and read-only ET/CT status-panel behavior without adding providers, background execution, or trading controls.

**Architecture:** Wrap `exchange_calendars` behind project-owned immutable models and a typed protocol. Inject a clock into market-state services, derive fail-closed snapshots and schedule plans in pure domain code, expose one read-only FastAPI endpoint, and render it in a self-contained React status component.

**Tech Stack:** Python 3.12/3.13, FastAPI, Pydantic Settings, `exchange_calendars` 4.13.x, standard-library `zoneinfo`, pytest, Ruff, mypy, React 19, TypeScript, Vitest, Testing Library, Docker Compose.

**Specification:** `docs/plans/2026-07-18-milestone-2-market-calendar-and-scheduling-spec.md`

**Implementation discipline:** Use `@superpowers:test-driven-development` for every production change. Run each named failing test before implementing it, keep third-party calendar types inside the adapter, and commit after every task. Do not add a scheduler loop, network provider, broker code, order path, or database migration.

---

### Task 1: Add the calendar dependency and timezone configuration

**Files:**
- Modify: `apps/api/pyproject.toml`
- Modify: `apps/api/src/market_trader/config.py`
- Modify: `apps/api/tests/test_config.py`
- Modify: `.env.example`
- Modify: `compose.yaml`

**Step 1: Write failing configuration tests**

Extend `apps/api/tests/test_config.py` with typed `MonkeyPatch` usage and these cases:

```python
from pytest import MonkeyPatch


def test_defaults_display_timezone_to_chicago(monkeypatch: MonkeyPatch) -> None:
    monkeypatch.delenv("MARKET_TRADER_DISPLAY_TIMEZONE", raising=False)
    get_settings.cache_clear()

    assert get_settings().display_timezone == "America/Chicago"


def test_rejects_unknown_display_timezone(monkeypatch: MonkeyPatch) -> None:
    monkeypatch.setenv("MARKET_TRADER_DISPLAY_TIMEZONE", "CST")
    get_settings.cache_clear()

    try:
        get_settings()
    except ValueError as error:
        assert "display timezone" in str(error).lower()
    else:
        raise AssertionError("invalid display timezone was accepted")
```

Add `get_settings.cache_clear()` in a fixture or `try/finally` so one test's
cached settings cannot affect another.

**Step 2: Run the tests and verify failure**

Run from `apps/api`:

```bash
.venv/bin/pytest tests/test_config.py -q
```

Expected: FAIL because `Settings` has no `display_timezone` field.

**Step 3: Add the dependency and setting**

Add this runtime dependency in `apps/api/pyproject.toml`:

```toml
"exchange-calendars>=4.13,<5",
```

Use `ZoneInfo` to validate the setting without maintaining a timezone allowlist:

```python
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError


class Settings(BaseSettings):
    # existing fields...
    display_timezone: str = "America/Chicago"

    @model_validator(mode="after")
    def validate_safety_settings(self) -> "Settings":
        if self.trading_mode is TradingMode.LIVE:
            raise ValueError("Live trading is unavailable in the foundation release")
        try:
            ZoneInfo(self.display_timezone)
        except ZoneInfoNotFoundError as error:
            raise ValueError("Unknown display timezone") from error
        return self
```

Rename the existing validator rather than adding two order-dependent model
validators. Preserve the live-mode rejection text expected by current tests.

Add to `.env.example`:

```dotenv
MARKET_TRADER_DISPLAY_TIMEZONE=America/Chicago
```

Pass the same value through the API service in `compose.yaml`:

```yaml
MARKET_TRADER_DISPLAY_TIMEZONE: ${MARKET_TRADER_DISPLAY_TIMEZONE:-America/Chicago}
```

Do not make the XNYS calendar configurable in this milestone.

**Step 4: Install and run focused checks**

Run:

```bash
cd apps/api
.venv/bin/python -m pip install -e '.[dev]'
.venv/bin/pytest tests/test_config.py -q
.venv/bin/ruff check src/market_trader/config.py tests/test_config.py
.venv/bin/mypy src
```

Expected: all checks pass.

**Step 5: Commit**

```bash
git add .env.example compose.yaml apps/api/pyproject.toml apps/api/src/market_trader/config.py apps/api/tests/test_config.py
git commit -m "chore: add market calendar configuration"
```

---

### Task 2: Add injectable clock primitives

**Files:**
- Modify: `apps/api/src/market_trader/domain/time.py`
- Modify: `apps/api/tests/test_domain_primitives.py`

**Step 1: Write failing clock tests**

Add tests that prove both implementations return aware UTC values:

```python
from datetime import UTC, datetime, timedelta, timezone

from market_trader.domain.time import FrozenClock, SystemClock


def test_system_clock_returns_aware_utc() -> None:
    assert SystemClock().now().tzinfo is UTC


def test_frozen_clock_normalizes_aware_value_to_utc() -> None:
    source = datetime(2026, 7, 20, 10, 30, tzinfo=timezone(timedelta(hours=-5)))

    assert FrozenClock(source).now() == datetime(2026, 7, 20, 15, 30, tzinfo=UTC)


def test_frozen_clock_rejects_naive_value() -> None:
    try:
        FrozenClock(datetime(2026, 7, 20, 10, 30))
    except ValueError as error:
        assert "timezone-aware" in str(error)
    else:
        raise AssertionError("frozen clock accepted a naive datetime")
```

**Step 2: Verify the tests fail**

```bash
cd apps/api
.venv/bin/pytest tests/test_domain_primitives.py -q
```

Expected: import failure for `FrozenClock` and `SystemClock`.

**Step 3: Implement the clock protocol**

Keep the existing helpers and add:

```python
from dataclasses import dataclass
from typing import Protocol


class Clock(Protocol):
    def now(self) -> datetime: ...


class SystemClock:
    def now(self) -> datetime:
        return utc_now()


@dataclass(frozen=True)
class FrozenClock:
    value: datetime

    def __post_init__(self) -> None:
        object.__setattr__(self, "value", ensure_utc(self.value))

    def now(self) -> datetime:
        return self.value
```

**Step 4: Run focused checks**

```bash
cd apps/api
.venv/bin/pytest tests/test_domain_primitives.py -q
.venv/bin/ruff check src/market_trader/domain/time.py tests/test_domain_primitives.py
.venv/bin/mypy src
```

Expected: PASS.

**Step 5: Commit**

```bash
git add apps/api/src/market_trader/domain/time.py apps/api/tests/test_domain_primitives.py
git commit -m "feat: add deterministic clock boundary"
```

---

### Task 3: Define calendar models, protocol, and entry policy

**Files:**
- Create: `apps/api/src/market_trader/market_calendar/__init__.py`
- Create: `apps/api/src/market_trader/market_calendar/models.py`
- Create: `apps/api/src/market_trader/market_calendar/policy.py`
- Test: `apps/api/tests/test_entry_window_policy.py`

**Step 1: Write failing policy tests**

Use standard-library values only:

```python
from datetime import UTC, date, datetime

from market_trader.market_calendar.models import ExchangeSession
from market_trader.market_calendar.policy import EntryWindowPolicy


def session(close_hour: int) -> ExchangeSession:
    return ExchangeSession(
        calendar="XNYS",
        session_date=date(2026, 7, 20),
        market_open=datetime(2026, 7, 20, 13, 30, tzinfo=UTC),
        market_close=datetime(2026, 7, 20, close_hour, 0, tzinfo=UTC),
        is_early_close=close_hour == 17,
    )


def test_normal_session_entry_window() -> None:
    window = EntryWindowPolicy.v1().window_for(session(20))

    assert window.opens_at == datetime(2026, 7, 20, 13, 45, tzinfo=UTC)
    assert window.closes_at == datetime(2026, 7, 20, 19, 30, tzinfo=UTC)
    assert window.policy_version == "entry-window-v1"


def test_early_close_preserves_thirty_minute_buffer() -> None:
    window = EntryWindowPolicy.v1().window_for(session(17))

    assert window.closes_at == datetime(2026, 7, 20, 16, 30, tzinfo=UTC)


def test_entry_end_is_exclusive() -> None:
    policy = EntryWindowPolicy.v1()
    window = policy.window_for(session(20))

    assert policy.allows(window.opens_at, window)
    assert not policy.allows(window.closes_at, window)
```

Use the actual November early-close date in adapter tests; this pure policy test
uses a synthetic session to isolate arithmetic.

**Step 2: Verify failure**

```bash
cd apps/api
.venv/bin/pytest tests/test_entry_window_policy.py -q
```

Expected: import failure for `market_trader.market_calendar`.

**Step 3: Implement immutable project-owned models**

`models.py` should define:

```python
from dataclasses import dataclass
from datetime import date, datetime
from enum import StrEnum
from typing import Protocol


class MarketState(StrEnum):
    CLOSED = "closed"
    PRE_MARKET = "pre_market"
    OPENING_BUFFER = "opening_buffer"
    ENTRY_OPEN = "entry_open"
    ENTRY_CLOSED = "entry_closed"
    POST_MARKET = "post_market"


@dataclass(frozen=True)
class ExchangeSession:
    calendar: str
    session_date: date
    market_open: datetime
    market_close: datetime
    is_early_close: bool


@dataclass(frozen=True)
class EntryWindow:
    opens_at: datetime
    closes_at: datetime
    policy_version: str


class ExchangeCalendar(Protocol):
    name: str
    timezone_name: str

    def is_session(self, session_date: date) -> bool: ...
    def session(self, session_date: date) -> ExchangeSession: ...
    def next_session(self, after: date) -> ExchangeSession: ...
    def previous_session(self, before: date) -> ExchangeSession: ...
    def sessions_between(self, start: date, end: date) -> tuple[ExchangeSession, ...]: ...
    def session_for_timestamp(self, value: datetime) -> ExchangeSession | None: ...
```

Add project exceptions `CalendarUnavailableError` and `SessionNotFoundError` in
this module or a small `errors.py` if that keeps imports clearer.

**Step 4: Implement `EntryWindowPolicy`**

Use frozen dataclass fields for opening delay, closing buffer, and version. Its
`window_for()` and `allows()` methods call `ensure_utc()` and enforce the
inclusive-start, exclusive-end rule. Reject a malformed session whose calculated
window is empty or inverted.

**Step 5: Run focused checks**

```bash
cd apps/api
.venv/bin/pytest tests/test_entry_window_policy.py -q
.venv/bin/ruff check src/market_trader/market_calendar tests/test_entry_window_policy.py
.venv/bin/mypy src
```

Expected: PASS.

**Step 6: Commit**

```bash
git add apps/api/src/market_trader/market_calendar apps/api/tests/test_entry_window_policy.py
git commit -m "feat: define exchange calendar domain contracts"
```

---

### Task 4: Implement the bounded XNYS adapter

**Files:**
- Create: `apps/api/src/market_trader/market_calendar/adapter.py`
- Test: `apps/api/tests/test_xnys_calendar.py`

**Step 1: Write fixed-date adapter tests**

Construct the adapter with explicit `start=date(2026, 1, 1)` and
`end=date(2027, 12, 31)`. Assert:

```python
def test_normal_session_uses_expected_utc_hours() -> None:
    observed = calendar.session(date(2026, 7, 20))
    assert observed.market_open == datetime(2026, 7, 20, 13, 30, tzinfo=UTC)
    assert observed.market_close == datetime(2026, 7, 20, 20, 0, tzinfo=UTC)
    assert not observed.is_early_close


def test_independence_day_observed_is_not_a_session() -> None:
    assert not calendar.is_session(date(2026, 7, 3))


def test_day_after_thanksgiving_is_early_close() -> None:
    observed = calendar.session(date(2026, 11, 27))
    assert observed.market_close == datetime(2026, 11, 27, 18, 0, tzinfo=UTC)
    assert observed.is_early_close


def test_spring_dst_changes_open_utc_hour() -> None:
    assert calendar.session(date(2026, 3, 6)).market_open.hour == 14
    assert calendar.session(date(2026, 3, 9)).market_open.hour == 13
```

Also test weekend behavior, previous/next session lookup, `sessions_between`,
open-minute timestamp lookup, closed-minute lookup returning `None`, naive
timestamp rejection, and an out-of-bounds date translated to the project-owned
exception.

**Step 2: Verify failure**

```bash
cd apps/api
.venv/bin/pytest tests/test_xnys_calendar.py -q
```

Expected: import failure for `XNYSCalendarAdapter`.

**Step 3: Implement the adapter**

Use these verified `exchange_calendars` 4.13 APIs:

```python
import exchange_calendars as exchange_calendars
import pandas as pd

self._calendar = exchange_calendars.get_calendar(
    "XNYS",
    start=start.isoformat(),
    end=end.isoformat(),
)
self._calendar.is_session(session_date.isoformat())
self._calendar.session_open(session_date.isoformat())
self._calendar.session_close(session_date.isoformat())
self._calendar.previous_session(session_date.isoformat())
self._calendar.next_session(session_date.isoformat())
self._calendar.sessions_in_range(start.isoformat(), end.isoformat())
self._calendar.minute_to_session(pd.Timestamp(aware_utc), direction="none")
```

Convert a pandas timestamp only through its standard Python datetime/date output,
then call `ensure_utc()`. Determine early close membership inside the adapter
using the dependency's `early_closes` index. No pandas object may appear in a
return type or project-owned model.

Catch dependency parsing/out-of-bounds errors and raise
`CalendarUnavailableError` or `SessionNotFoundError` with stable application
messages. Do not catch `BaseException` or hide programming errors.

If mypy reports missing or incomplete dependency typing, contain a narrowly
scoped `Any` annotation inside `adapter.py`; do not disable strict mypy globally.

**Step 4: Run focused checks**

```bash
cd apps/api
.venv/bin/pytest tests/test_xnys_calendar.py -q
.venv/bin/ruff check src/market_trader/market_calendar/adapter.py tests/test_xnys_calendar.py
.venv/bin/mypy src
```

Expected: PASS.

**Step 5: Commit**

```bash
git add apps/api/src/market_trader/market_calendar/adapter.py apps/api/tests/test_xnys_calendar.py
git commit -m "feat: add bounded XNYS calendar adapter"
```

---

### Task 5: Derive market-state snapshots and freshness

**Files:**
- Modify: `apps/api/src/market_trader/market_calendar/models.py`
- Create: `apps/api/src/market_trader/market_calendar/service.py`
- Test: `apps/api/tests/test_market_state_service.py`

**Step 1: Write state-transition tests with a fake calendar**

Create a small fake implementing `ExchangeCalendar` with a normal July 20
session, July 21 next session, and November 27 early-close session. Use
`FrozenClock` and parameterize exact values:

```python
@pytest.mark.parametrize(
    ("observed_at", "expected_state", "entry_allowed", "next_transition"),
    [
        (datetime(2026, 7, 20, 13, 29, 59, tzinfo=UTC), MarketState.PRE_MARKET, False, datetime(2026, 7, 20, 13, 30, tzinfo=UTC)),
        (datetime(2026, 7, 20, 13, 30, tzinfo=UTC), MarketState.OPENING_BUFFER, False, datetime(2026, 7, 20, 13, 45, tzinfo=UTC)),
        (datetime(2026, 7, 20, 13, 45, tzinfo=UTC), MarketState.ENTRY_OPEN, True, datetime(2026, 7, 20, 19, 30, tzinfo=UTC)),
        (datetime(2026, 7, 20, 19, 30, tzinfo=UTC), MarketState.ENTRY_CLOSED, False, datetime(2026, 7, 20, 20, 0, tzinfo=UTC)),
        (datetime(2026, 7, 20, 20, 0, tzinfo=UTC), MarketState.POST_MARKET, False, datetime(2026, 7, 21, 13, 30, tzinfo=UTC)),
    ],
)
def test_state_boundaries(...):
    ...
```

Add tests for:

- Weekend `closed` with next session open as the transition.
- Early-close entry end at 12:30 PM ET / 16:30 UTC on November 27, 2026.
- `valid_until` equal to `observed_at + 60 seconds` away from transitions.
- `valid_until` capped at a transition less than 60 seconds away.
- Snapshot freshness true at or before `valid_until` and false after it.
- Adapter failure becoming `CalendarUnavailableError`, never guessed state.

**Step 2: Verify failure**

```bash
cd apps/api
.venv/bin/pytest tests/test_market_state_service.py -q
```

Expected: import failure for the service/snapshot.

**Step 3: Add the immutable snapshot**

Include these typed fields in `MarketStateSnapshot`:

```python
market_state: MarketState
entry_allowed: bool
calendar: str
policy_version: str
observed_at: datetime
valid_until: datetime
next_transition: datetime
session: ExchangeSession | None
entry_window: EntryWindow | None
next_session: ExchangeSession
calendar_timezone: str
display_timezone: str
```

Add `is_fresh(reference_time: datetime) -> bool` using `ensure_utc()` and the
approved inclusive freshness boundary. It must not read the system clock.

**Step 4: Implement `MarketStateService`**

Inject `Clock`, `ExchangeCalendar`, `EntryWindowPolicy`, display timezone, and a
60-second freshness interval. Convert `observed_at` to `ZoneInfo("America/New_York")`
to choose the current Eastern calendar date. Derive state in this exact order:

1. Non-session date -> `closed`, transition to next session open.
2. Before open -> `pre_market`, transition to open.
3. Before entry start -> `opening_buffer`, transition to entry start.
4. Before entry end -> `entry_open`, transition to entry end.
5. Before close -> `entry_closed`, transition to close.
6. At or after close -> `post_market`, transition to next session open.

Set `entry_allowed` only by comparing state with `ENTRY_OPEN`. Calculate
`valid_until = min(observed_at + freshness_interval, next_transition)`.

**Step 5: Run focused checks**

```bash
cd apps/api
.venv/bin/pytest tests/test_market_state_service.py tests/test_entry_window_policy.py -q
.venv/bin/ruff check src/market_trader/market_calendar tests/test_market_state_service.py
.venv/bin/mypy src
```

Expected: PASS.

**Step 6: Commit**

```bash
git add apps/api/src/market_trader/market_calendar apps/api/tests/test_market_state_service.py
git commit -m "feat: derive deterministic market state"
```

---

### Task 6: Add deterministic schedule planning

**Files:**
- Create: `apps/api/src/market_trader/scheduling/__init__.py`
- Create: `apps/api/src/market_trader/scheduling/models.py`
- Create: `apps/api/src/market_trader/scheduling/planner.py`
- Test: `apps/api/tests/test_schedule_planner.py`

**Step 1: Write failing schedule-planner tests**

Define representative values in tests:

```python
scan = RecurringSchedule(
    schedule_id="scan-fixture",
    job_kind=JobKind.SCAN,
    window=SessionWindow.ENTRY,
    interval=timedelta(minutes=5),
    policy_version="scan-schedule-v1",
)

end_of_day = SessionOffsetSchedule(
    schedule_id="eod-fixture",
    job_kind=JobKind.END_OF_DAY,
    anchor=SessionAnchor.CLOSE,
    offset=timedelta(minutes=5),
    policy_version="eod-schedule-v1",
)
```

Test that:

- A normal session generates recurring runs from 9:45 AM ET inclusive and never
  at or after 3:30 PM ET.
- A 1:00 PM early close stops recurring entry-window runs before 12:30 PM ET.
- A close-plus-five-minute run is based on the actual early close.
- A weekend interval generates no runs.
- A start-exclusive/end-inclusive query returns runs at the end boundary but not
  the start boundary.
- A delayed interval returns every expected run in chronological order.
- Repeating the query produces equal runs and equal idempotency keys.
- Scan, refresh, end-of-day, and recovery job kinds can all be represented.
- Naive interval boundaries and non-positive recurring intervals are rejected.

**Step 2: Verify failure**

```bash
cd apps/api
.venv/bin/pytest tests/test_schedule_planner.py -q
```

Expected: import failure for `market_trader.scheduling`.

**Step 3: Define immutable schedule values**

`models.py` should include:

```python
class JobKind(StrEnum):
    SCAN = "scan"
    REFRESH = "refresh"
    END_OF_DAY = "end_of_day"
    RECOVERY = "recovery"


class SessionWindow(StrEnum):
    REGULAR = "regular"
    ENTRY = "entry"


class SessionAnchor(StrEnum):
    OPEN = "open"
    CLOSE = "close"


@dataclass(frozen=True)
class RecurringSchedule: ...


@dataclass(frozen=True)
class SessionOffsetSchedule: ...


@dataclass(frozen=True)
class ScheduledRun:
    schedule_id: str
    job_kind: JobKind
    session_date: date
    scheduled_for: datetime
    calendar: str
    policy_version: str
    idempotency_key: str
```

The idempotency key must be derived only from stable fields such as schedule ID,
policy version, session date, and UTC scheduled time. Use a readable canonical
string or a SHA-256 digest; never use Python's process-randomized `hash()`.

**Step 4: Implement the pure planner**

Inject `ExchangeCalendar` and `EntryWindowPolicy`. Query enough Eastern dates to
cover the UTC interval, ask the adapter for sessions, generate candidate times,
filter by `start_exclusive < scheduled_for <= end_inclusive`, sort, and return a
tuple.

Recurring windows are half-open. Session-offset runs may be outside regular
hours, such as close plus five minutes. The planner returns expected runs only;
it does not track execution, persist watermarks, sleep, retry, or invoke a
callback.

**Step 5: Run focused checks**

```bash
cd apps/api
.venv/bin/pytest tests/test_schedule_planner.py -q
.venv/bin/ruff check src/market_trader/scheduling tests/test_schedule_planner.py
.venv/bin/mypy src
```

Expected: PASS.

**Step 6: Commit**

```bash
git add apps/api/src/market_trader/scheduling apps/api/tests/test_schedule_planner.py
git commit -m "feat: add deterministic schedule planner"
```

---

### Task 7: Expose the read-only market-state API

**Files:**
- Create: `apps/api/src/market_trader/api/market_state.py`
- Modify: `apps/api/src/market_trader/main.py`
- Test: `apps/api/tests/test_market_state_api.py`

**Step 1: Write failing API contract tests**

Create a deterministic service fake or real service with a fake calendar and
override the FastAPI dependency. Assert:

```python
response = client.get("/api/market-state")
assert response.status_code == 200
assert response.headers["cache-control"] == "no-store"
assert response.json() == {
    "market_state": "entry_open",
    "entry_allowed": True,
    "calendar": "XNYS",
    "policy_version": "entry-window-v1",
    # include every exact contract field from the specification
}
```

Add tests for a weekend response with nullable session fields and a calendar
failure response:

```python
assert response.status_code == 503
assert response.json()["entry_allowed"] is False
assert response.json()["error_code"] == "market_calendar_unavailable"
assert "traceback" not in response.text.lower()
```

**Step 2: Verify failure**

```bash
cd apps/api
.venv/bin/pytest tests/test_market_state_api.py -q
```

Expected: 404 for `/api/market-state`.

**Step 3: Implement API models and dependency factory**

Define explicit Pydantic response models. Use `datetime` and `date` fields so
FastAPI serializes UTC values consistently. Include current session, entry
window, next session, timezone identifiers, and early-close fields as specified.

Create a cached production service factory that:

- Uses `SystemClock`.
- Builds `XNYSCalendarAdapter` with explicit bounds covering at least ten years
  before and five years after the production clock date.
- Uses `EntryWindowPolicy.v1()`.
- Reads only the display timezone from settings.

Keep the factory as a FastAPI dependency so tests can override it. Do not build a
new exchange calendar on every request.

Catch only `CalendarUnavailableError`. Return the structured 503 body with
`entry_allowed: false`; do not guess a session or return dependency exception
text. Set `Cache-Control: no-store` on both success and unavailable responses.

**Step 4: Register the router**

In `create_app()`, include the new router under `/api` next to health. Preserve
the existing docs and health routes.

**Step 5: Run focused and regression checks**

```bash
cd apps/api
.venv/bin/pytest tests/test_market_state_api.py tests/test_health.py tests/test_config.py -q
.venv/bin/ruff check src tests/test_market_state_api.py
.venv/bin/mypy src
```

Expected: PASS.

**Step 6: Commit**

```bash
git add apps/api/src/market_trader/api/market_state.py apps/api/src/market_trader/main.py apps/api/tests/test_market_state_api.py
git commit -m "feat: expose read-only market state"
```

---

### Task 8: Add frontend market-state contracts and formatting

**Files:**
- Modify: `apps/web/src/api.ts`
- Create: `apps/web/src/marketTime.ts`
- Test: `apps/web/src/marketTime.test.ts`

**Step 1: Write failing formatting tests**

Test date-aware ET and CT formatting across daylight-saving time:

```typescript
import { describe, expect, test } from 'vitest'

import { formatMarketTime } from './marketTime'

describe('formatMarketTime', () => {
  test('formats summer values in both ET and CT', () => {
    const value = '2026-07-20T13:30:00Z'
    expect(formatMarketTime(value, 'America/New_York', 'ET')).toContain('9:30 AM ET')
    expect(formatMarketTime(value, 'America/Chicago', 'CT')).toContain('8:30 AM CT')
  })

  test('formats winter offsets from IANA zones', () => {
    const value = '2026-11-27T14:30:00Z'
    expect(formatMarketTime(value, 'America/New_York', 'ET')).toContain('9:30 AM ET')
    expect(formatMarketTime(value, 'America/Chicago', 'CT')).toContain('8:30 AM CT')
  })
})
```

Also test `isSnapshotFresh(snapshot, now)` at and after `valid_until` using
explicit milliseconds; it must not read `Date.now()` internally unless `now` is
omitted by a UI wrapper.

**Step 2: Verify failure**

```bash
cd apps/web
npm test -- --run src/marketTime.test.ts
```

Expected: module import failure.

**Step 3: Add the API contract and fetch function**

Define `MarketState`, `MarketStateResponse`, and `MarketStateUnavailableResponse`
in `api.ts`. Mirror nullable fields exactly. Add:

```typescript
export async function fetchMarketState(signal?: AbortSignal): Promise<MarketStateResponse> {
  const response = await fetch('/api/market-state', {
    headers: { Accept: 'application/json' },
    cache: 'no-store',
    signal,
  })
  if (!response.ok) throw new Error(`Market state request failed with ${response.status}`)
  return (await response.json()) as MarketStateResponse
}
```

The frontend treats every non-2xx response as unavailable and never infers
eligibility from local time.

**Step 4: Implement formatting helpers**

Use `Intl.DateTimeFormat('en-US', { timeZone, ... })` and append the explicit
`ET` or `CT` label supplied by the caller. Do not hard-code offsets and do not use
the browser's default timezone.

**Step 5: Run focused checks**

```bash
cd apps/web
npm test -- --run src/marketTime.test.ts
npm run lint
npm run build
```

Expected: PASS. The known host Node version warning may appear, but the command
must exit zero; Docker uses a supported Node version.

**Step 6: Commit**

```bash
git add apps/web/src/api.ts apps/web/src/marketTime.ts apps/web/src/marketTime.test.ts
git commit -m "feat: add frontend market time contracts"
```

---

### Task 9: Build the polling, stale-aware market status component

**Files:**
- Create: `apps/web/src/MarketStatus.tsx`
- Test: `apps/web/src/MarketStatus.test.tsx`

**Step 1: Write failing component tests**

Use Testing Library and fake timers. Cover:

- Loading text before the first response.
- Normal `entry_open` response with ET and CT values.
- Early-close text and 12:30 PM ET entry close.
- Market API failure showing `Market schedule unavailable` while preserving no
  executable control.
- A retained successful snapshot becoming unavailable exactly after
  `valid_until`.
- A refresh request every 30 seconds.
- Cleanup aborting the request and clearing timers on unmount.

Use `vi.useFakeTimers()` and `vi.setSystemTime()` with fixed UTC values. Restore
real timers in `afterEach`. Do not wait 30 real seconds.

**Step 2: Verify failure**

```bash
cd apps/web
npm test -- --run src/MarketStatus.test.tsx
```

Expected: module import failure.

**Step 3: Implement the component state machine**

Use states equivalent to:

```typescript
type MarketLoadState =
  | { kind: 'loading' }
  | { kind: 'ready'; snapshot: MarketStateResponse }
  | { kind: 'unavailable' }
```

On mount, fetch immediately and create a 30-second interval. On success, replace
the snapshot and schedule a one-shot expiry at `valid_until`. On request failure,
retain a still-fresh snapshot; otherwise transition to unavailable. At expiry,
transition to unavailable unless a newer snapshot has replaced it.

Guard asynchronous updates after unmount. Use one `AbortController` per request
or correctly replace an aborted controller for later polling. Timer cleanup must
be complete and testable.

Render a semantic section with a heading and definition list. Show state,
entry-window status, current observed time, session hours, entry hours, next
transition, and early-close indication. Format every timestamp in both ET and CT.
For closed dates, show the next session rather than blank current-session rows.

Do not include buttons, toggles, links that trigger work, or local entry-state
calculations.

**Step 4: Run focused checks**

```bash
cd apps/web
npm test -- --run src/MarketStatus.test.tsx src/marketTime.test.ts
npm run lint
```

Expected: PASS with no leaked-timer warnings.

**Step 5: Commit**

```bash
git add apps/web/src/MarketStatus.tsx apps/web/src/MarketStatus.test.tsx
git commit -m "feat: add stale-aware market status panel"
```

---

### Task 10: Integrate and style the compact status panel

**Files:**
- Modify: `apps/web/src/App.tsx`
- Modify: `apps/web/src/App.test.tsx`
- Modify: `apps/web/src/index.css`

**Step 1: Extend application tests first**

Update fetch mocks to return health for `/api/health` and market state for
`/api/market-state`. Assert:

- The paper-mode banner remains first and unmistakable.
- Health metadata still renders.
- The market-status heading and ET/CT labels render.
- Market-state failure does not replace the paper-mode and health screen with the
  global backend-health failure state.
- Health failure still produces the existing blocking global alert.
- No button is rendered.

**Step 2: Run the App tests and verify failure**

```bash
cd apps/web
npm test -- --run src/App.test.tsx
```

Expected: FAIL because `App` does not render `MarketStatus`.

**Step 3: Integrate the component**

Render `<MarketStatus />` after the application title and before or after the
small system metadata section. Keep health loading/error ownership in `App` and
market-state loading/error ownership in `MarketStatus` so a calendar problem
does not hide the verified paper-mode safety state.

**Step 4: Add restrained responsive styles**

Use the existing dark foundation design rather than creating a marketing page.
Keep sections unframed or use a single compact status surface; do not nest cards.
Use a responsive definition-list grid with `minmax(0, 1fr)`, explicit wrapping,
and a mobile breakpoint. Distinguish open, closed, and unavailable with text and
border/accent differences, not color alone. Keep border radii at 8px or less.

Verify no label or timestamp can overflow at 320px width. Do not add gradients,
decorative blobs, animations, oversized hero text, or feature instructions.

**Step 5: Run frontend verification**

```bash
cd apps/web
npm test -- --run
npm run lint
npm run build
```

Expected: all tests and commands pass.

**Step 6: Commit**

```bash
git add apps/web/src/App.tsx apps/web/src/App.test.tsx apps/web/src/index.css
git commit -m "feat: display exchange and Chicago market time"
```

---

### Task 11: Add operational verification and documentation

**Files:**
- Modify: `scripts/verify-foundation.sh`
- Modify: `README.md`
- Create: `docs/milestone-2-calendar.md`
- Test: `apps/api/tests/test_container_configuration.py`

**Step 1: Extend container/configuration tests**

Add assertions that Compose passes `MARKET_TRADER_DISPLAY_TIMEZONE` to the API
and that the verification script checks `/api/market-state` without allowing an
entry decision to bypass paper mode.

**Step 2: Verify the test fails**

```bash
cd apps/api
.venv/bin/pytest tests/test_container_configuration.py -q
```

Expected: FAIL because Compose/script do not yet include the Milestone 2 checks.

**Step 3: Extend the smoke script**

Fetch `/api/market-state` and assert with Python JSON parsing:

- `calendar == "XNYS"`.
- `entry_allowed` is a JSON boolean.
- `calendar_timezone == "America/New_York"`.
- `display_timezone == "America/Chicago"` under default configuration.
- A policy version is present.

Keep the existing paper-mode, database, and frontend checks. Do not assert that
the market is open, because smoke tests may run at any time.

**Step 4: Write the runbook**

Document:

- XNYS regular-hours scope.
- ET and CT display using IANA zones.
- Normal and early-close entry-window boundaries.
- Calendar and scheduler test commands.
- Dependency update review and fixed fixture expectations.
- The fact that schedule planning does not execute jobs.
- Docker startup and smoke verification on macOS.
- Provider-free, broker-free, paper-only exclusions.

Update README with a short Milestone 2 section linking the runbook.

**Step 5: Run focused verification**

```bash
cd apps/api
.venv/bin/pytest tests/test_container_configuration.py -q
cd ../..
git diff --check
```

Expected: PASS.

**Step 6: Commit**

```bash
git add README.md docs/milestone-2-calendar.md scripts/verify-foundation.sh apps/api/tests/test_container_configuration.py
git commit -m "docs: document milestone 2 calendar workflow"
```

---

### Task 12: Run complete Milestone 2 verification

**Files:**
- Modify only if a verification failure exposes a Milestone 2 defect.

**Step 1: Run all backend tests and static checks**

```bash
cd apps/api
.venv/bin/pytest -q
.venv/bin/ruff check src tests migrations
.venv/bin/mypy src
```

Expected: all tests pass, coverage remains at or above the repository threshold,
and Ruff/mypy exit zero. Investigate failures with
`@superpowers:systematic-debugging`; do not weaken tests or global type settings.

**Step 2: Run all frontend checks**

```bash
cd apps/web
npm test -- --run
npm run lint
npm run build
```

Expected: all commands pass.

**Step 3: Run Docker verification**

From the repository root:

```bash
test -f .env || cp .env.example .env
docker compose down
docker compose up --build -d
./scripts/verify-foundation.sh
docker compose exec api alembic current
docker compose down
```

Expected:

- Foundation verification passes at `http://127.0.0.1:8080`.
- Market state reports XNYS and both timezone identifiers.
- Alembic remains at `20260718_0001 (head)` because Milestone 2 adds no migration.
- Containers stop cleanly without deleting the named data volume.

On macOS, if `docker` is not in `PATH`, prepend
`/Applications/Docker.app/Contents/Resources/bin` for this shell. Do not alter
system files.

**Step 4: Inspect the running UI before shutdown when practical**

At desktop and mobile widths, verify:

- Paper mode is the first safety signal.
- ET and CT labels are both present.
- Long timestamps wrap without overlap.
- Early-close and unavailable states are textually distinguishable using test
  fixtures or component tests.
- No trading control exists.

Use browser automation or screenshots for inspection if available. Do not add
snapshot images to the repository unless a reviewed test strategy requires them.

**Step 5: Run the safety boundary scan**

```bash
rg -n "Schwab|OAuth|client_secret|access_token|submit_order|place_order|live order" apps scripts .env.example
```

Expected: only explicit safety/exclusion copy or existing paper-mode guards; no
credential, provider, account, or order-submission integration.

**Step 6: Verify branch state and commit any justified fixes**

```bash
git status -sb
git diff --check
git log --oneline --decorate -15
```

If verification required a code fix, repeat the smallest relevant checks, then
the full checks, and commit the fix separately. Finish with
`@superpowers:verification-before-completion` and
`@superpowers:requesting-code-review` before publishing the branch.

---

## Expected Commit Sequence

1. `chore: add market calendar configuration`
2. `feat: add deterministic clock boundary`
3. `feat: define exchange calendar domain contracts`
4. `feat: add bounded XNYS calendar adapter`
5. `feat: derive deterministic market state`
6. `feat: add deterministic schedule planner`
7. `feat: expose read-only market state`
8. `feat: add frontend market time contracts`
9. `feat: add stale-aware market status panel`
10. `feat: display exchange and Chicago market time`
11. `docs: document milestone 2 calendar workflow`

Keep commits narrow. Do not combine dependency setup, domain behavior, API,
frontend polling, and documentation into one change.

## Final Safety Boundary

This plan authorizes deterministic local calendar data, schedule calculation,
and a read-only status display only. It does not authorize external market data,
background job execution, credentials, account access, approval controls, broker
previews, order submission, or live mode.
