# Milestone 6 Options Analysis And Spread Construction Specification

Date: July 19, 2026
Status: Approved specification
Depends on: Milestones 1-5
Roadmap milestone: 6

## Purpose

Milestone 6 turns a qualified Milestone 4 scanner candidate, current Milestone 5
catalyst context, and an authoritative normalized option chain into deterministic,
defined-risk debit-spread analysis. It constructs bull call spreads for bullish
candidates and bear put spreads for bearish candidates, with explicit rejection
reasons and risk warnings.

This milestone remains paper-analysis only. It cannot size a position, create an
approval, request a broker preview, submit an order, or access a Schwab account.
It does not add naked options, credit spreads, 0DTE strategies, or any live
provider client.

## Approved Design Decisions

- Analyze only qualified Milestone 4 candidates; standalone symbol analysis is
  out of scope.
- Consume existing normalized `NormalizedOptionChain` data from Milestone 3;
  option-chain acquisition remains outside this milestone.
- Use fixed, synthetic 2026 fixtures for validation and replay. No network access
  is needed or permitted by the offline CLI paths.
- Require a valid standard 100-share deliverable, a complete current chain, and
  30 through 60 calendar DTE inclusive.
- Construct only two-leg debit spreads: bull call spreads for bullish candidates
  and bear put spreads for bearish candidates.
- Keep all thresholds, target delta bands, ranking rules, and warning behavior in
  a versioned, hash-locked options-analysis policy.
- Fail closed on missing scanner lineage, blocked catalyst evidence, incomplete or
  stale chain data, adjusted contracts, invalid prices, or missing required event
  context.
- Persist accepted and rejected analysis outcomes atomically and idempotently,
  including immutable inputs, calculations, warnings, and audit lineage.
- Use aware UTC times internally, XNYS sessions for market-time rules, and
  `America/Chicago` only for user-facing renderings.

## Goals

- Validate standard contracts and reject adjusted, nonstandard, incomplete,
  stale, crossed, or otherwise unusable chain inputs with stable reasons.
- Enforce expiration, delta, open interest, volume, bid/ask, and width filters.
- Construct reproducible bull call and bear put debit spreads in the approved
  30-60 DTE range.
- Calculate debit, maximum loss, maximum gain, break-even, net Greeks, technical
  stop reference, liquidity, and execution-quality metrics with exact decimals.
- Surface earnings, ex-dividend, early-assignment, expiration, and pin-risk
  warnings with deterministic severity and blocking semantics.
- Replay identical inputs into exactly identical analysis candidates, rejections,
  warnings, stable keys, and result digests.
- Store a complete, auditable analysis run without mutating scanner or catalyst
  history.

## Non-Goals

- Covered calls, naked options, puts or calls without a defined-risk long leg,
  credit spreads, calendars, diagonals, iron condors, or 0DTE strategies.
- Position sizing, buying power, portfolio exposure, tax treatment, approval,
  paper execution, broker previews, or order submission.
- A Schwab client, OAuth, account data, option-chain network fetcher, streaming
  quotes, background jobs, polling, or automatic analysis runs.
- Predictive option pricing, volatility forecasting, probability-of-profit
  claims, automatic policy tuning, or model-driven selection.
- Dashboard expansion beyond serializable analysis results for later milestones.

## Architecture

The new `options_analysis` domain sits beside `market_data`, `scanner`, and
`catalysts` and contains no SQLAlchemy, HTTP, environment, wall-clock, broker,
approval, or order imports.

1. `AnalysisInputResolver` accepts a qualified scanner candidate, its immutable
   scanner lineage, the matching current catalyst decision, an option chain, and
   an explicit `as_of`.
2. `ContractValidator` verifies chain completeness, freshness, standard
   deliverables, contract timestamps, pricing sanity, liquidity, DTE, and delta
   eligibility. It returns accepted contracts and reason-coded rejections.
3. `SpreadConstructor` pairs contracts by direction, expiration, and strikes to
   form only legal debit spreads.
4. `SpreadCalculator` derives debit, payoff bounds, break-even, net Greeks,
   technical-stop reference, liquidity, and execution-quality values.
