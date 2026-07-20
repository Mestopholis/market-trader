# Milestone 7 Risk, Sizing, Exposure, And Tax Warnings Specification

## Status

Drafted for implementation on `milestone7`.

## Objective

Milestone 7 adds deterministic risk decisions that turn scanner/options-analysis
outputs into approval-readiness decisions without broker access, broker previews,
or order submission. It enforces sizing, capital-at-risk, portfolio exposure,
reserved risk, stale data, risk locks, settlement, and tax-warning boundaries.

## Scope

### Included

- Versioned risk policy for cash, per-trade, aggregate, daily, weekly,
  position-count, trade-count, correlation-group, drawdown, settlement, and
  tax-warning rules.
- Share sizing and debit-spread sizing with integer quantities only.
- Rejection of share proposals below one share and debit-spread proposals below
  one contract.
- Buying-power abstraction that represents settled cash, unsettled cash,
  reserved risk, and non-borrowed available cash.
- Reserved-risk accounting for working simulated orders and assignment stress.
- Risk locks for stale data, daily/weekly loss, authentication, account mismatch,
  strategy review, drawdown, and manual operator hold.
- Correlation-group exposure limits using deterministic symbol-to-group inputs.
- Wash-sale and short-term/long-term tax-estimate warnings with explicit
  non-advice wording.
- Versioned risk decisions with complete explanation payloads and stable digests.
- Append-only persistence and audit events for risk evaluations and reservations.
- Synthetic fixtures and replay for boundary scenarios.

### Excluded

- Schwab account balances or buying power.
- Broker order previews, broker order IDs, broker account data, live orders, and
  real tax advice.
- UI approval controls, paper execution, fills, and position lifecycle changes
  beyond read-only exposure inputs already modeled in storage.
- Margin or borrowed buying power.
- Automatic lock clearing from external systems.

## Inputs

The risk engine consumes immutable values assembled from already-approved
milestones:

- A candidate identity and direction from Milestone 4.
- A selected share or debit-spread proposal built from Milestone 6 data.
- Current paper portfolio positions, working orders, and existing reservations.
- Buying-power snapshot supplied by the paper system, not a broker.
- Account profile flags: cash account, taxable account, pattern-day-trade
  unavailable, and margin disabled.
- Recent realized P/L and trade counts by XNYS session and week.
- Risk locks and their activation timestamps.
- Tax lots and closed trades for wash-sale and holding-period warnings.
- Versioned risk policy hash and aware UTC `as_of`.

Inputs must be pure domain data. The engine must not import SQLAlchemy, HTTP,
Schwab, broker, UI, environment settings, or wall-clock helpers.

## Outputs

The engine produces a `RiskDecision` containing:

- `decision_key`, `input_digest`, `result_digest`, `policy_version`,
  `policy_hash`, and `as_of`.
- `status`: `approved`, `blocked`, or `warning`.
- A sorted tuple of `RiskCheck` records with code, severity, state, facts, and
  source keys.
- A deterministic `SizingResult` with integer quantity, notional, maximum loss,
  reserved risk, assignment stress, and rejected/accepted reason codes.
- Buying-power, exposure, tax, and lock summaries.
- A bounded explanation payload safe for persistence and frontend display.

`approved` means risk policy did not block the proposal. It does not authorize
approval, preview, or order submission; later milestones still own those steps.

## Required Rules

### Sizing

- Share sizing uses integer shares only; fractional shares are rejected.
- Debit-spread sizing uses integer contracts only; zero contracts are rejected.
- Debit-spread maximum loss is debit times multiplier times contracts.
- Assignment stress for short options must be represented separately from max
  loss and included in exposure checks.
- Rounding must only round down; no rule may round up to meet a minimum.

### Capital And Exposure

- Per-trade risk cannot exceed the configured cash and account-equity limits.
- Aggregate reserved risk includes existing open positions, working orders,
  pending proposed trades, and the current proposal.
- Daily and weekly realized-loss limits block new approval-readiness.
- Position count, trade count, and correlation-group concentration limits block
  when the current proposal would cross the boundary.
- Drawdown limits block when realized plus open risk crosses policy thresholds.

### Locks

- Active risk locks block all proposals unless the policy explicitly marks the
  lock type informational.
- Required lock types are: `stale_data`, `authentication`, `account_mismatch`,
  `daily_loss`, `weekly_loss`, `drawdown`, `strategy_review`, and
  `manual_operator_hold`.
- Lock decisions include lock id, type, reason, activation time, and source event
  id when available.

### Settlement And Buying Power

- Only settled cash and policy-approved unsettled cash may be used.
- Borrowed buying power, margin availability, or externally reported broker
  buying power is ignored in Milestone 7.
- Working orders and pending proposals reserve cash/risk before the current
  proposal is evaluated.

### Tax Warnings

- Wash-sale warnings are emitted when a buy-like proposal occurs within the
  configured window after a loss sale of the same or equivalent symbol.
- Short-term/long-term warnings are informational estimates only and must include
  the configured non-advice disclaimer.
- Tax warnings cannot approve or block a trade unless the reviewed policy marks
  a specific warning as blocking.

## Persistence

Milestone 7 adds append-only tables for:

- `risk_decisions`
- `risk_checks`
- `risk_reservations`

Repositories persist a full decision and child rows atomically, flush without
committing, and emit audit events:

- `risk_decision.recorded`
- `risk_check.recorded`
- `risk_reservation.recorded`

Exact reruns return the existing decision when input and result digests match.
Digest conflicts raise a typed error and leave no partial rows.

## Fixtures And CLI

Production fixtures must include:

- `share-sizing-boundaries`
- `spread-sizing-boundaries`
- `portfolio-limits-and-locks`
- `settlement-and-tax-warnings`

The CLI provides offline `validate` and `evaluate` commands. Commands print one
compact sorted JSON object, never use credentials or network access, and return
exit `2` for dataset/policy errors and `3` for infrastructure errors.

## Exit Criteria

- Boundary-value tests prove unsafe proposals are rejected rather than rounded up.
- Locks cannot be bypassed by the risk engine or repository.
- Every risk result is deterministic and auditable.
- Full backend Ruff, strict mypy, pytest, frontend lint/test/build, Alembic head
  migration, fixture validation, Docker compose build, and foundation smoke pass.
