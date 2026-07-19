# Milestone 5 Catalysts, Events, News, And Filings Specification

Date: July 19, 2026
Status: Approved specification
Depends on: Milestones 1-4
Roadmap milestone: 5

## Purpose

Milestone 5 adds traceable event context without allowing external text or
language-model output to control trading decisions. It introduces provider-neutral
contracts, official SEC and BLS adapters, deterministic classification and risk
windows, replay, transactional persistence, and a narrow integration with the
Milestone 4 scanner.

This milestone remains paper-analysis only. A catalyst decision is context, not a
trade recommendation or executable instruction. It cannot become approval-ready,
select an option, size a position, create an order intent, or reach a broker.

## Approved Design Decisions

- Build a typed `catalysts` domain beside `market_data` and `scanner`.
- Keep the default runtime offline and make every network fetch explicit.
- Implement credential-free official adapters for SEC EDGAR public data and the
  unregistered BLS Public Data API. Broader economic providers remain typed
  contracts and fixtures.
- Implement fixture-backed provider interfaces for company news, earnings, and
  authorized social observations without selecting a commercial vendor.
- Classify materiality and direction only from allowlisted structured event types
  and numeric facts. Raw text is never a policy input.
- Apply conservative version-one risk windows: earnings from two XNYS sessions
  before through the first full session after, and high-impact macro from 60
  minutes before through 30 minutes after.
- Permit social observations to corroborate context, but never to confirm or
  upgrade a catalyst by themselves.
- Define cited, non-authoritative summary contracts and deterministic fixtures,
  but add no live language-model adapter.
- Persist source runs, observations, quarantine outcomes, decisions, and summaries
  atomically and idempotently with complete source lineage.
- Give Milestone 4 only immutable structured decisions, risk state, reasons, and
  lineage. Raw text and summaries never enter scanner scores or candidate keys.
- Use aware UTC timestamps internally, XNYS sessions for trading windows, and the
  IANA zone `America/Chicago` for user-facing examples.

## Goals

- Represent company news, earnings, SEC filings, economic releases, and authorized
  social observations through project-owned immutable contracts.
- Attribute every observation and decision to a source reference, publication
  time, ingestion time, stable event identity, and authoritative payload digest.
- Normalize and quarantine provider events through deterministic, versioned rules.
- Classify event family, category, materiality, direction, confirmation state, and
  event-risk state without inspecting prose.
- Detect stale, malformed, unavailable, duplicated, conflicting, and future-dated
  inputs with stable reason codes.
- Reproduce identical observations, decisions, risk windows, explanations, keys,
  and digests from fixed inputs.
- Persist new outcomes and their audit events in one caller-owned transaction.
- Populate the existing Milestone 4 catalyst evidence contract without giving
  external content authority over eligibility, scores, approvals, or orders.
- Support offline validation and replay plus explicit, bounded SEC and BLS fetches.

## Non-Goals

- Live commercial company-news, earnings-calendar, or social providers.
- FRED, BEA, or other keyed economic adapters in version one.
- Downloading or retaining article bodies, complete SEC filings, or social threads.
- Headline sentiment, keyword trading, embeddings, or prose-based direction.
- Live language-model calls, autonomous research, browsing agents, or tool use.
- Background polling, queues, workers, schedulers, or automatic scanner runs.
- Schwab APIs, OAuth, account data, broker previews, approvals, or orders.
- Options analysis, sizing, portfolio risk, tax analysis, or dashboard expansion.
- Predictive calibration, backtest performance claims, or automatic policy tuning.

## Architecture

The catalyst pipeline is a sequence of small typed components:

1. Source adapters return immutable provider-shaped events or explicit source
   failures. They do not normalize, persist, or classify.
2. `CatalystNormalizer` sanitizes first, validates source-specific structure, and
   emits a normalized observation or quarantine outcome.
3. `CatalystPolicyEvaluator` classifies structured observations under exact policy
   and source-policy versions.
4. `EventRiskEvaluator` calculates earnings and macro windows using an injected
   `as_of` and project-owned exchange calendar interface.
5. `CatalystDecisionService` resolves duplicates, corroboration, and conflicts into
   immutable symbol-level and market-level decisions.
6. `CatalystReplayService` runs recorded fixtures through the same production
   normalization and decision path with a virtual clock.
7. Repository sinks optionally persist a complete source run, observations,
   quarantine outcomes, decisions, summaries, and audit events in one transaction.