5. `WarningEvaluator` applies event context and option-position facts to produce
   earnings, ex-dividend, early-assignment, expiration, and pin-risk warnings.
6. `RankingService` sorts non-blocked spreads by a policy-defined canonical tuple
   and applies deterministic tie-breakers.
7. `OptionsReplayService` drives the production path from fixed fixtures with an
   injected virtual clock.
8. `OptionsAnalysisRepository` optionally persists a complete run, outcomes, and
   journal events in one caller-owned transaction.

The scanner remains the authority for candidate eligibility and direction. The
catalyst domain remains the authority for event state and risk windows. Options
analysis can block or rank its own spread outputs but cannot change scanner score,
catalyst decision, eligibility, or their historical records.

## Inputs And Authority

An analysis request requires all of the following:

- A `CandidateResult` whose status is qualified and whose direction is `bullish`
  or `bearish`.
- Immutable scanner run identity, signal identity, evidence digest, rule versions,
  and a scanner `as_of` not later than the analysis `as_of`.
- A current symbol-level catalyst decision and market-level event-risk state from
  Milestone 5. A blocked, stale, unresolved, or missing required input blocks
  analysis.
- A `NormalizedOptionChain` from Milestone 3 for the same display symbol, with a
  current valid `ObservationMetadata` record.
- A loaded `OptionsAnalysisPolicy` with an exact version and content hash.

No raw news text, generated summary text, chain provider payload, account data,
credential, approval state, or order-shaped value becomes a policy input. The
analysis input digest includes only canonical authoritative structured data,
version identifiers, and policy hashes. Display text, database IDs, creation times,
and input order are excluded.

## Contract Validation

Each option contract is considered independently before pairing.

### Chain-Level Rules

- Underlying must equal the scanner candidate symbol after canonical normalization.
- The chain must be complete, `valid`, and current according to the existing
  Milestone 3 option-chain freshness contract at the explicit analysis `as_of`.
- The chain must include a source timestamp and a nonempty immutable contract
  collection. Unknown, stale, degraded, quarantined, unavailable, partial, or
  conflicting states block the complete analysis.
- Naive timestamps, non-finite values, and nonpositive underlying price reject the
  complete analysis.

### Contract-Level Rules

- Deliverable must be `standard`; adjusted, unknown, mini, fractional, and other
  nonstandard deliverables are rejected.
- Expiration must be 30 through 60 calendar days after the analysis date,
  inclusive. Earlier and later expirations are rejected rather than rounded.
- Strike, bid, ask, last, implied volatility, absolute delta, open interest, and
  volume must be finite, nonnegative decimal values where applicable.
- Bid must be positive, ask must be positive, and bid must not exceed ask. A
  crossed, zero-bid, or zero-ask contract is rejected.
- Absolute delta must fall in the configured long-leg or short-leg band for its
  intended role. No sign inference is made from a malformed option type.
- Open interest and volume must meet their configured inclusive floors.
- Relative bid/ask width is `(ask - bid) / midpoint`, where midpoint is
  `(bid + ask) / 2`; zero midpoint rejects the contract. Width above the policy
  ceiling rejects the contract.

## Spread Construction And Calculations

Only same-expiration, two-leg vertical debit spreads are allowed.

### Bull Call Spread

For a bullish scanner candidate, buy one call at lower strike `K_long` and sell
one call at higher strike `K_short`, where `K_long < K_short`. The entry debit is
the long-leg ask minus the short-leg bid. The spread is invalid when debit is not
strictly positive or is greater than or equal to width `K_short - K_long`.

- Maximum loss: `debit * 100`.
- Maximum gain: `(K_short - K_long - debit) * 100`.
- Break-even: `K_long + debit`.
- Net delta, gamma, theta, and vega: long-leg Greek minus short-leg Greek.

### Bear Put Spread

For a bearish scanner candidate, buy one put at higher strike `K_long` and sell
one put at lower strike `K_short`, where `K_long > K_short`. Debit and payoff
validation follow the same rules.

