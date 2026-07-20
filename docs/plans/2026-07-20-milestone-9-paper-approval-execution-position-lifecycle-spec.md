# Milestone 9 Paper Approval, Execution, And Position Lifecycle Specification

Date: July 20, 2026
Status: Draft specification
Depends on: Milestones 1-8
Roadmap milestone: 9

## Purpose

Milestone 9 turns the local paper-only system into an end-to-end simulated
trading workflow. It lets an operator approve, modify, paper trade, or reject
risk-approved candidates, routes approved orders through a deterministic paper
broker, records fills, maintains paper positions, and recovers open lifecycle
state after restart.

The milestone remains fully paper-only. It must not authenticate with Schwab,
call Schwab endpoints, place live orders, store broker credentials, or arm live
mode.

## Approved Design Decisions

- Generate approval cards only from persisted candidates that have current
  risk-approved or risk-warning decisions. Milestone 9 does not include manual
  trade entry.
- Use existing trade lifecycle tables as the persistence foundation:
  `proposed_trades`, `approvals`, `orders`, `fills`, and `positions`.
- Add a deterministic paper lifecycle domain above those repositories instead of
  embedding workflow logic directly in FastAPI handlers.
- Treat paper broker responses as deterministic functions of order intent,
  scenario, clock, and existing lifecycle state.
- Keep all external-broker references null. Only `simulated_broker_reference`
  may be populated.
- Require fresh market-state and quote-like simulated facts before approval and
  paper submission.
- Permit only limit orders.
- Journal every operator action, preview, order state transition, fill,
  position transition, cancellation, replacement, rejection, timeout, and
  recovery action.

## Goals

- Show approval cards for eligible risk-approved candidate outputs.
- Support approve, modify, paper trade, and reject actions.
- Enforce expiring approvals and stale-quote rejection.
- Generate final paper previews from deterministic simulated quotes.
- Submit limit orders to a deterministic paper broker.
- Simulate accepted, partial-fill, full-fill, reject, cancel, cancel/replace,
  timeout, and reconciliation outcomes.
- Maintain paper position state, average price, closed quantity, realized P/L
  facts, technical stops, profit targets, time exits, event exits, and
  expiration handling.
- Recover open approvals, working orders, positions, and timed-out paper broker
  requests after restart.
- Extend the dashboard with lifecycle views while preserving paper-mode
  visibility and audit traceability.

## Non-Goals

- Manual trade tickets or free-form order entry.
- Schwab OAuth, account reads, order previews, order placement, order IDs, or
  account reconciliation.
- Live-mode arming or live order submission.
- Market-data provider integration beyond deterministic paper quote inputs.
- Margin, borrowed buying power, short-selling locate, real tax lots, or broker
  buying-power authority.
- Complex options strategies beyond outputs already approved by Milestone 6.
- Background schedulers beyond deterministic recovery commands and explicit API
  calls.

## Source Eligibility

An approval card may be created only when all of the following are true:

- A persisted candidate exists and has a stable candidate key.
- The candidate can be traced to scanner evidence, symbol, strategy, direction,
  score, and policy version.
- Options analysis exists when the candidate requires a spread.
- A risk decision exists with status `approved` or `warning`.
- The risk decision has nonzero quantity, finite maximum loss, stable input and
  result digests, and no blocking checks.
- Source data is not stale under the approved Milestone 9 freshness policy.
- No active required risk lock blocks new approvals.

Blocked, stale, unavailable, or risk-rejected candidates must remain visible in
read-only dashboard views but cannot produce approval cards.

## Domain Model

Milestone 9 introduces pure domain contracts for:

- `ApprovalCard`: source candidate, strategy, symbol, direction, proposal kind,
  risk summary, quote requirements, expiration, allowed operator actions, and
  source digests.
- `PaperOrderIntent`: limit order side, symbol or option legs, quantity,
  limit price, time-in-force, source proposal, risk decision key, and
  correlation id.
- `PaperPreview`: deterministic quote snapshot, limit validation, estimated
  maximum loss, buying-power reservation, warnings, expiration, and preview
  digest.
- `PaperBrokerOrder`: accepted simulated order with scenario, status, remaining
  quantity, fills, timeout clock, and simulated reference.
- `PaperPosition`: open, partially closed, closed, expired, or assigned paper
  position with average price, quantity, exit rules, and realized/unrealized
  facts.
- `LifecycleEvent`: immutable state transition record suitable for journal
  persistence and recovery replay.

Domain objects must reject raw credentials, broker account identifiers, market
orders, unbounded payloads, non-UTC timestamps, negative quantities, and
non-finite prices.

## Approval Workflow

1. The backend assembles approval cards from current risk-approved candidates.
2. The operator may reject a card, approve it as-is, or modify bounded paper-only
   fields such as limit price within policy constraints.
3. Approval creates or updates a proposed trade and approval record with a short
   expiration.
4. A final paper preview must be generated after approval and before paper
   submission.
5. Paper trade submission succeeds only when the approval and preview are fresh,
   the market entry window is still valid, the order is limit-only, and risk
   source digests still match.
