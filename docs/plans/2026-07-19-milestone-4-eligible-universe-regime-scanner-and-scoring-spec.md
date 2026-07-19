# Milestone 4 Eligible Universe, Regime, Scanner, And Scoring Specification

Date: July 19, 2026  
Status: Approved specification
Depends on: Milestones 1-3  
Roadmap milestone: 4

## Purpose

Milestone 4 generates deterministic, explainable bullish and bearish candidates
from provider-neutral market inputs. It adds a versioned curated universe,
eligibility decisions, regime classification, five strategy evaluators,
correlation-aware scoring, replay, and transactional persistence.

This milestone is paper-analysis only. A candidate is an analytical result, not a
trade recommendation or executable instruction. It cannot become approval-ready,
be sized, select an option, create an order intent, or reach a broker.

## Approved Design Decisions

- Use a typed deterministic pipeline rather than a generic rule language or a
  monolithic scanner service.
- Derive price and volume features from Milestone 3 observations. Breadth,
  sector, volatility, macro, and catalyst evidence enter through typed,
  fixture-backed project contracts.
- Use an explicit versioned allowlist. Do not discover or add symbols
  automatically.
- Make news continuation executable from typed attributed fixture evidence;
  Milestone 5 may later populate the same contract.
- Persist eligibility and strategy decisions for every evaluated symbol. Create
  candidate rows only for signals that pass all gates and the score threshold.
- Use conservative reference thresholds that are versioned and explicitly
  uncalibrated.
- Use evidence families with contribution caps to prevent correlated evidence
  from being counted repeatedly.
- Execute only through an explicit application service and CLI. Milestone 2 may
  plan run times, but Milestone 4 starts no scheduler or worker.
- Use fixed UTC `as_of` values for calculations and fixtures. User-facing local
  examples use the IANA zone `America/Chicago`; exchange sessions remain
  `America/New_York`.

## Goals

- Evaluate a fixed sample universe from immutable, versioned inputs.
- Represent eligibility as `eligible`, `ineligible`, or `blocked` with stable
  reason codes and observed values.
- Classify the market as `bullish`, `bearish`, `neutral`, `mixed`, or `blocked`.
- Evaluate bullish breakout, bullish pullback, bearish breakdown, bearish
  failed-rally, and news-continuation strategies.
- Produce a deterministic `0` through `100` score with exposed component and
  evidence-family contributions.
- Persist scan runs, all decisions, passing candidates, and bounded audit
  metadata atomically and idempotently.
- Replay fixed scanner fixtures without a database and optionally persist the
  same outcomes through an explicit database URL.
- Make every candidate reconstructable from configuration versions, input
  references, observations, gates, score components, and reason codes.

## Non-Goals

- External market, breadth, macro, volatility, news, social, or Schwab clients.
- Background polling, automatic scans, queues, workers, or cron management.
- Language-model sentiment, eligibility, regime, strategy, or scoring decisions.
- Predictive calibration, optimization, backtest performance claims, or
  automatic threshold tuning.
- Options selection, spread construction, sizing, portfolio risk, tax analysis,
  approvals, simulated execution, broker previews, or order submission.
- Scanner or candidate UI. Dashboard expansion remains Milestone 8.
- Changes to Milestone 3 normalization or freshness semantics except narrow
  project-owned query interfaces needed to assemble scanner inputs.

## Architecture

The scanner is a sequence of small typed components:

1. `ScanInputAssembler` resolves a versioned allowlist and immutable market and
   supplemental evidence at one explicit `as_of` value.
2. `FeatureCalculator` derives adjusted daily and completed intraday features
   without reading a wall clock.
3. `EligibilityEvaluator` emits one decision for every allowlisted symbol.
4. `RegimeClassifier` emits one market-level regime assessment.
5. Strategy evaluators consume only eligible symbols, compatible regime state,
   and their declared input contracts.
6. `EvidenceScorer` applies component weights and evidence-family caps.
7. `CandidateSelector` emits candidates only when all required gates pass and
   final score is at least the configured threshold.