- Maximum loss: `debit * 100`.
- Maximum gain: `(K_long - K_short - debit) * 100`.
- Break-even: `K_long - debit`.
- Net delta, gamma, theta, and vega: long-leg Greek minus short-leg Greek.

The technical-stop reference is derived from the source candidate's immutable
technical invalidation price. For bullish spreads it is the candidate stop below
the underlying; for bearish spreads it is the candidate stop above the underlying.
Missing, nonpositive, or directionally inconsistent stops block the candidate.
It is reference information only and never represents an order instruction.

## Liquidity And Execution Quality

The analysis reports, but does not execute, a conservative limit-price reference:
the debit midpoint rounded to the configured cent increment. It must not be
interpreted as a broker instruction.

Spread liquidity is the minimum of the two legs' open interest and volume. Spread
relative width is the sum of each leg's executable-side width divided by the
debit midpoint. Execution quality is classified by policy from the largest leg
width and spread width: `good`, `acceptable`, or `poor`. `poor` blocks selection;
the other states remain explicit in the result.

All monetary outputs use decimal strings and a fixed contract multiplier of 100.
No float arithmetic, price rounding beyond the displayed cent reference, or hidden
slippage assumption is permitted.

## Warning Model

Warnings are immutable records with a stable code, severity (`info`, `warning`,
or `block`), explanatory facts, and source lineage. A blocked warning excludes a
spread from ranked selectable outputs but retains it in the analysis result.

- `earnings_risk`: block when the Milestone 5 earnings state is active,
  unresolved, stale, or missing for the candidate symbol.
- `ex_dividend_risk`: warning when a known ex-dividend date is before expiration;
  block when it is on or before the next XNYS session and the short call is
  in-the-money. The initial source is a structured fixture-backed corporate-action
  input; no provider adapter is added.
- `early_assignment_risk`: warning for a short call that is in-the-money with a
  known ex-dividend date before expiration; block under the ex-dividend rule
  above. Short puts receive an informational early-assignment caveat only.
- `expiration_risk`: warning when expiration falls on or before the policy's
  configured minimum remaining-session threshold at analysis time.
- `pin_risk`: warning when the underlying is within the configured percentage
  distance of the short strike; a policy-defined stricter distance blocks the
  spread.

Known high-impact macro risk is already reflected in the scanner/catalyst input.
If the market-level catalyst state is blocked or unresolved, the complete analysis
is blocked with `macro_risk_active` or `macro_risk_unresolved` rather than treating
it as a spread-level warning.

## Versioned Configuration

`apps/api/config/options_analysis/options-analysis-policy-v1.json` is an exact,
canonical configuration document. It contains its version, SHA-256 content hash,
and these fixed values:

- `dte_min: "30"`, `dte_max: "60"`, and `contract_multiplier: "100"`.
- Standard-deliverable requirement and cent increment `"0.01"`.
- Long and short absolute-delta bands.
- Minimum per-leg open interest and volume.
- Maximum per-leg relative width and maximum spread relative width.
- Minimum remaining-session threshold and pin-risk warning/block distances.
- A stable ranking tuple and all reason and warning vocabulary.

Unknown keys, duplicate rule IDs, invalid decimal strings, overlapping or inverted
ranges, unsupported policy versions, and hash mismatches reject configuration.
Runtime flags cannot relax DTE, standard-deliverable, liquidity, or warning-block
boundaries.

## Deterministic Identity And Replay

Stable keys use length-prefixed UTF-8 components and SHA-256 when a compact key is
required. Canonical JSON uses sorted keys, compact separators, exact decimal
strings, aware UTC timestamps, and no NaN or infinity.

- Analysis run key includes scanner run key, candidate key, chain authoritative
  digest, catalyst-decision keys, corporate-action input digest, analysis `as_of`,
  and options-policy version/hash.
- Contract evaluation key includes run key, contract ID, authoritative contract
  digest, and intended leg role.
- Spread key includes run key, direction, expiration, long contract ID, short
  contract ID, and options-policy version.
- Result digest covers authoritative input identity, accepted/rejected contract
  outcomes, spread calculations, warnings, ranks, and stable reason codes.

