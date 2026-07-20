# Milestone 9 Paper Approval, Execution, And Position Lifecycle

Status: Complete
Scope: deterministic paper approval, simulated execution, positions, recovery,
and paper-only operator controls

## What This Milestone Adds

Milestone 9 turns risk-approved candidate output into a complete paper-only
lifecycle. It adds approval cards, approval decisions, final paper previews,
deterministic simulated order outcomes, fills, positions, recovery state, and
frontend workflow panels.

The lifecycle remains local and simulated. It does not connect to Schwab, read
brokerage accounts, store external order references, expose market orders, or
arm live mode.

The paper API covers:

- `GET /api/paper/approval-cards` for current eligible approval cards;
- `POST /api/paper/approval-cards/{card_key}/approve`;
- `POST /api/paper/approval-cards/{card_key}/modify`;
- `POST /api/paper/approval-cards/{card_key}/reject`;
- `POST /api/paper/approvals/{approval_id}/preview`;
- `POST /api/paper/approvals/{approval_id}/submit`;
- `POST /api/paper/orders/{order_id}/cancel`;
- `POST /api/paper/orders/{order_id}/replace`;
- `GET /api/paper/orders`;
- `GET /api/paper/positions`;
- `POST /api/paper/recover`.

## Local Startup

From the repository root:

```bash
cp .env.example .env
docker compose up --build -d
open http://127.0.0.1:8080
```

Stop the stack with:

```bash
docker compose down
```

The stack sets `MARKET_TRADER_TRADING_MODE=paper`. The API applies Alembic
migrations before serving FastAPI.

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

If port `8080` is already in use, use a temporary compose override for local
verification and set `MARKET_TRADER_URL` to the alternate host port.

## Source Eligibility

Approval cards are assembled only from persisted candidate lineage with current
risk decisions in `approved` or `warning` states. Eligibility requires:

- positive quantity and positive limit price;
- current risk input and result digests;
- available source records for the proposal shape;
- no active required risk lock;
- source data that has not gone stale under the Milestone 9 policy.

Blocked, stale, malformed, missing-lineage, zero-quantity, and actively locked
records remain inspectable in read-only dashboard views but do not produce
approval cards.

## Approval Workflow

The `Paper Approvals` tab lists eligible approval cards with source traces,
expiration time, risk status, quantity, limit price, maximum loss, and allowed
paper-only actions.

Operators can:

- approve a paper approval card;
- modify bounded quantity and limit price;
- reject a paper approval card;
- request a final paper preview;
- submit a paper order only after a current preview exists.

Approval and submit flows reject expired approvals, stale previews, changed risk
digests, closed entry windows, active required locks, invalid payloads, and
non-limit orders.

## Preview And Submit Behavior

A final paper preview is required before submission. The preview carries a
digest, quote observation time, quote expiration time, bid/ask values, reserved
risk, warnings, and source keys.

The frontend disables `Submit paper order` until a current preview exists. The
backend verifies the submitted preview digest and rejects stale or changed
preview state with conflict errors.

## Paper Scenarios

The deterministic paper broker supports:

- `accepted_unfilled`;
- `full_fill`;
- `partial_fill`;
- `reject`;
- `cancel`;
- `cancel_replace`;
- `timeout`;
- `assignment`.

Scenario execution is deterministic for the same intent, preview, scenario, and
timestamp. Generated order IDs, simulated references, fill prices, lifecycle
events, reason codes, and position state are stable.

## Position Lifecycle

Paper fills can create paper positions with quantity, average price, realized
P/L, unrealized P/L, source order IDs, source fill IDs, risk decision key,
opened and updated timestamps, and exit rules.

The `Paper Positions` tab shows P/L facts, stop and target rules when present,
expiration labels, and assignment warnings. Position records keep
`broker_reference` unset.

## Orders And Recovery

The `Paper Orders` tab shows open paper orders, status, fill progress, limit
price, timestamps, and paper-only cancel/replace controls.

The `Paper Recovery` tab summarizes open approvals, working orders, timed-out
orders, open orders, and open positions. Restart recovery prioritizes open
positions and working orders so the operator can inspect unresolved paper state
after process restart.

## Fixture Expectations

Checked-in paper lifecycle fixtures cover:

- success;
- partial fill;
- reject;
- stale quote;
- expired approval;
- cancel race;
- restart recovery;
- simulated assignment.

`apps/api/scripts/generate_paper_lifecycle_fixtures.py` regenerates the
manifests idempotently. Fixture conformance tests verify required coverage,
domain enum values, expected order and position status, recovery counts, paper
mode, and absence of external references.

`scripts/verify-foundation.sh` validates the checked-in paper lifecycle
manifests inside the Docker API container without writing to the image
filesystem.

## Explicit Non-Capabilities

Milestone 9 does not implement:

- Schwab OAuth;
- Schwab order submission;
- brokerage account reads;
- external broker previews;
- external order IDs;
- broker credentials;
- live-mode arming;
- live order submission;
- market orders;
- automatic trading;
- tax advice.