8. `ScanRunService` produces a deterministic result in memory and optionally
   writes the complete run through one repository transaction.

Each stage returns immutable domain values. It does not persist, log raw payloads,
read environment credentials, or call another stage's internals. Persistence is
an outer application concern.

## Temporal Model

Every scan requires an aware UTC `as_of` timestamp and an XNYS session date.
Naive timestamps are rejected. The scanner does not call `utc_now()` or sleep.

Daily indicators use only daily candles for sessions completed before `as_of`.
Intraday indicators use only completed one-minute candles whose end is at or
before `as_of`. A current-session aggregate is derived from those completed
candles; an unfinished one-minute interval is never synthesized.

Relative intraday volume compares current cumulative volume with the median
cumulative volume at the same completed minute offset over the previous twenty
comparable regular sessions. A strategy requiring relative volume is blocked
when fewer than twenty comparable sessions exist. Early-close sessions are
comparable only through elapsed regular-session minute offset. Missing intervals
do not become zero volume.

Supplemental observations carry `observed_at`, `valid_until`, source, schema
version, configuration version, correlation identifier, and evidence lineage.
An observation is stale when `as_of > valid_until`; equality remains valid.

Mixing session dates, using observations after `as_of`, or combining incompatible
configuration versions produces a blocked input bundle. There is no fallback to
the current time, latest database row regardless of timestamp, or a neutral
default.

## Versioned Configuration

Milestone 4 checks in human-reviewable JSON configuration with canonical hashes.
Configuration is parsed into typed immutable values before evaluation.

Version-one identifiers are:

- Universe: `eligible-universe-v1`
- Eligibility policy: `eligibility-policy-v1`
- Feature policy: `scanner-features-v1`
- Regime policy: `market-regime-v1`
- Strategy rules: `scanner-strategies-v1`
- Scoring policy: `candidate-scoring-v1`
- Supplemental evidence schema: `scanner-evidence-v1`
- Scanner fixture schema: `scanner-fixture-v1`

Unknown versions fail validation. Changing a symbol, threshold, formula, weight,
cap, reason code meaning, or required input creates a new version. Existing runs
retain the original identifier and content hash.

## Reference Universe

The version-one sample allowlist contains thirty symbols:

- Broad ETFs: `SPY`, `QQQ`, `IWM`, `DIA`
- Sector ETFs: `XLB`, `XLC`, `XLE`, `XLF`, `XLI`, `XLK`, `XLP`, `XLRE`,
  `XLU`, `XLV`, `XLY`
- Common stocks: `AAPL`, `MSFT`, `NVDA`, `AMZN`, `META`, `GOOGL`, `TSLA`,
  `AMD`, `AVGO`, `JPM`, `XOM`, `UNH`, `LLY`, `WMT`, `COST`

The list is a reproducible sample configuration, not a recommendation or an
assertion that each symbol will always satisfy liquidity requirements. Membership
permits evaluation only. Eligibility rules decide whether a member participates
in a specific run.

Universe entries declare display symbol, expected security type, exchange family,
sector classification when applicable, benchmark role, and active date range.
Duplicate symbols, unsupported types, overlapping active records, unknown sector
codes, and missing benchmark roles fail configuration validation.

The four broad ETFs and eleven sector ETFs may be regime inputs even when the
candidate policy is configured not to emit candidates for benchmark symbols.
Version one allows candidates for all eligible entries but records each entry's
role in the explanation.

## Input Contracts

### Market Input Bundle

For each symbol, the assembler supplies:

- Symbol and instrument identity from the Milestone 1 repository.
- Security type, exchange, active state, and universe role.
- At least 200 completed adjusted daily candles for global eligibility.
- Current-session completed one-minute candles when a strategy uses intraday
  confirmation.
- Latest structurally valid quote and provider operational state.
- Applicable corporate actions and adjustment support state.
- Source event IDs, ingestion keys, payload digests, observation timestamps,
  quality states, and configuration versions.

Only `valid` or explicitly permitted `degraded` observations may enter features.
Stale or quarantined observations never enter calculations. Locked quotes may be
measured but block any strategy configured to require an unlocked top of book.
Unsupported adjusted deliverables and unresolved corporate actions block the
symbol.