6. Submission creates a paper order record and routes it to the deterministic
   paper broker.
7. Paper broker transitions create fills and update positions atomically.

Expired approvals, stale previews, changed risk digests, closed entry windows,
  active required risk locks, or missing source records must block paper
submission with journaled reasons.

## Deterministic Paper Broker

The paper broker must be local, deterministic, and side-effect free outside the
database transaction passed by the application service.

Supported scenarios:

- `accepted_unfilled`: order remains working.
- `full_fill`: order fills completely at the deterministic fill price.
- `partial_fill`: order receives a bounded partial fill and remains working.
- `reject`: order is rejected with a stable reason code.
- `cancel`: working order is canceled before fill.
- `cancel_replace`: working order is replaced by a new limit order while
  preserving the lifecycle chain.
- `timeout`: order remains unresolved until recovery marks it timed out or
  reconciled.
- `assignment`: option spread assignment stress is represented as a simulated
  lifecycle event and position change.

Scenario selection must come from explicit fixture input, policy configuration,
or deterministic order attributes. It must not use randomness, network calls, or
wall-clock timing hidden from tests.

## Position Lifecycle

Position state is derived from fills and explicit paper lifecycle events.

Required behavior:

- Opening fills create or update a paper position.
- Partial fills update average price and remaining order quantity.
- Closing fills reduce or close positions and emit realized P/L facts.
- Technical stops, profit targets, time exits, event exits, and expiration exits
  are represented as pending paper exit intents until submitted through the same
  deterministic broker boundary.
- Position records must preserve source order, fill, proposal, and risk decision
  identifiers.
- Restart recovery reconstructs current position and working-order state from
  persisted lifecycle records.

## API Requirements

All write endpoints remain paper-only and must reject live-mode, broker, or
credential-shaped payloads.

Required endpoints:

- `GET /api/paper/approval-cards`
- `POST /api/paper/approval-cards/{card_key}/approve`
- `POST /api/paper/approval-cards/{card_key}/modify`
- `POST /api/paper/approval-cards/{card_key}/reject`
- `POST /api/paper/approvals/{approval_id}/preview`
- `POST /api/paper/approvals/{approval_id}/submit`
- `POST /api/paper/orders/{order_id}/cancel`
- `POST /api/paper/orders/{order_id}/replace`
- `GET /api/paper/orders`
- `GET /api/paper/positions`
- `POST /api/paper/recover`

Every response includes paper-mode state, aware UTC timestamps, correlation id,
source keys, and stable lifecycle identifiers.

## Frontend Requirements

The React app adds paper lifecycle views while preserving the Milestone 8
dashboard:

- Approval queue with cards for eligible risk-approved candidates.
- Card detail with scanner, options, risk, preview, and expiration facts.
- Modify form for bounded limit-price changes only.
- Paper preview confirmation.
- Paper order blotter with accepted, working, partially filled, filled,
  rejected, canceled, replaced, timed-out, and reconciled states.
- Paper positions view with entry, exits, stops, targets, P/L facts, and
  expiration/assignment warnings.
- Recovery status panel for open approvals, working orders, and open positions.

All action buttons must be labeled explicitly as paper actions. No control may
say or imply live trading, broker connection, Schwab, or real order placement.

## Safety Requirements

- All new write APIs must require `trading_mode == paper`.
- Any payload containing live mode, Schwab, broker credentials, external account
  identifiers, market order type, or unbounded raw payloads is rejected.
- Order submission must be impossible without a current approval, current
  preview, current risk-approved source digest, open entry window, and limit
  price.
- The simulated broker must never import HTTP clients or Schwab/broker modules.
- Existing read-only dashboard safety tests must remain valid for
  `/api/dashboard`.
- Paper lifecycle safety tests must prove no external broker reference is
  written and no live-mode route exists.

## Testing And Verification

- Domain tests cover approval-card eligibility, expiration, limit-only
  validation, digest mismatch, stale quote, and paper-only rejection.
- Paper broker tests cover every deterministic scenario.
- Repository tests cover lifecycle state transitions, idempotency, audit events,
  and recovery replay.
- API tests cover every paper route, validation failure, and success path.
- Frontend tests cover approval queue, modify, reject, preview, submit, order
  blotter, positions, recovery states, and paper-only labels.
- End-to-end paper scenarios cover success, partial fill, reject, stale quote,
  expired approval, cancel race, restart recovery, and simulated assignment.
- Full backend Ruff, strict mypy, pytest, frontend lint, frontend tests,
  frontend build, Alembic head upgrade, Docker compose build, and
  `scripts/verify-foundation.sh` must pass.

## Exit Criteria

- A risk-approved candidate can become an approval card, approval, paper
  preview, paper order, fill, and paper position with complete journal
  traceability.
- Unsafe, stale, expired, changed, or blocked proposals cannot be submitted.
- Paper broker scenarios are deterministic and replayable.
- Restart recovery prioritizes open positions and working orders.
- No Schwab, broker, credential, or live-mode capability is introduced.