The same inputs in another order must produce the same results. A changed
authoritative payload under a stable key is a conflict that aborts persistent
storage. Display-only descriptions and user-facing Chicago renderings cannot
change any key, calculation, rank, or digest.

## Persistence And Audit

Milestone 6 adds one migration after `20260719_0004`.

### Analysis Runs

`options_analysis_runs` stores unique run key, scanner run/candidate keys,
option-chain digest, catalyst input digest, corporate-action input digest, policy
version/hash, analysis `as_of`, status, sorted reasons, result digest, correlation
ID, and creation time.

### Contract Evaluations

`option_contract_evaluations` stores the unique evaluation key, parent run,
contract identity/digest, intended leg role, expiration, strike, option type,
pricing and liquidity inputs, acceptance state, sorted reasons, and creation time.

### Spread Candidates

`option_spread_candidates` stores unique spread key, parent run, direction,
expiration, long/short contract identities, debit, payoff bounds, break-even, net
Greeks, technical-stop reference, liquidity metrics, execution-quality state,
rank, blocked state, canonical calculation payload, and creation time.

### Warnings And Atomicity

`option_spread_warnings` stores each stable spread-warning key, parent spread,
code, severity, bounded structured facts, source lineage, and creation time. Run
records and their children are append-only through repository APIs. SQLite triggers
prevent update/delete; PostgreSQL-compatible indexes and constraints are required.

Repositories flush but do not commit. The caller owns one transaction that appends
these bounded journal events:

- `options_analysis_run.recorded`
- `option_contract_evaluation.recorded`
- `option_spread_candidate.recorded`
- `option_spread_warning.recorded`

An exact rerun returns existing records without duplicate events. Any stable-key
digest conflict, missing scanner candidate, mismatched symbol, or missing required
lineage rolls back the complete run.

## CLI And Fixtures

The offline CLI will support:

```text
python -m market_trader.options_analysis.cli validate <dataset-path>
python -m market_trader.options_analysis.cli analyze <dataset-path> [--database-url URL]
```

`validate` checks fixture stream hashes, policy versions/hashes, timestamps,
schema versions, expected counts, reason summaries, and expected result digest.
`analyze` uses the same production path in memory or, with an explicit database
URL, migrates and persists it in one transaction. Neither command contacts a
provider or reads credentials.

Exit `0` is success, `2` is invalid fixture/configuration/input, and `3` is an
unexpected analysis or persistence failure. Output is one compact sorted JSON
object. Diagnostics do not echo database URLs, raw provider payloads, credentials,
or any order-shaped instruction.

Production fixtures are synthetic, credential-free, fixed in 2026, ordered by
nondecreasing ingest time, and include:

- Eligible bullish and bearish scanner candidates with standard chains.
- Exact 30- and 60-DTE accepted boundaries plus 29- and 61-DTE rejections.
- Standard and adjusted/nonstandard deliverable scenarios.
- Open-interest, volume, bid/ask, width, delta, stale, incomplete, crossed, and
  zero-price boundaries.
- Valid bull call and bear put payoff, Greeks, ranking, and deterministic
  tie-break scenarios.
- Earnings, known ex-dividend, early-assignment, expiration, pin-risk, macro,
  unresolved-event, and warning-boundary scenarios.
- Duplicate replay, input reordering, stable-key conflicts, and atomic rollback.
- XNYS holidays, early closes, daylight-saving transitions, and Chicago rendering.

## Testing And Exit Criteria

Unit tests cover configuration validation, exact decimal calculations, every
contract validation rule, spread legality, warning severities, ranking, canonical
identity, and sanitization. Integration tests cover fixture validation, in-memory
analysis, persistent SQLite analysis, migration upgrade, idempotent rerun, audit
events, and rollback on conflict. Existing Milestone 3, 4, and 5 suites remain
unchanged except for intentional integration contract additions.

Milestone 6 is complete only when identical chains yield identical results,
invalid or illiquid contracts are rejected with reasons, maximum loss and
assignment stress are stored and rendered, all fixture scenarios pass offline,
and no path can reach sizing, approval, broker preview, or order submission.