### Breadth Evidence

`BreadthEvidence` contains total eligible issues, advancing issues, declining
issues, unchanged issues, issues above their 50-session average, and aggregate up
and down volume. Counts must be nonnegative and internally consistent. Breadth
must refer to one declared source universe and session.

### Sector Evidence

`SectorEvidence` contains one observation for each of the eleven sector ETFs,
including close relative to its 50-session average and 20-session return. Missing,
duplicate, or stale sector observations block regime classification.

### Volatility Evidence

`VolatilityEvidence` contains a named broad-market volatility measure, current
value, value five completed sessions earlier, twenty-session median, source, and
timestamps. Values must be finite nonnegative decimals. Version one uses direction
from the five-session percentage change; it does not assume one provider symbol.

### Macro Evidence

`MacroEvidence` carries a project-owned state of `risk_on`, `neutral`,
`risk_off`, or `blocked`, plus attributed reason codes and lineage. Milestone 4
does not derive this state from external releases. Fixtures may supply it;
Milestone 5 may later implement an adapter that produces the same contract.

### Catalyst Evidence

`CatalystEvidence` contains an evidence ID, symbol, attributed source reference,
published and observed timestamps, materiality (`material` or `non_material`),
direction (`positive`, `negative`, or `unclear`), evidence category, valid-until
timestamp, and lineage ID. It contains no article body, model-generated sentiment,
credential, instruction text, or executable content.

News continuation requires material evidence with positive or negative direction
published no earlier than the start of the second completed XNYS session before
the scan session. `as_of` must not exceed `valid_until`. Multiple records sharing
one lineage count once.

## Feature Calculations

Calculations use `Decimal`; binary floating point is prohibited for thresholds,
scores, prices, ratios, and weights.

Version-one features are:

- `sma_20`, `sma_50`, and `sma_200`: arithmetic means of adjusted daily closes.
- `sma_50_slope_20`: current `sma_50` minus `sma_50` twenty completed sessions
  earlier, divided by the earlier value.
- `prior_20_high` and `prior_20_low`: extrema of the twenty completed daily
  sessions preceding the current scan session; current-session data is excluded.
- `median_dollar_volume_20`: median of adjusted close multiplied by daily volume
  for the previous twenty completed sessions.
- `session_open`, `session_high`, `session_low`, `session_close`, and
  `session_volume`: aggregate of completed current-session one-minute candles.
- `session_vwap`: sum of minute VWAP multiplied by minute volume divided by total
  volume. It is unavailable when total volume is zero or a required minute VWAP is
  absent.
- `relative_volume_20`: current cumulative volume divided by the median cumulative
  volume at the same session minute offset over twenty comparable sessions.
- `return_20`: adjusted close return over twenty completed sessions.
- `relative_strength_percentile_20`: percentile rank of `return_20` among eligible
  candidate-role universe members. Ties receive the same deterministic minimum
  rank; symbols are ordered by display symbol only as a final stable tie breaker.

Division by zero, nonfinite values, inconsistent OHLC, duplicate candles, missing
required intervals, or adjustment discontinuities produce blocked features with
stable reason codes.

## Eligibility Policy Version One

Global eligibility is evaluated for every allowlisted symbol before regime or
strategy logic.

An entry is `eligible` only when all conditions pass:

- Symbol repository record is active and matches the configured display symbol.
- Security type is U.S.-listed common stock or unleveraged ETF.
- Latest adjusted close is from `$10.00` through `$1,000.00`, inclusive.
- At least 200 completed daily sessions are available.
- Twenty-session median daily dollar volume is at least `$25,000,000`, inclusive.
- Required daily observations are fresh and structurally valid.
- Provider state is not unavailable.
- No halt, non-updating critical quote, unsupported adjustment, or unresolved
  corporate action applies.

`ineligible` means complete evidence proves a rule failed. `blocked` means the
system cannot decide safely. Stable global reason codes include:

- `not_in_universe`
- `inactive_symbol`
- `security_type_ineligible`
- `price_below_minimum`
- `price_above_maximum`
- `dollar_volume_below_minimum`
- `insufficient_daily_history`
- `halted_symbol`
- `non_updating_quote`
- `stale_market_data`
- `provider_unavailable`
- `unsupported_adjustment`
- `unresolved_corporate_action`
- `missing_required_input`
- `conflicting_input`

An eligible symbol may still have a strategy-specific `blocked` result, such as
insufficient comparable intraday sessions. Ineligibility does not become a low
score and cannot be overcome by strategy evidence.

## Regime Policy Version One

The classifier emits a signed component total from `-100` through `+100` and a
state. Each component is independently explainable.

### Broad Trend: 30 Points

- `+30` when `SPY` adjusted close is above `sma_50`, `sma_50` is above
  `sma_200`, and `sma_50_slope_20 > 0`.
- `-30` when close is below `sma_50`, `sma_50` is below `sma_200`, and
  `sma_50_slope_20 < 0`.
- Otherwise `0`.

### Breadth: 20 Points

- `+20` when at least 60% of issues are above their 50-session average and the
  advance/decline ratio is at least `1.50`.
- `-20` when at most 40% are above their 50-session average and the
  advance/decline ratio is at most `0.67`.
- Otherwise `0`.

When declining issues are zero with at least one advancer, the ratio is positive
infinity for threshold comparison but is serialized as the reason
`no_declining_issues`; no nonfinite number is stored. The bearish mirror applies
when advancers are zero.

### Sector Participation: 15 Points

- `+15` when at least 7 of 11 sector ETFs close above their 50-session average.
- `-15` when at least 7 of 11 close below their 50-session average.
- Otherwise `0`.

Equality to the average is neutral for that sector.

### Volume Participation: 10 Points

- `+10` when aggregate up-volume/down-volume ratio is at least `1.50`.
- `-10` when the ratio is at most `0.67`.
- Otherwise `0`.

Zero-denominator handling follows the breadth rule and records a reason rather
than a nonfinite persisted value.

### Volatility Direction: 15 Points

- `+15` when the named volatility measure decreased at least 5% over five
  completed sessions.
- `-15` when it increased at least 5%.
- Otherwise `0`.

### Macro Overlay: 10 Points

- `risk_on`: `+10`
- `neutral`: `0`
- `risk_off`: `-10`
- `blocked`: block the regime

### Classification

Critical trend, breadth, sector, or volatility evidence that is stale, missing,
or conflicting produces `blocked`.

When broad trend and breadth have opposite nonzero signs, or fewer than 7 sectors
align while sector returns span both positive and negative directions, the state
is `mixed`. The signed total remains available as directional context.

Otherwise:

- Total at least `+35`: `bullish`
- Total at most `-35`: `bearish`
- All other totals: `neutral`

Strategies may accept `mixed` only when its signed total has the strategy's
direction and absolute value is at least `20`. A blocked regime blocks every
strategy; it never becomes neutral.

## Strategy Rules Version One

All strategy outputs have status `passed`, `failed`, `blocked`, or
`not_applicable`. They include direction, observations, required gates, reason
codes, evidence lineage, and component inputs. A strategy is scored only after
all required inputs are available; a failed gate may still receive a diagnostic
score, but it cannot create a candidate.

### Bullish Breakout

Required gates:

- Established uptrend: latest completed daily close > `sma_50` > `sma_200` and
  `sma_50_slope_20 > 0`.
- Latest completed one-minute close > `prior_20_high`.
- `relative_volume_20 >= 1.50`.
- Regime is bullish, or mixed with signed total at least `+20`.
- Current session close is not below session VWAP.

### Bullish Pullback

Required gates:

- Established uptrend as defined above.
- Current session low is within 1% above or below `sma_20`.
- Current session low remains strictly above `sma_50`.
- The latest completed five-minute aggregate closes above its open and above the
  preceding completed five-minute aggregate high.
- Regime is bullish, neutral with nonnegative total, or mixed with positive total.

Five-minute aggregates are derived from complete groups of five one-minute bars
aligned to XNYS regular-session open. Partial groups are ignored.