8. `ScannerCatalystAdapter` maps authoritative decisions into Milestone 4
   `CatalystEvidence` and macro-blocking inputs.

Domain components do not import SQLAlchemy, HTTP clients, environment settings,
wall-clock helpers, Schwab, broker, approval, order, or language-model packages.
Network and persistence concerns remain outer application adapters.

## Trust And Authority Model

Inputs are separated into four authority classes:

- `official_structured`: SEC and BLS facts from allowlisted official origins.
- `authorized_structured`: future configured news, earnings, and social provider
  fields covered by an explicit source policy.
- `external_text`: headlines, excerpts, filing descriptions, and social text.
- `generated_summary`: cited text produced by a summary provider or fixture.

Only `official_structured` and `authorized_structured` fields declared by the
active policy may affect materiality, direction, confirmation, conflicts, or risk
windows. External text and generated summaries are display-only context.

No adapter receives broker credentials, account identifiers, approval state,
candidate actions, arbitrary tools, shell access, or callback URLs. Provider
payloads cannot change source origins, request methods, headers, policy versions,
configuration, or subsequent fetch targets.

## Temporal Model

Every normalization, evaluation, replay, and scanner integration requires an aware
UTC `as_of`. Naive timestamps are rejected. Domain evaluation never reads the wall
clock.

Each observation carries:

- `published_at`: source publication or effective time in UTC.
- `ingested_at`: time the project received the event in UTC.
- `scheduled_for`: optional future event time in UTC.
- `valid_until`: policy-derived inclusive freshness boundary in UTC.

An observation is future-dated when `published_at` is more than five minutes after
`ingested_at` or after the explicit replay `as_of`. A future scheduled event is
valid only when represented by `scheduled_for`; publication time cannot be used as
a substitute. An observation is stale only when `as_of > valid_until`; equality
remains current.

Unscheduled material company events, earnings results, and material filing events
remain current through the close of the first full XNYS session after publication.
Contextual social observations remain current for 30 minutes and cannot confirm a
catalyst. Source-state observations use explicit provider-policy freshness.

## Versioned Configuration

Milestone 5 introduces exact, immutable configuration documents:

- `catalyst-source-policy-v1`: source IDs, authority classes, fixed origins,
  capabilities, rate limits, response bounds, and freshness.
- `catalyst-classification-policy-v1`: event categories, structured field rules,
  materiality, direction, corroboration, and conflict semantics.
- `event-risk-policy-v1`: earnings and macro categories, session rules, and block
  windows.
- `catalyst-summary-policy-v1`: citation requirements, text bounds, and explicit
  exclusion from authoritative decisions.
- `catalyst-fixture-v1`: manifest and stream contract.

Configuration files contain string-encoded decimal thresholds, exact versions,
and canonical content hashes. Unknown keys, categories, versions, source IDs,
authority classes, or reason codes are rejected. Runtime overrides cannot weaken
security boundaries or risk windows.

## Provider Contracts

### Provider Event

Every source adapter produces a `CatalystProviderEvent` with:

- Source ID and stable provider event ID.
- Event family and provider schema version.
- Publication and ingestion timestamps.
- Optional scheduled time and symbol identity.
- Structured fields as an immutable bounded mapping.
- Optional bounded external-text fields.
- Canonical source reference controlled by the adapter.
- Correlation identifier.

The canonical ingestion key is derived from source ID, provider event ID, and
provider schema version. An authoritative SHA-256 digest covers attribution,
timestamps, structured facts, and policy-relevant metadata; a separate external-
text digest covers bounded display text. The same key with another authoritative
digest is an identity conflict. A display-text-only difference returns the existing
authoritative observation and cannot create a conflict or another decision input.

### Provider Protocols

Project-owned protocols cover:

- `CompanyNewsProvider`
- `EarningsProvider`
- `SecFilingProvider`
- `EconomicReleaseProvider`
- `AuthorizedSocialProvider`
- `SummaryProvider`

Each protocol returns either events or a typed source failure. Unsupported,
unavailable, throttled, partial, and malformed states are explicit and cannot be
represented by an empty successful collection.

## Official SEC Adapter

The initial SEC adapter uses only fixed HTTPS resources under `data.sec.gov`:

- `/submissions/CIK##########.json` for filing identity and metadata.
- `/api/xbrl/companyfacts/CIK##########.json` for allowlisted XBRL facts.