### Bearish Breakdown

Required gates mirror bullish breakout:

- Established downtrend: close < `sma_50` < `sma_200` and
  `sma_50_slope_20 < 0`.
- Latest completed one-minute close < `prior_20_low`.
- `relative_volume_20 >= 1.50`.
- Regime is bearish, or mixed with signed total at most `-20`.
- Current session close is not above session VWAP.

### Bearish Failed Rally

Required gates mirror bullish pullback:

- Established downtrend as defined above.
- Current session high is within 1% above or below `sma_20`.
- Current session high remains strictly below `sma_50`.
- Latest completed five-minute aggregate closes below its open and below the
  preceding completed five-minute aggregate low.
- Regime is bearish, neutral with nonpositive total, or mixed with negative total.

### News Continuation

Required gates:

- At least one current material catalyst with clear positive or negative
  direction and attributed source reference.
- Positive evidence requires latest completed one-minute close above session
  VWAP; negative evidence requires close below session VWAP.
- `relative_volume_20 >= 1.50`.
- The latest completed one-minute close remains on the catalyst side of the
  current session open.
- Regime is not blocked and its signed total is not opposite the catalyst
  direction by 35 points or more.

Conflicting positive and negative material evidence from independent lineages
blocks news continuation with `conflicting_catalyst_direction`. Unclear or
non-material evidence is retained for explanation but cannot satisfy the gate.

### Strategy Status And Reason Vocabulary

Each technical evaluator runs once for every globally eligible symbol. News
continuation also runs once, but returns `not_applicable` when no current material
catalyst exists. A supplied stale, malformed, or conflicting catalyst produces
`blocked`, not `not_applicable`.

Version-one strategy and shared-feature reason codes are:

- `regime_blocked`
- `regime_not_compatible`
- `trend_not_established`
- `breakout_not_confirmed`
- `breakdown_not_confirmed`
- `pullback_zone_not_reached`
- `failed_rally_zone_not_reached`
- `reversal_not_confirmed`
- `relative_volume_below_minimum`
- `insufficient_intraday_history`
- `price_below_vwap`
- `price_above_vwap`
- `session_open_not_held`
- `missing_session_vwap`
- `catalyst_missing`
- `catalyst_stale`
- `catalyst_not_material`
- `catalyst_direction_unclear`
- `conflicting_catalyst_direction`
- `price_confirmation_missing`
- `duplicate_evidence_lineage`
- `feature_division_by_zero`
- `feature_nonfinite`
- `feature_input_missing`
- `feature_input_conflicting`
- `regime_input_missing`
- `regime_input_stale`
- `regime_input_conflicting`
- `macro_blocked`
- `trend_breadth_divergence`
- `sector_dispersion`

Reasons are sorted and deduplicated before persistence and digest creation.
Changing a code's meaning requires a new applicable policy version.

## Scoring Policy Version One

Scores use six-decimal `Decimal` arithmetic and are clamped from `0` through
`100`. The candidate threshold is `70.000000`, inclusive. Required gates and
score threshold must both pass.

Evidence families and maximum contributions are:

- `market_direction`: 25 points
- `price_structure`: 30 points
- `participation_liquidity`: 20 points
- `relative_performance`: 15 points
- `catalyst`: 10 points

The five component scores correspond to those families. Multiple observations in
one lineage are deduplicated before scoring. Multiple lineages in one family may
improve confidence but cannot exceed the family cap. A component may not borrow
unused points from another family.

### Market Direction: 25

- Established strategy-direction trend: 15.
- Regime aligned with direction: 10.
- Neutral regime: 5 for pullback or failed-rally, otherwise 0.
- Mixed regime with compatible signed direction: 5.
- Opposite or blocked regime: 0.

### Price Structure: 30

- Required price trigger passes: 20.
- Trigger distance is at least `0.25%` beyond breakout/breakdown level, or
  pullback/failed-rally reversal closes at least `0.25%` beyond the preceding
  five-minute extreme: additional 5.
- Session price is on the correct side of VWAP: additional 5.

News continuation assigns 20 for holding the catalyst side of session open, 5
for correct VWAP side, and 5 when distance from VWAP is at least `0.25%`.

### Participation And Liquidity: 20

- Eligibility dollar-volume threshold passes: 5.
- Relative volume `1.50` through less than `2.00`: 10; `2.00` or greater: 15.

### Relative Performance: 15

- Bullish direction at or above the 70th percentile, or bearish direction at or
  below the 30th percentile: 10.
- Bullish at or above the 85th, or bearish at or below the 15th: 15.
- Otherwise 0.

### Catalyst: 10

- Current material, attributed, directionally compatible evidence: 10.
- Otherwise 0.

Technical strategies do not require catalyst points and can reach 90. News
continuation requires catalyst points. Language-model output and unattributed
text are not score inputs.

Boundary tests cover `69.999999`, `70.000000`, and `70.000001`. Explanation
payloads include pre-cap contributions, applied caps, final contributions, gate
states, and source lineage IDs.

## Candidate Selection

A candidate is emitted only when:

- Global eligibility is `eligible`.
- Regime is not blocked and satisfies the strategy gate.
- Strategy status is `passed`.
- Every required gate is true.
- Final score is at least `70.000000`.
- No blocking reason applies.

Candidate direction is `bullish` or `bearish`; it does not contain order side,
quantity, expiration, strike, limit price, stop, target, or risk allocation.
Candidate status is exactly `qualified`. No Milestone 4 API can transition it to
an approval or proposed-trade state.

When more than one strategy qualifies for the same symbol and direction, each
strategy has its own signal and candidate. This preserves explainability. Later
milestones may group them for display, but Milestone 4 does not collapse distinct
strategies into one candidate.

## Deterministic Identity And Digests

Canonical JSON uses sorted keys, compact separators, UTF-8, no NaN, bounded
collections, and the Milestone 3 sanitizer.

- Input digest covers sanitized input references and supplemental evidence,
  including source event IDs, ingestion keys, payload digests, timestamps, and
  schema/configuration versions. It does not duplicate raw payloads.
- Run key covers `as_of`, session date, all policy versions, universe content
  hash, and input digest.
- Eligibility key covers run key and symbol.
- Signal key covers run key, symbol, strategy identifier, and strategy version.
- Candidate key covers signal key and scoring-policy version.
- Result digest covers ordered regime, eligibility, signal, and candidate outcome
  records with scores and reason codes. Random database IDs and wall-clock values
  are excluded.

An exact rerun returns the existing result without duplicate rows or audit events.
The same stable key with a different digest is an infrastructure conflict and
never overwrites the prior record.

## Persistence Model

Milestone 4 adds an Alembic migration compatible with SQLite and PostgreSQL.

### Scan Runs

`scanner_runs` stores stable run key, `as_of`, session date, input digest,
universe and policy versions, regime state and signed score, sanitized explanation,
result counts, result digest, status, correlation ID, and created timestamp.
Run key is unique. Indexes support session date, status, and correlation lookup.

### Eligibility Decisions

`eligibility_decisions` stores stable decision key, run ID, symbol ID, status,
reason codes, bounded observed-value payload, input digest, policy version,
correlation ID, and created timestamp. `(run_id, symbol_id)` and decision key are
unique. Reason codes use PostgreSQL JSONB with GIN and remain JSON on SQLite.

### Signals

The existing `signals` table gains stable signal key, scanner run ID, strategy
identifier, input digest, reason codes, gate payload, component-score payload, and
scoring-policy version. Existing direction, score, status, input snapshot,
explanation, strategy version, and correlation fields remain. Signal key is
unique. The existing singular input snapshot remains a primary trace reference;
the explanation contains the ordered full input-reference list.

Every globally eligible symbol receives exactly five signal rows, one per
strategy, including `failed`, `blocked`, and `not_applicable` outcomes. Globally
ineligible or blocked symbols receive eligibility rows but no signal rows.

### Candidates

The existing `candidates` table gains stable candidate key, scanner run ID,
strategy identifier, direction, input digest, and scoring-policy version.
Candidate key is unique. Status must be `qualified` for Milestone 4 writes.