The adapter does not use EDGAR filer APIs, tokens, submission endpoints, browser
automation, filing-document links, or arbitrary archive URLs. CIK values come from
versioned local symbol configuration and are rendered as ten digits. Version one
configures the 15 operating-company symbols in the Milestone 4 universe and marks
the 15 fund symbols explicitly unsupported for company-filing classification.

SEC public data requires no API key. Requests include a configured application
name and contact email in `User-Agent`, use fixed `Accept` and encoding headers,
and remain at or below five requests per second with one process-wide limiter. The
limit is intentionally below the SEC's published fair-access ceiling of ten
requests per second. Responses are capped at 10 MiB, use ten-second connect and
twenty-second total timeouts, and allow no cross-origin redirects.

Version one accepts filing metadata for `8-K`, `10-Q`, `10-K`, `6-K`, `20-F`, and
`40-F`, including amendments as distinct attributed events. Form type and
allowlisted item codes may establish materiality, but never positive or negative
direction by themselves. XBRL numeric facts may corroborate an existing structured
earnings event; they do not infer sentiment from labels or filing text.

Official API references reviewed for this design:

- [SEC EDGAR public data APIs](https://www.sec.gov/search-filings/edgar-application-programming-interfaces)
- [SEC developer resources and fair access](https://www.sec.gov/about/developer-resources)

## Official BLS Adapter

The initial macro adapter uses the unregistered BLS Public Data API and official
release calendar. It accesses only these fixed HTTPS resources:

- `api.bls.gov/publicAPI/v1/timeseries/data/` for allowlisted published series.
- `www.bls.gov/schedule/news_release/bls.ics` for scheduled release identity and
  Eastern publication time.

It never includes a registration key, parses schedule data from any other URL, or
scrapes linked release pages. Calendar event titles are mapped through an exact
allowlist; unknown titles remain contextual and cannot create a risk window.

Version-one series are configured, not discovered:

- `CUSR0000SA0`: Consumer Price Index for All Urban Consumers, all items,
  seasonally adjusted.
- `CES0000000001`: total nonfarm payroll employment, seasonally adjusted.
- `LNS14000000`: civilian unemployment rate, seasonally adjusted.

The source policy limits time-series requests to three series, one request at a
time, no more than five total BLS requests per minute, and no more than twenty
time-series requests per UTC day. This stays below BLS's documented unregistered
limits. Responses are capped at 2 MiB with ten-second connect and twenty-second
total timeouts.

BLS values are authoritative published observations, but BLS does not provide a
market-consensus value through this contract. Therefore BLS observations establish
release identity and risk state but have `neutral` direction unless corroborated by
an independent authorized structured event containing an attributed consensus.
The adapter never compares prose in a news release.

Official API references reviewed for this design:

- [BLS Public Data API](https://www.bls.gov/developers/home.htm)
- [BLS API signatures](https://www.bls.gov/developers/api_signature_v2.htm)
- [BLS limits and registration FAQ](https://www.bls.gov/developers/api_faqs.htm)
- [BLS release calendar](https://www.bls.gov/schedule/)

## Normalized Observation Contract

An accepted `CatalystObservation` contains:

- Stable observation key, authoritative payload digest, and external-text digest.
- Source ID, authority class, event family, and event category.
- Provider event ID and canonical source reference.
- Optional symbol ID and external symbol identity.
- Publication, ingestion, optional scheduled, and valid-until timestamps.
- Sorted immutable structured facts with exact decimal strings.
- Bounded external text stored separately from structured facts.
- Source, normalization, and fixture schema versions.
- Correlation ID and sorted source-quality reasons.

External text is excluded from observation identity beyond a separate content
digest. Differences in display-only text cannot alter materiality, direction, or
risk decisions. Structured fact changes under the same provider identity remain an
identity conflict rather than an update.

## Event Classification Policy Version One

Classification produces event category, materiality, direction, and reasons from
structured facts only.

### Earnings

An earnings result is `material` when actual and attributed consensus values are
both present and the absolute surprise is at least `2.000000%`. Direction is
`positive` above the threshold, `negative` below the negative threshold, and
`neutral` inside the band. Division by zero, mismatched periods or currencies,
restated values, and conflicting consensus values produce `blocked`.

Structured `guidance_raised` and `guidance_lowered` events are material and
positive or negative respectively only when old and new numeric ranges share the
same period, unit, and currency. A provider label without comparable numeric facts
is directionally unclear.

### Company Events

Version-one allowlisted structured categories are:

- `regulatory_approval`: material positive.
- `regulatory_denial`: material negative.
- `dividend_increase`: material positive when new amount exceeds old amount.
- `dividend_cut`: material negative when new amount is below old amount.
- `buyback_authorized`: material positive when amount and authorization date exist.
- `bankruptcy_filing`: material negative.
- `going_concern`: material negative.
- `cyber_incident`: material with unclear direction.
- `acquisition_announced`: material with unclear direction.
- `executive_change`: contextual with unclear direction.

Provider labels outside the allowlist remain `unknown` and cannot confirm a
catalyst. Text cannot supply a missing amount, date, category, or direction.

### SEC Filings

Allowlisted current-report and periodic forms are attributed filing events. A form
or item code can be material or contextual under configuration, but direction is
`unclear` unless an independent allowlisted structured fact establishes it.
Amendments never silently replace an earlier observation. Conflicting structured
facts preserve both lineages and block the affected decision.

### Economic Releases

CPI, Employment Situation, and FOMC rate decisions are high-impact macro
categories in the risk policy. The BLS adapter populates CPI and Employment
Situation observations. FOMC and other provider protocols remain fixture-backed in
version one. Macro events are market-level, not symbol-level catalysts.

Actual-versus-consensus direction requires independent attributed structured
consensus. Missing consensus leaves direction neutral and does not weaken the risk
window.

### Social Observations

Authorized social observations are contextual only. They may add lineage to an
already confirmed event when the symbol, category, and time window match, but they
cannot create, upgrade, or resolve a catalyst. Social-only input produces
`social_only_unconfirmed`.

## Confirmation And Conflict Rules

A symbol catalyst is `confirmed` only when at least one current, material,
attributed official or authorized structured observation has clear direction. A
current material observation with unclear direction remains `unconfirmed` unless a
compatible independent structured observation supplies direction.

Independent current material observations with opposite directions produce
`blocked` and `conflicting_catalyst_direction`. Duplicate observations from one
lineage never count as independent corroboration. Source unavailability does not
erase previously accepted current evidence, but an unavailable required source
state blocks decisions that depend on that source.

Decision explanations contain sorted source lineages, structured observations,
materiality, direction, risk windows, and reasons. They contain no article body,
filing body, prompt text, or summary text.

## Event-Risk Policy Version One

### Earnings Windows

A scheduled earnings event blocks dependent candidates beginning at the regular
XNYS open two sessions before the event session. It ends at the regular close of
the first full XNYS session after the event occurs.

- Before-market events use that trading date as the event session.
- After-market events use that trading date and still end after the next full
  session.
- Events with unknown time use the scheduled trading date and the conservative
  full-day window.
- Holidays and weekends are traversed with the exchange calendar, never calendar
  day arithmetic.
- Missing, stale, changed, or conflicting timing blocks the symbol.

Early-close sessions may be part of the pre-event window but are not the required
full post-event session. Exact window boundaries are inclusive.

### Macro Windows

High-impact macro releases block all dependent candidates from 60 minutes before
through 30 minutes after `scheduled_for`. CPI, Employment Situation, and FOMC rate
decisions are high impact in version one. Missing or conflicting high-impact
schedule data blocks the market-level macro input.

Lower-impact releases are contextual and do not block. Source timestamps remain
UTC; configured release schedules use `America/New_York` and are converted with
timezone-aware rules. User-facing renderings may additionally show
`America/Chicago`.

## Stable Reason Vocabulary

Version-one normalization and decision reasons are:

- `source_unavailable`
- `source_throttled`
- `source_partial`
- `source_malformed`
- `source_not_authorized`
- `source_origin_rejected`
- `response_too_large`
- `unknown_schema_version`
- `unknown_source`
- `unknown_event_family`
- `unknown_event_category`
- `event_identity_conflict`
- `duplicate_event`
- `event_out_of_order`
- `event_future_dated`
- `event_stale`
- `publication_time_missing`
- `scheduled_time_missing`
- `source_reference_missing`
- `symbol_identity_missing`
- `symbol_identity_unknown`
- `structured_fact_missing`
- `structured_fact_malformed`
- `structured_fact_conflicting`
- `numeric_fact_nonfinite`
- `numeric_fact_unit_mismatch`
- `numeric_fact_currency_mismatch`
- `numeric_fact_period_mismatch`
- `consensus_missing`
- `consensus_conflicting`
- `materiality_unknown`
- `direction_unclear`
- `catalyst_unconfirmed`
- `conflicting_catalyst_direction`
- `duplicate_evidence_lineage`
- `social_only_unconfirmed`
- `earnings_window_active`
- `earnings_time_missing`
- `earnings_time_conflicting`
- `macro_window_active`
- `macro_schedule_missing`
- `macro_schedule_conflicting`
- `summary_citation_missing`
- `summary_source_unknown`
- `summary_text_too_large`
- `external_text_redacted`

Reasons are sorted and deduplicated before persistence and digest creation.
Changing a reason's meaning requires a new applicable policy version.

## Cited Summary Contract

A `CitedSummary` contains a stable summary ID, summary-provider ID, generated time,
an ordered tuple of summary segments, summary policy version, and content digest.
Each segment contains bounded plain text plus nonempty sorted observation keys and
source references. The concatenated text is capped at 2,048 characters.

Every segment must reference at least one accepted observation. Unknown or
quarantined references reject the complete summary. Segment text remains opaque
display data; citation validation does not attempt to infer whether prose is true.

Summaries are persisted separately and are excluded from observation digests,
catalyst decision inputs, materiality, direction, confirmation, event-risk state,
scanner scores, candidate identity, approvals, and orders. Deleting or failing to
produce a summary cannot change an authoritative decision.

## Deterministic Identity And Digests

Stable keys use length-prefixed UTF-8 components and SHA-256 where a compact key is
required. Version-one identities include:

- Source run: source, requested capability, bounded request parameters, as-of,
  source policy version, and fixture version when applicable.
- Observation: source, provider event ID, provider schema version.
- Quarantine: observation ingestion key and sanitized payload digest.
- Decision: scope, symbol when present, as-of, sorted observation keys,
  classification policy, risk policy, and source-state digest.
- Summary: summary provider, generated time, sorted observation keys, summary
  policy, and text digest.

Canonical JSON uses sorted keys, compact separators, UTF-8, aware UTC timestamps,
string decimals, and no NaN or infinity. Input order, database IDs, wall-clock
creation times, raw text, and summaries cannot change decision keys or digests.

## Persistence Model

Milestone 5 adds one migration after `20260719_0003`.

### Source Runs

`catalyst_source_runs` records run key, source ID, capability, as-of, request
digest, source-policy version, status, source-state reasons, result counts,
correlation ID, and creation time. Run key is unique.

### Observations

`catalyst_observations` records observation key, ingestion key, authoritative
payload digest, external-text digest, source and provider identities, authority
class, event family/category, symbol ID, publication/ingestion/scheduled/valid-until
times, canonical source reference, structured facts, bounded external text, quality
reasons, schema versions, correlation ID, and creation time. Observation and
ingestion keys are unique.

Rows are immutable through repository APIs. SQLite update and delete triggers
enforce append-only behavior; PostgreSQL-compatible migration definitions and
indexes remain required.

### Quarantine

`catalyst_quarantine` stores ingestion key, sanitized payload digest, bounded
sanitized payload, source/provider identities when parseable, timestamps, sorted
reasons, schema versions, correlation ID, and creation time. It is append-only and
never stores unsanitized data.

### Decisions

`catalyst_decisions` stores decision key, scope, optional symbol ID, as-of,
materiality, direction, confirmation state, risk state, sorted reason codes,
observation lineage, policy versions, input digest, explanation payload,
correlation ID, and creation time. Decision key is unique and rows are immutable.

### Summaries

`catalyst_summaries` stores summary key, provider ID, generated time, bounded text,
observation keys, source references, policy version, content digest, correlation
ID, and creation time. It has no foreign key to signals, candidates, approvals, or
orders.

### Audit And Atomicity

New writes append bounded journal events:

- `catalyst_source_run.recorded`
- `catalyst_observation.stored`
- `catalyst_observation.quarantined`
- `catalyst_decision.recorded`
- `catalyst_summary.stored`

Repositories flush but do not commit. The application service owns one transaction
for a persistent run. Exact reruns return existing records without duplicate audit
events. Any stable-key digest conflict rolls back the complete transaction.

## Milestone 4 Integration

`ScannerCatalystAdapter` consumes only accepted catalyst decisions current at the
scanner's explicit `as_of` and policy versions. It produces the existing typed
Milestone 4 catalyst and macro evidence contracts.

- A confirmed material directional company decision may satisfy news-continuation
  catalyst gates.
- A blocked or conflicting decision blocks news continuation.
- An active or unresolved earnings window blocks every strategy for that symbol.
- An active or unresolved high-impact macro window blocks dependent scanner input
  at market scope.
- Social-only, summary-only, stale, contextual, or unclear observations cannot
  satisfy catalyst gates or add catalyst score.

The integration does not mutate prior scanner runs. Replaying a scan with new
catalyst decisions creates a new deterministic scanner input digest and run key.

## Sanitization And External Text Isolation

Sanitization runs before parsing diagnostics, persistence, hashing, logging, or
summary validation. Keys containing `authorization`, `cookie`, `token`, `secret`,
`password`, `api_key`, `account`, `approval`, or `order` are redacted recursively.

External text fields are stripped of control characters and markup, capped at 512
characters per field and 2,048 characters per event, and stored separately from
structured facts. Collections and nesting are bounded. Bytes and unknown objects
are represented by type, length, and SHA-256 digest rather than raw content.

URLs from provider payloads are never fetched. Canonical source references are
constructed by adapters from allowlisted identifiers and origins. Prompt
instructions, code, tool requests, credential requests, and approval language are
inert text and cannot trigger any action.

## Fetch, Validate, And Replay CLI

The CLI supports:

```text
python -m market_trader.catalysts.cli validate <dataset-path>
python -m market_trader.catalysts.cli replay <dataset-path> [--database-url URL]
python -m market_trader.catalysts.cli fetch sec --as-of UTC_TIMESTAMP [--database-url URL]
python -m market_trader.catalysts.cli fetch bls --as-of UTC_TIMESTAMP [--database-url URL]
```

`validate` and memory replay require no database or network. Persistent replay
runs migrations, opens one transaction, and returns the same canonical domain
result as memory replay. Fetch requires explicit source configuration and never
falls back to another source.

Commands print one compact sorted JSON result. Expected exit codes are `0` for
success, `2` for invalid configuration/dataset/input, `3` for source or persistence
failure, and `4` for security-policy rejection. Errors are sanitized and never
include API keys, user-agent contact values, database URLs, raw payloads, or text.

## Fixtures And Replay

Fixture manifests declare dataset ID, description, schema version, fixed as-of,
policy versions and hashes, ordered streams, SHA-256 stream hashes, record counts,
expected outcome counts, expected reason summary, and result digest.

Production fixture groups cover:

- Positive and negative structured company catalysts.
- Earnings beat, miss, inside-threshold, guidance change, and timing conflicts.
- Material and contextual SEC filings with amendments and XBRL corroboration.
- CPI, Employment Situation, FOMC, lower-impact, active-window, and boundary cases.
- Authorized social corroboration and social-only rejection.
- Cited summaries plus missing, unknown, oversized, and injection-shaped content.
- Source unavailable, throttled, partial, malformed, stale, future, duplicate,
  out-of-order, and recovery states.
- Exact rerun idempotence and changed-input conflict.
- XNYS holidays, early closes, daylight-saving transitions, and Chicago rendering.

Fixtures are synthetic, credential-free, and fixed in 2026. Recorded HTTP fixtures
contain only bounded representative SEC and BLS response fragments. Tests never
regenerate frozen expected values during normal execution.

## Failure Semantics

Dataset-level configuration, manifest, schema, hash, count, and policy failures
abort before writes. Event-level failures are quarantined when safe attribution
and sanitized evidence can be retained.

Required source failures never become an empty successful result. Missing,
malformed, stale, or conflicting earnings timing blocks that symbol. Missing,
malformed, stale, or conflicting high-impact macro timing blocks market-level
dependent decisions. Contextual source failure remains visible without erasing
valid independent evidence.

Retries occur only in network adapters for timeout, `429`, and retryable `5xx`
responses. At most two retries use bounded server-directed or deterministic
backoff. Domain and replay paths never sleep. Non-retryable errors fail closed and
preserve a sanitized source-run result when persistence is enabled.

## Testing Requirements

Unit tests cover:

- UTC enforcement, immutability, canonical serialization, and every enum.
- Every reason code and rejection of unversioned additions.
- Every source, category, materiality, direction, and confirmation mapping.
- Earnings surprise equality and one decimal quantum outside the threshold.
- Risk-window starts, ends, equality, and one microsecond outside.
- XNYS holidays, early closes, pre/post-market events, and daylight saving.
- Social corroboration without social authority.
- Summary citation and non-authority invariants.
- Deduplication, identity conflict, lineage conflict, and input-order invariance.
- External-text isolation and recursive credential redaction.

Adapter tests use recorded transports and cover:

- Exact SEC paths, ten-digit CIKs, required user-agent, fixed origins, rate limits,
  response bounds, redirects, timeouts, throttling, malformed JSON, and schema drift.
- Exact BLS series allowlist, unregistered requests, limits, partial series,
  provider errors, malformed values, and unavailable responses.
- No real network access in the default test suite.

Integration tests cover migration, append-only triggers, SQLite and PostgreSQL
metadata, source-run atomicity, exact reruns, conflicts and rollback, audit events,
CLI memory/persistent parity, scanner mapping, and production fixture conformance.

Property-style invariants prove:

- Raw text and summaries cannot change authoritative decisions or digests.
- Social-only input cannot confirm a catalyst.
- A failed required gate cannot be overcome by corroboration count.
- Input order cannot change decisions, explanations, or digests.
- No observation published after `as_of` affects a decision.
- Active or unresolved conservative risk windows cannot become non-blocking.

Ruff, strict mypy for new code, backend coverage above 90 percent, migration,
frontend regressions, Docker builds, and offline foundation smoke remain required.
Existing repository-wide mypy debt is reported separately unless fixed in a
dedicated scoped task.

## Operations And Documentation

The Milestone 5 runbook documents:

- Backend setup on macOS and Linux.
- Offline fixture validation, memory replay, and persistent SQLite replay.
- Explicit SEC and BLS configuration and fetch commands.
- SEC application/contact identification without logging the contact value.
- Source limits, timeouts, unavailable states, and recovery.
- Inspection of source runs, observations, quarantine, decisions, summaries, and
  audit events.
- Policy version and content-hash changes with frozen fixture review.
- UTC source timestamps, XNYS windows, and `America/Chicago` examples.
- Confirmation that Schwab, model APIs, accounts, approvals, and orders remain
  unavailable.

The non-root API container packages catalyst configuration and fixtures. Foundation
smoke validates one catalyst fixture entirely offline and does not require SEC,
BLS, Schwab, FRED, BEA, news, social, or model credentials.

## Acceptance Criteria

Milestone 5 is complete only when:

- Every accepted observation and decision is traceable to source, time, identity,
  policy, digest, and audit lineage.
- Fixed inputs reproduce identical classifications, risk windows, decisions,
  explanations, keys, and digests.
- SEC and BLS adapters enforce fixed origins, bounds, rate limits, sanitization,
  and explicit source states.
- Raw text, social-only evidence, and summaries cannot confirm catalysts, change
  direction, satisfy scanner gates, or change scores.
- Earnings and high-impact macro windows block at every approved boundary.
- Missing, malformed, stale, unavailable, and conflicting required sources fail
  closed with stable reasons.
- Exact reruns add no duplicate observations, decisions, summaries, or audit
  events; identity conflicts roll back.
- Memory and persistent replay render the same canonical result.
- Milestone 4 integration accepts only structured authoritative decisions and
  creates a new scan identity when catalyst input changes.
- CLI, migration, backend, frontend, container, and smoke checks pass.
- The runbook is complete and the roadmap marks only Milestone 5 complete.

## Deferred Work

- Commercial news and earnings providers remain a future authorized integration.
- Live authorized social providers remain deferred until retention and licensing
  requirements are selected.
- Live language-model summaries remain deferred; only the safe contract exists.
- FRED and BEA adapters remain deferred until API-key ownership and terms are
  approved.
- Option-chain filtering and spread construction: Milestone 6.
- Position sizing, exposure, risk limits, and tax warnings: Milestone 7.
- Catalyst and candidate dashboard views: Milestone 8.
- Approval, paper execution, and position lifecycle: Milestone 9.
- Production observability, security hardening, and recovery: Milestone 10.
- Schwab read-only integration: Milestone 11.
- Broker order contracts and live-mode work remain governed by Milestones 12-14.