### Audit

New audit event types are:

- `scanner_run.completed`
- `eligibility_decision.recorded`
- `scanner_signal.recorded`
- `scanner_candidate.qualified`

Audit payloads contain schema version, stable key, run key, symbol identity when
applicable, versions, status, score, reason codes, input digest, and result digest
when applicable. They do not copy full market or supplemental payloads.

The run, all decisions, signals, candidates, and audit events commit in one
transaction. Any flush, uniqueness, mapping, or audit error rolls back the whole
new run. Repository APIs expose no in-place update of completed decisions.

## Scanner Fixtures And Replay

Scanner fixture manifests declare:

- Dataset ID and description.
- Scanner fixture schema version.
- Fixed `as_of` and XNYS session date.
- Universe and every policy version plus content hash.
- Ordered references to Milestone 3 market-data fixture streams or dedicated
  scanner market streams using the same provider-event schema.
- Supplemental breadth, sector, volatility, macro, and catalyst files with
  SHA-256 and record counts.
- Expected regime state and score.
- Expected eligibility, blocked, failed, signal, and candidate counts.
- Expected reason summary and result digest.

Production fixture groups cover:

- Bullish breakout and pullback.
- Bearish breakdown and failed rally.
- Positive and negative news continuation.
- Neutral, mixed, and blocked regimes.
- Eligibility and score threshold boundaries.
- Stale, missing, conflicting, halted, and corporate-action inputs.
- Evidence-lineage deduplication and family caps.
- Exact rerun idempotence and changed-input conflict.
- Normal, early-close, and daylight-saving session timing.

Fixture values are synthetic and fixed in 2026. No fixture contains credentials,
accounts, cookies, authorization headers, provider tokens, article bodies, or
real customer data.

Replay advances only through recorded ingestion timestamps and the explicit scan
`as_of`. It never sorts by observation time or reads a wall clock. Each production
dataset is replayed twice into fresh memory sinks and must produce identical
results and digests.

## CLI

The standard-library CLI exposes:

```text
python -m market_trader.scanner.cli validate <dataset>
python -m market_trader.scanner.cli scan <dataset>
python -m market_trader.scanner.cli scan <dataset> --database-url sqlite:///path.db
```

`validate` and default `scan` are database-free. They load all manifests and
configuration, verify hashes/counts/versions, run in memory, compare expected
outcomes, and print one compact sorted JSON object.

Only `--database-url` enables migrations and repository persistence. Persistent
scan opens one session, commits one complete run, rolls back on any exception,
and prints the same canonical result as the in-memory validation. It does not
auto-create symbols; every universe symbol must resolve through the symbol
repository.

Exit codes are:

- `0`: validated or scanned successfully.
- `2`: dataset, configuration, schema, hash, expected-outcome, or temporal error.
- `3`: database, migration, repository, audit, or other infrastructure error.

Errors are one sanitized JSON object on stderr. Raw parser, SQLAlchemy, Alembic,
filesystem, or unsupported-object messages do not become stable contracts.

## Failure Semantics

Project-owned stable reason codes cross scanner package boundaries. Failures use
the narrowest safe scope:

- Invalid manifest or configuration: reject the dataset before evaluation.
- Critical regime input unavailable: regime and all strategies are blocked.
- Global eligibility failure with complete evidence: symbol is ineligible.
- Global eligibility evidence incomplete or stale: symbol is blocked.
- Strategy-specific evidence missing: only that strategy is blocked.
- Required gate false: strategy fails; it is not blocked.
- Correlated duplicate evidence: count once and expose deduplication reason.
- Persistence or audit failure: roll back the complete run.
- Existing stable key with different digest: infrastructure conflict.

The scanner never converts missing to zero, stale to fresh, blocked to neutral,
ineligible to a low score, failed gates to optional components, or conflicting
evidence to an arbitrary direction.

## Security And Safety Boundaries

- The scanner package imports no HTTP client, Schwab adapter, secret manager, or
  broker package.
- Supplemental evidence is structured data, never executable text or tool
  instructions.
- Catalyst source references are bounded identifiers or URLs for attribution;
  article bodies are excluded.
- Sanitization runs before diagnostics, persistence, audit, and digest creation.
- Database URLs are never printed.
- Configuration is local, versioned, and hash-verified; no remote rule update is
  accepted.
- Candidate output includes no approval or execution control.
- The application remains paper-only and rejects live mode.

## Testing Requirements

Unit tests cover:

- Every feature formula and zero/missing-data boundary.
- Eligibility exactly below, equal to, and above each threshold.
- Every global and strategy-specific stable reason code.
- All five regime states and six regime components.
- Positive, negative, failed, blocked, and not-applicable cases for all five
  strategies.
- Scores `69.999999`, `70.000000`, and `70.000001`.
- Evidence-lineage deduplication and every family cap.
- Decimal-only arithmetic and canonical explanation ordering.

Invariant and property-style tests prove:

- Ineligible or blocked symbols create no candidates.
- No candidate exists without one passing signal.
- A failed required gate cannot be overcome by score.
- Scores remain within `0` and `100`.
- Adding duplicate evidence with the same lineage cannot increase a score.
- Input order cannot change outcomes or digests.
- No observation after `as_of` affects a run.

Integration tests cover:

- Migration from a Milestone 3 database and Alembic metadata checks.
- SQLite append/idempotency behavior and PostgreSQL JSONB/GIN compilation.
- Atomic run, decision, signal, candidate, and audit persistence.
- Exact rerun without duplicate rows or audits.
- Changed-input conflict and full rollback.
- CLI memory and persistent paths with sanitized errors.
- Production fixture scenario inventory and deterministic digests.
- API container fixture/config packaging and non-root execution.

Full backend Ruff, strict mypy, pytest, migration, frontend regression, Docker
build, and foundation smoke checks remain required. Existing coverage must be
maintained or improved.

## Operations And Documentation

The Milestone 4 runbook documents:

- Backend development setup on macOS and Linux.
- Offline fixture validation and in-memory scan commands.
- SQLite migration, symbol seeding, persistent scan, and idempotent rerun.
- Inspection of run, eligibility, signal, candidate, and audit records.
- Adding or changing universe/rule configuration with version and digest review.
- Authoring scanner fixtures and reviewing expected digests.
- Interpretation of regime, eligibility, strategy, score, blocked, and conflict
  states.
- UTC source timestamps, Eastern exchange sessions, and `America/Chicago`
  user-facing examples.
- Confirmation that no network provider, Schwab credential, account access,
  approval, or order path exists.

The Docker image includes scanner fixtures and configuration. The foundation
smoke script validates one scanner dataset inside the non-root API container
without contacting a network data source.

## Acceptance Criteria

Milestone 4 is complete only when:

- Fixed input bundles produce identical regime, eligibility, signal, score,
  candidate, explanation, reason, and digest outputs.
- Every allowlisted symbol receives one persisted eligibility decision.
- Ineligible and blocked symbols cannot create candidates.
- Every candidate traces to one passing signal and complete versioned evidence.
- Correlated evidence cannot exceed its family cap or increase score when
  duplicated.
- All five strategy evaluators have passing, failing, and blocked fixture cases.
- Stale critical inputs and blocked regime state fail closed.
- Persistent exact reruns add no duplicate decisions, candidates, or audit events.
- A run writes atomically and conflicting input cannot overwrite prior evidence.
- CLI, migration, backend, frontend, container, and smoke checks pass.
- The runbook is complete and the roadmap marks only Milestone 4 complete.

## Deferred Work

- External catalyst, filings, news, macro, and social adapters: Milestone 5.
- Option-chain filtering and spread construction: Milestone 6.
- Position sizing, exposure, risk limits, and tax warnings: Milestone 7.
- Candidate and explanation dashboard views: Milestone 8.
- Approval, paper execution, and position lifecycle: Milestone 9.
- Production observability, security hardening, and recovery: Milestone 10.
- Schwab read-only integration: Milestone 11.
- Broker order contracts and live-mode work remain governed by Milestones 12-14.
