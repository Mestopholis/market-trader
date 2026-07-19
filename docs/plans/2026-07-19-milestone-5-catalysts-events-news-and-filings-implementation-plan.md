# Milestone 5 Catalysts, Events, News, And Filings Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Build traceable catalyst ingestion, deterministic classification and event-risk decisions, official SEC/BLS adapters, replay, persistence, and safe Milestone 4 integration without giving external text or model output trading authority.

**Architecture:** Provider adapters emit immutable project-owned events into a sanitize-first normalization pipeline. Versioned pure-domain evaluators classify structured facts, calculate conservative XNYS risk windows, and resolve evidence into deterministic decisions; replay and optional repository sinks use the same path. Network, persistence, external text, and summaries remain outside authoritative decision logic.

**Tech Stack:** Python 3.12/3.13, dataclasses, `Decimal`, `httpx`, `icalendar`, exchange-calendars through the existing project adapter, SQLAlchemy 2, Alembic, pytest, Ruff, strict mypy, SQLite/PostgreSQL-compatible models, Docker Compose.

**Specification:** `docs/plans/2026-07-19-milestone-5-catalysts-events-news-and-filings-spec.md`

## Execution Rules

- Work in a Milestone 5 feature worktree created from the merged planning branch.
- Read the approved specification before Task 1.
- Use `@superpowers:test-driven-development` for every behavior change and
  `@superpowers:systematic-debugging` for unexpected failures.
- Use `@superpowers:verification-before-completion` before commits and completion
  claims.
- Do not use sub-agents; the user requested direct execution in the primary agent.
- Domain modules must not import SQLAlchemy, HTTP clients, environment settings,
  wall-clock helpers, Schwab, broker, approval, order, or model-provider packages.
- Sanitize before parsing diagnostics, persistence, hashing, or logging.
- Use aware UTC timestamps, `Decimal` for numeric policy values, XNYS sessions for
  risk windows, and `America/Chicago` only for user-facing examples.
- Keep all default tests and fixture commands offline. Live SEC/BLS tests require
  an explicit opt-in marker and are not acceptance dependencies.
- Run backend commands from `apps/api` with `.venv/bin/` executables.
- Preserve the 44 known strict-mypy errors in four older test files as separately
  reported debt; every new and modified Milestone 5 file must pass strict mypy.
- Do not mark Milestone 5 complete until Task 16 passes its applicable gates.

---

### Task 1: Catalyst Domain Contracts And Canonical Serialization

**Interfaces**

- Consumes: aware UTC timestamps, immutable source identity, structured facts, and
  bounded external-text fields.
- Produces: immutable provider events, observations, decisions, source outcomes,
  summaries, and stable canonical JSON/digests.

**Files:**

- Create: `apps/api/src/market_trader/catalysts/__init__.py`
- Create: `apps/api/src/market_trader/catalysts/models.py`
- Create: `apps/api/src/market_trader/catalysts/serialization.py`
- Create: `apps/api/tests/catalysts/__init__.py`
- Create: `apps/api/tests/catalysts/test_models.py`
- Create: `apps/api/tests/catalysts/test_serialization.py`

- [x] **Step 1: Write failing contract tests.** Prove naive timestamps are
  rejected; enums contain only approved values; mappings are immutable; reasons,
  lineages, and references are sorted/deduplicated; and reordered inputs produce
  identical JSON and SHA-256 digests. Start with these public contracts:

  ```python
  class EventFamily(StrEnum):
      COMPANY_NEWS = "company_news"
      EARNINGS = "earnings"
      SEC_FILING = "sec_filing"
      ECONOMIC_RELEASE = "economic_release"
      SOCIAL = "social"

  class Materiality(StrEnum):
      MATERIAL = "material"
      CONTEXTUAL = "contextual"
      UNKNOWN = "unknown"

  class CatalystDirection(StrEnum):
      POSITIVE = "positive"
      NEGATIVE = "negative"
      NEUTRAL = "neutral"
      UNCLEAR = "unclear"

  class ConfirmationState(StrEnum):
      CONFIRMED = "confirmed"
      UNCONFIRMED = "unconfirmed"
      BLOCKED = "blocked"

  class SourceState(StrEnum):
      AVAILABLE = "available"
      DEGRADED = "degraded"
      STALE = "stale"
      UNAVAILABLE = "unavailable"
      MALFORMED = "malformed"
  ```

- [x] **Step 2: Run RED:** `.venv/bin/pytest tests/catalysts/test_models.py tests/catalysts/test_serialization.py -q`. Expected: collection fails because `market_trader.catalysts` does not exist.
- [x] **Step 3: Implement immutable types.** Add `AuthorityClass`, `RiskState`,
  `SourceFailureKind`, `CatalystProviderEvent`, `SourceFailure`,
  `CatalystObservation`, `QuarantinedObservation`, `EventRiskWindow`,
  `CatalystDecision`, `CitedSummary`, `SourceRunResult`, and policy-version records.
  Validate aware UTC with `ensure_utc`; convert mappings to `MappingProxyType` and
  collections to sorted tuples.
- [x] **Step 4: Implement canonical serialization.** Reuse Milestone 3 canonical
  JSON conventions, encode `Decimal` as fixed strings, exclude wall-clock/database
  identity, and provide `canonical_record(value)` and `stable_digest(value)`.
- [x] **Step 5: Run GREEN:** `.venv/bin/ruff check src/market_trader/catalysts tests/catalysts && .venv/bin/mypy src/market_trader/catalysts tests/catalysts && .venv/bin/pytest tests/catalysts/test_models.py tests/catalysts/test_serialization.py -q`.
- [x] **Step 6: Commit:** `git add apps/api/src/market_trader/catalysts apps/api/tests/catalysts && git commit -m "feat: add catalyst domain contracts"`.

---

### Task 2: Versioned Catalyst Configuration

**Interfaces**

- Consumes: four exact local JSON policies.
- Produces: a verified `CatalystConfiguration` with source, classification, risk,
  and summary policies plus canonical content hashes.

**Files:**

- Create: `apps/api/config/catalysts/catalyst-source-policy-v1.json`
- Create: `apps/api/config/catalysts/catalyst-classification-policy-v1.json`
- Create: `apps/api/config/catalysts/event-risk-policy-v1.json`
- Create: `apps/api/config/catalysts/catalyst-summary-policy-v1.json`
- Create: `apps/api/src/market_trader/catalysts/configuration.py`
- Create: `apps/api/tests/catalysts/test_configuration.py`

- [x] **Step 1: Write failing tests.** Assert exact versions, fixed SEC/BLS origins,
  SEC five-per-second limit, BLS five-per-minute/twenty-per-day limits, response
  bounds, exact CIK map for 15 operating companies, explicit unsupported status for
  15 fund symbols, exact BLS series, category
  allowlist, `2.000000` earnings threshold, 30-minute social freshness, two-session
  earnings lead, full-session post-event rule, and 60/30-minute macro window.
  Reject unknown keys, duplicate sources/categories/CIKs, JSON numeric decimals,
  unknown versions, changed hashes, and any source policy containing broker/model
  origins or arbitrary redirects.
- [x] **Step 2: Run RED:** `.venv/bin/pytest tests/catalysts/test_configuration.py -q`.
- [x] **Step 3: Add exact JSON documents.** Encode every decimal as a string and
  include canonical `content_hash`. Source IDs are `sec-edgar-public-v1`,
  `bls-public-v1`, `recorded-company-news-v1`, `recorded-earnings-v1`,
  `recorded-social-v1`, and `recorded-summary-v1`.
- [x] **Step 4: Implement strict loading:**

  ```python
  @dataclass(frozen=True)
  class CatalystConfiguration:
      sources: SourcePolicy
      classification: ClassificationPolicy
      risk: EventRiskPolicy
      summary: SummaryPolicy
      content_hashes: Mapping[str, str]

  def load_catalyst_configuration(path: Path | str) -> CatalystConfiguration: ...
  ```

  Hash canonical payloads with `content_hash` omitted and reject undeclared fields.
- [x] **Step 5: Run GREEN:** `.venv/bin/ruff check src/market_trader/catalysts/configuration.py tests/catalysts/test_configuration.py && .venv/bin/mypy src/market_trader/catalysts/configuration.py tests/catalysts/test_configuration.py && .venv/bin/pytest tests/catalysts/test_configuration.py -q`.
- [x] **Step 6: Commit:** `git add apps/api/config/catalysts apps/api/src/market_trader/catalysts/configuration.py apps/api/tests/catalysts/test_configuration.py && git commit -m "feat: add versioned catalyst configuration"`.

---

### Task 3: Provider Protocols And Sanitize-First Boundaries

**Interfaces**

- Consumes: bounded provider requests and unknown provider payloads.
- Produces: provider events/failures and sanitized immutable payloads safe for
  diagnostics, hashing, and quarantine.

**Files:**

- Create: `apps/api/src/market_trader/catalysts/providers.py`
- Create: `apps/api/src/market_trader/catalysts/sanitization.py`
- Create: `apps/api/tests/catalysts/test_providers.py`
- Create: `apps/api/tests/catalysts/test_sanitization.py`

- [x] **Step 1: Write failing tests.** Define protocol fakes for company news,
  earnings, SEC, macro, social, and summary sources. Prove unsupported, unavailable,
  throttled, partial, and malformed outcomes cannot become empty success. Inject
  nested authorization/cookie/token/secret/password/api-key/account/approval/order
  fields, bytes, objects, HTML, control characters, huge strings, deep mappings,
  and large collections; assert redaction and bounds occur before digesting.
- [x] **Step 2: Run RED:** `.venv/bin/pytest tests/catalysts/test_providers.py tests/catalysts/test_sanitization.py -q`.
- [x] **Step 3: Implement protocols.** Each protocol accepts an explicit immutable
  request containing `as_of` and allowlisted identity, and returns
  `ProviderBatch(events=...)` or `SourceFailure`; no exception represents a normal
  provider state.
- [x] **Step 4: Implement `sanitize_provider_payload`.** Reuse the Milestone 3
  recursive sanitizer where semantics match, add catalyst-specific text/control
  bounds, return a typed recursive value, and never retain unknown object reprs.
- [x] **Step 5: Run GREEN:** `.venv/bin/ruff check src/market_trader/catalysts/providers.py src/market_trader/catalysts/sanitization.py tests/catalysts/test_providers.py tests/catalysts/test_sanitization.py && .venv/bin/mypy src/market_trader/catalysts/providers.py src/market_trader/catalysts/sanitization.py tests/catalysts/test_providers.py tests/catalysts/test_sanitization.py && .venv/bin/pytest tests/catalysts/test_providers.py tests/catalysts/test_sanitization.py -q`.
- [x] **Step 6: Commit:** `git add apps/api/src/market_trader/catalysts/providers.py apps/api/src/market_trader/catalysts/sanitization.py apps/api/tests/catalysts && git commit -m "feat: isolate catalyst provider inputs"`.

---

### Task 4: Catalyst Normalization And Quarantine

**Interfaces**

- Consumes: one sanitized `CatalystProviderEvent`, source policy, and explicit
  `as_of`.
- Produces: accepted `CatalystObservation` or `QuarantinedObservation` with stable
  reasons and no raw secret-bearing payload.

**Files:**

- Create: `apps/api/src/market_trader/catalysts/normalizers.py`
- Create: `apps/api/tests/catalysts/test_normalizers.py`

- [x] **Step 1: Write failing tests.** Cover all five event families, aware UTC,
  stable ingestion keys/digests, fixed source reference construction, external-text
  separation, exact duplicate identity, unknown source/schema/category, missing
  attribution, invalid symbol, malformed/nonfinite decimal, five-minute future
  tolerance, stale equality, one microsecond stale/future, out-of-order events, and
  deterministic quarantine reasons.
- [x] **Step 2: Run RED:** `.venv/bin/pytest tests/catalysts/test_normalizers.py -q`.
- [x] **Step 3: Implement normalization:**

  ```python
  @dataclass(frozen=True)
  class NormalizationResult:
      observation: CatalystObservation | None
      quarantine: QuarantinedObservation | None

  def normalize_event(
      event: CatalystProviderEvent,
      *,
      as_of: datetime,
      configuration: CatalystConfiguration,
      watermark: ObservationWatermark | None = None,
  ) -> NormalizationResult: ...
  ```

  Validate structured facts by family, canonicalize decimal strings, construct
  references only from source policy, and retain display text outside facts.
- [x] **Step 4: Prove text non-authority.** Parametrize two events with identical
  structured fields and different prompt-shaped text; accepted authoritative
  records and classification-facing digests must match while text digests differ.
  Reusing a provider identity with only changed display text returns the existing
  authoritative observation and does not emit `event_identity_conflict`.
- [x] **Step 5: Run GREEN:** `.venv/bin/ruff check src/market_trader/catalysts/normalizers.py tests/catalysts/test_normalizers.py && .venv/bin/mypy src/market_trader/catalysts/normalizers.py tests/catalysts/test_normalizers.py && .venv/bin/pytest tests/catalysts/test_normalizers.py -q`.
- [x] **Step 6: Commit:** `git add apps/api/src/market_trader/catalysts/normalizers.py apps/api/tests/catalysts/test_normalizers.py && git commit -m "feat: normalize catalyst observations"`.

---

### Task 5: Official SEC EDGAR Adapter

**Interfaces**

- Consumes: configured CIKs, explicit `as_of`, fixed SEC origins, and injected HTTP
  transport/limiter.
- Produces: filing/company-fact provider events or typed SEC source failure.

**Files:**

- Modify: `apps/api/pyproject.toml`
- Create: `apps/api/src/market_trader/catalysts/adapters/__init__.py`
- Create: `apps/api/src/market_trader/catalysts/adapters/sec.py`
- Create: `apps/api/tests/catalysts/adapters/__init__.py`
- Create: `apps/api/tests/catalysts/adapters/test_sec.py`
- Create: `apps/api/tests/catalysts/fixtures/http/sec-submissions.json`
- Create: `apps/api/tests/catalysts/fixtures/http/sec-companyfacts.json`

- [x] **Step 1: Write failing recorded-transport tests.** Use `httpx.MockTransport`
  to assert exact `data.sec.gov` hosts/paths, ten-digit CIK, GET only, configured
  identified `User-Agent`, no credentials, fixed headers, no cross-origin redirect,
  10 MiB bound, connect/total timeouts, and at most five requests per second. Cover
  `8-K`, `10-Q`, `10-K`, `6-K`, `20-F`, `40-F`, amendments, partial arrays,
  malformed column lengths, `403`, `429`, retryable `5xx`, timeout, and schema drift.
- [x] **Step 2: Run RED:** `.venv/bin/pytest tests/catalysts/adapters/test_sec.py -q`.
- [x] **Step 3: Move `httpx>=0.28,<1` from dev-only to production dependencies.**
  Keep one declaration and regenerate no lock file because this project has none.
- [x] **Step 4: Implement `SecEdgarAdapter`.** Inject `httpx.Client`, limiter, and
  sleeper; production defaults are created only by the CLI. Parse columnar arrays
  by validated equal index, sort events by `(published_at, event_id)`, construct
  source references from accession/CIK, and never fetch filing links.
- [x] **Step 5: Implement bounded retry.** Retry timeout, `429`, and retryable `5xx`
  at most twice using bounded `Retry-After` or deterministic delays. Tests inject a
  no-op sleeper and assert request count and terminal failure.
- [x] **Step 6: Run GREEN:** `.venv/bin/ruff check src/market_trader/catalysts/adapters/sec.py tests/catalysts/adapters/test_sec.py && .venv/bin/mypy src/market_trader/catalysts/adapters/sec.py tests/catalysts/adapters/test_sec.py && .venv/bin/pytest tests/catalysts/adapters/test_sec.py -q`.
- [x] **Step 7: Commit:** `git add apps/api/pyproject.toml apps/api/src/market_trader/catalysts/adapters apps/api/tests/catalysts/adapters apps/api/tests/catalysts/fixtures/http && git commit -m "feat: add official SEC catalyst adapter"`.

---

### Task 6: Official BLS Series And Calendar Adapter

**Interfaces**

- Consumes: exact unregistered BLS endpoint/calendar, three configured series,
  explicit `as_of`, and injected transport/limiter.
- Produces: scheduled CPI/employment and published-value provider events or typed
  BLS source failure.

**Files:**

- Modify: `apps/api/pyproject.toml`
- Create: `apps/api/src/market_trader/catalysts/adapters/bls.py`
- Create: `apps/api/tests/catalysts/adapters/test_bls.py`
- Create: `apps/api/tests/catalysts/fixtures/http/bls-series.json`
- Create: `apps/api/tests/catalysts/fixtures/http/bls-calendar.ics`

- [x] **Step 1: Write failing recorded-transport tests.** Assert only
  `api.bls.gov/publicAPI/v1/timeseries/data/` and
  `www.bls.gov/schedule/news_release/bls.ics` are requested; no registration key;
  exact three-series allowlist; one request at a time; five/minute and twenty/day
  limits; 2 MiB bound; fixed methods; no cross-origin redirect. Cover CPI,
  Employment Situation, Eastern-to-UTC conversion, DST, calendar title allowlist,
  unknown events, missing UID/time, duplicate schedule events, partial series,
  BLS status errors, `429`, timeout, malformed JSON/ICS, and broken properties.
- [x] **Step 2: Run RED:** `.venv/bin/pytest tests/catalysts/adapters/test_bls.py -q`.
- [x] **Step 3: Add `icalendar>=7.2,<8` to production dependencies.** Use
  `Calendar.from_ical`; inspect event parse errors and reject broken required
  properties instead of manually parsing RFC 5545 text.
- [x] **Step 4: Implement `BlsPublicAdapter`.** Convert calendar `DTSTART` through
  `America/New_York`, map only exact CPI/Employment titles, derive stable event IDs
  from source UID/category/time, and emit published numeric observations separately
  from scheduled events.
- [x] **Step 5: Implement limits/retry.** Reuse the injected HTTP/retry primitives
  from Task 5 without coupling source-specific parsing. Return explicit partial or
  unavailable state when any required series/schedule capability fails.
- [x] **Step 6: Run GREEN:** `.venv/bin/ruff check src/market_trader/catalysts/adapters/bls.py tests/catalysts/adapters/test_bls.py && .venv/bin/mypy src/market_trader/catalysts/adapters/bls.py tests/catalysts/adapters/test_bls.py && .venv/bin/pytest tests/catalysts/adapters/test_bls.py -q`.
- [x] **Step 7: Commit:** `git add apps/api/pyproject.toml apps/api/src/market_trader/catalysts/adapters/bls.py apps/api/tests/catalysts/adapters/test_bls.py apps/api/tests/catalysts/fixtures/http && git commit -m "feat: add official BLS catalyst adapter"`.

---

### Task 7: Deterministic Catalyst Classification

**Interfaces**

- Consumes: accepted structured observations and classification policy.
- Produces: one classification per observation with materiality, direction, and
  stable reasons; external text is unavailable to this module.

**Files:**

- Create: `apps/api/src/market_trader/catalysts/classification.py`
- Create: `apps/api/tests/catalysts/test_classification.py`

- [x] **Step 1: Write failing policy tests.** Cover earnings surprise at
  `-2.000001`, `-2.000000`, `-1.999999`, `1.999999`, `2.000000`, `2.000001`;
  zero consensus; period/unit/currency conflicts; raised/lowered guidance ranges;
  all ten company categories; SEC form/item materiality with unclear direction;
  macro with/without consensus; unknown categories; social contextual behavior;
  and raw-text variance invariance.
- [x] **Step 2: Run RED:** `.venv/bin/pytest tests/catalysts/test_classification.py -q`.
- [x] **Step 3: Implement pure classifiers:**

  ```python
  def classify_observation(
      observation: CatalystObservation,
      policy: ClassificationPolicy,
  ) -> ObservationClassification: ...
  ```

  Dispatch by event family, use `Decimal`, reject noncomparable facts, and never
  accept external text or summaries in the signature.
- [x] **Step 4: Add vocabulary/invariant tests.** Every configured category maps
  exactly once; adding an unversioned category fails; direction never comes from
  SEC form type, BLS value alone, social, or text.
- [x] **Step 5: Run GREEN:** `.venv/bin/ruff check src/market_trader/catalysts/classification.py tests/catalysts/test_classification.py && .venv/bin/mypy src/market_trader/catalysts/classification.py tests/catalysts/test_classification.py && .venv/bin/pytest tests/catalysts/test_classification.py -q`.
- [x] **Step 6: Commit:** `git add apps/api/src/market_trader/catalysts/classification.py apps/api/tests/catalysts/test_classification.py && git commit -m "feat: classify structured catalyst facts"`.

---

### Task 8: Conservative Event-Risk Windows

**Interfaces**

- Consumes: scheduled earnings/macro observations, explicit `as_of`, XNYS calendar,
  and risk policy.
- Produces: deterministic inclusive `EventRiskWindow` and blocked/clear state.

**Files:**

- Create: `apps/api/src/market_trader/catalysts/risk.py`
- Create: `apps/api/tests/catalysts/test_risk.py`

- [x] **Step 1: Write failing earnings tests.** Cover before-market, after-market,
  unknown-time, weekends, holidays, early closes, full post-event session,
  daylight-saving changes, two-session start equality/one microsecond outside,
  close equality/one microsecond outside, missing/stale/changed/conflicting timing,
  and naive `as_of` rejection.
- [x] **Step 2: Write failing macro tests.** Cover CPI, Employment Situation, FOMC,
  lower-impact events, 60-minute start, 30-minute end, equality/one microsecond
  outside, schedule missing/conflict, Eastern-to-UTC conversion, and Chicago
  display conversion without changing identity.
- [x] **Step 3: Run RED:** `.venv/bin/pytest tests/catalysts/test_risk.py -q`.
- [x] **Step 4: Implement `EventRiskEvaluator`.** Depend on the existing
  project-owned calendar protocol rather than exchange-calendars directly. Return
  `ACTIVE`, `CLEAR`, or `BLOCKED`, inclusive bounds, reasons, source lineages, and
  exact policy version.
- [x] **Step 5: Run GREEN:** `.venv/bin/ruff check src/market_trader/catalysts/risk.py tests/catalysts/test_risk.py && .venv/bin/mypy src/market_trader/catalysts/risk.py tests/catalysts/test_risk.py && .venv/bin/pytest tests/catalysts/test_risk.py -q`.
- [x] **Step 6: Commit:** `git add apps/api/src/market_trader/catalysts/risk.py apps/api/tests/catalysts/test_risk.py && git commit -m "feat: evaluate catalyst risk windows"`.

---

### Task 9: Catalyst Confirmation And Conflict Decisions

**Interfaces**

- Consumes: observation classifications, risk windows, source states, and explicit
  `as_of`.
- Produces: deterministic symbol-level and market-level `CatalystDecision` values.

**Files:**

- Create: `apps/api/src/market_trader/catalysts/decisions.py`
- Create: `apps/api/tests/catalysts/test_decisions.py`

- [x] **Step 1: Write failing tests.** Cover confirmed material directional facts,
  unclear/unconfirmed facts, duplicate lineage, independent compatible
  corroboration, independent opposite conflict, stale evidence, source outage with
  current evidence, required-source outage, social-only, social corroboration,
  active/blocked risk, input-order invariance, and text/summary absence.
- [x] **Step 2: Run RED:** `.venv/bin/pytest tests/catalysts/test_decisions.py -q`.
- [x] **Step 3: Implement pure decision service:**

  ```python
  def decide_catalysts(
      observations: tuple[ClassifiedObservation, ...],
      risk_windows: tuple[EventRiskWindow, ...],
      source_states: tuple[SourceStatus, ...],
      *,
      as_of: datetime,
      policy_versions: CatalystPolicyVersions,
  ) -> tuple[CatalystDecision, ...]: ...
  ```

  Group by market/symbol scope, deduplicate lineage before corroboration, preserve
  conflicts, sort explanations, and derive stable decision keys/digests.
- [x] **Step 4: Add property-style invariants.** Permuting inputs cannot change
  decisions; adding social/summary/text cannot create confirmation; active or
  unresolved risk never becomes clear; no future observation participates.
- [x] **Step 5: Run GREEN:** `.venv/bin/ruff check src/market_trader/catalysts/decisions.py tests/catalysts/test_decisions.py && .venv/bin/mypy src/market_trader/catalysts/decisions.py tests/catalysts/test_decisions.py && .venv/bin/pytest tests/catalysts/test_decisions.py -q`.
- [x] **Step 6: Commit:** `git add apps/api/src/market_trader/catalysts/decisions.py apps/api/tests/catalysts/test_decisions.py && git commit -m "feat: resolve catalyst decisions"`.

---

### Task 10: Cited Non-Authoritative Summaries

**Interfaces**

- Consumes: a fixture-backed summary provider response and accepted observation
  index.
- Produces: validated `CitedSummary` stored outside authoritative decisions.

**Files:**

- Create: `apps/api/src/market_trader/catalysts/summaries.py`
- Create: `apps/api/tests/catalysts/test_summaries.py`

- [x] **Step 1: Write failing tests.** Require summary provider ID, aware generated
  time, at least one ordered summary segment, nonempty sorted observation keys and
  source references on every segment, known accepted citations, a 2,048-character
  aggregate bound, sanitized plain text, stable content digest, and rejection of
  unknown/quarantined citations. Include prompt/tool/credential requests as inert
  text fixtures.
- [x] **Step 2: Run RED:** `.venv/bin/pytest tests/catalysts/test_summaries.py -q`.
- [x] **Step 3: Implement `validate_cited_summary`.** Return accepted summary or
  typed rejection reasons. Do not import or call any model API.
- [x] **Step 4: Prove non-authority.** Run decision and scanner-input digest tests
  before/after adding, changing, or removing summaries; every authoritative output
  must remain identical.
- [x] **Step 5: Run GREEN:** `.venv/bin/ruff check src/market_trader/catalysts/summaries.py tests/catalysts/test_summaries.py && .venv/bin/mypy src/market_trader/catalysts/summaries.py tests/catalysts/test_summaries.py && .venv/bin/pytest tests/catalysts/test_summaries.py -q`.
- [x] **Step 6: Commit:** `git add apps/api/src/market_trader/catalysts/summaries.py apps/api/tests/catalysts/test_summaries.py && git commit -m "feat: validate cited catalyst summaries"`.

---

### Task 11: Milestone 4 Scanner Integration

**Interfaces**

- Consumes: current authoritative catalyst decisions and scanner `as_of`.
- Produces: existing Milestone 4 `CatalystEvidence`/macro inputs only; no raw text,
  summary, provider, or persistence types cross the boundary.

**Files:**

- Create: `apps/api/src/market_trader/catalysts/scanner.py`
- Create: `apps/api/tests/catalysts/test_scanner_adapter.py`
- Modify: `apps/api/src/market_trader/scanner/evidence.py`
- Modify: `apps/api/tests/scanner/test_evidence.py`
- Modify: `apps/api/tests/scanner/strategies/test_news.py`

- [x] **Step 1: Write failing mapping tests.** Confirm material directional decision
  maps to current catalyst evidence; conflict maps to blocked; social-only,
  summary-only, contextual, stale, neutral, and unclear cannot satisfy news gates;
  active/unresolved earnings blocks every symbol strategy; active/unresolved macro
  blocks market input; source lineages and policy versions survive mapping.
- [x] **Step 2: Run RED:** `.venv/bin/pytest tests/catalysts/test_scanner_adapter.py tests/scanner/test_evidence.py tests/scanner/strategies/test_news.py -q`.
- [x] **Step 3: Implement `ScannerCatalystAdapter`.** Keep it pure and construct the
  existing scanner evidence records. Add only narrow scanner evidence fields needed
  to distinguish symbol earnings risk and market macro risk; preserve old fixture
  compatibility with explicit defaults.
- [x] **Step 4: Prove scan identity semantics.** Exact decisions preserve run key;
  changed catalyst decision/risk input changes scanner input digest/run key; prior
  persisted runs are not mutated.
- [x] **Step 5: Run GREEN:** `.venv/bin/ruff check src/market_trader/catalysts/scanner.py src/market_trader/scanner/evidence.py tests/catalysts/test_scanner_adapter.py tests/scanner && .venv/bin/mypy src/market_trader/catalysts/scanner.py src/market_trader/scanner/evidence.py tests/catalysts/test_scanner_adapter.py tests/scanner && .venv/bin/pytest tests/catalysts/test_scanner_adapter.py tests/scanner -q`.
- [x] **Step 6: Commit:** `git add apps/api/src/market_trader/catalysts/scanner.py apps/api/src/market_trader/scanner/evidence.py apps/api/tests/catalysts/test_scanner_adapter.py apps/api/tests/scanner && git commit -m "feat: integrate catalyst decisions with scanner"`.

---

### Task 12: Catalyst Fixture Loading And Deterministic Replay

**Interfaces**

- Consumes: complete fixture manifest and ordered NDJSON/JSON/ICS streams.
- Produces: validated immutable dataset and deterministic in-memory replay result.

**Files:**

- Create: `apps/api/src/market_trader/catalysts/fixtures.py`
- Create: `apps/api/src/market_trader/catalysts/replay.py`
- Create: `apps/api/tests/catalysts/test_fixture_loader.py`
- Create: `apps/api/tests/catalysts/test_replay.py`
- Create: `apps/api/tests/catalysts/fixtures/minimal/manifest.json`
- Create: `apps/api/tests/catalysts/fixtures/minimal/events.ndjson`
- Create: `apps/api/tests/catalysts/fixtures/minimal/bls-calendar.ics`

- [x] **Step 1: Write failing loader tests.** Assert exact fixture schema/version,
  policy versions/hashes, fixed aware as-of, ordered streams, relative filename
  confinement, complete-file size bounds, SHA-256/count verification before event
  yield, sanitized line diagnostics, unknown keys/kinds, invalid JSON/ICS, and no
  credentials/account identifiers.
- [x] **Step 2: Run RED:** `.venv/bin/pytest tests/catalysts/test_fixture_loader.py -q`.
- [x] **Step 3: Implement loader.** Parse manifests with standard JSON and strict
  dataclasses; parse ICS with `icalendar`; preserve manifest/line order; return
  immutable `CatalystFixtureDataset` only after every stream validates.
- [x] **Step 4: Write failing replay tests.** Use an injected virtual clock; process
  ingestion order; handle exact duplicates, identity conflicts, out-of-order events,
  source failures/recovery, summaries, classification, risk, decisions, and
  deterministic expected result/reason digests. Replay twice in fresh memory sinks.
- [x] **Step 5: Implement replay.** Reuse production sanitizer, normalizer,
  classifier, risk evaluator, decision service, and summary validator. No replay
  branch may bypass production behavior.
- [x] **Step 6: Run GREEN:** `.venv/bin/ruff check src/market_trader/catalysts/fixtures.py src/market_trader/catalysts/replay.py tests/catalysts/test_fixture_loader.py tests/catalysts/test_replay.py && .venv/bin/mypy src/market_trader/catalysts/fixtures.py src/market_trader/catalysts/replay.py tests/catalysts/test_fixture_loader.py tests/catalysts/test_replay.py && .venv/bin/pytest tests/catalysts/test_fixture_loader.py tests/catalysts/test_replay.py -q`.
- [x] **Step 7: Commit:** `git add apps/api/src/market_trader/catalysts/fixtures.py apps/api/src/market_trader/catalysts/replay.py apps/api/tests/catalysts && git commit -m "feat: replay deterministic catalyst fixtures"`.

---

### Task 13: Catalyst Persistence Schema

**Interfaces**

- Consumes: Milestone 1 audit/symbol tables and Milestone 5 storage contract.
- Produces: source-run, observation, quarantine, decision, and summary schema with
  append-only protections and stable uniqueness.

**Files:**

- Create: `apps/api/migrations/versions/20260719_0004_catalyst_events.py`
- Modify: `apps/api/src/market_trader/db/models.py`
- Create: `apps/api/tests/catalysts/test_schema.py`
- Modify: `apps/api/tests/test_migrations.py`

- [x] **Step 1: Write failing schema tests.** Assert all five tables, columns,
  lengths, foreign keys, unique stable keys, source/symbol/as-of indexes, JSONB/GIN
  compilation for reasons/lineages, and SQLite update/delete rejection for
  observations, quarantine, decisions, and summaries.
- [x] **Step 2: Run RED:** `.venv/bin/pytest tests/catalysts/test_schema.py tests/test_migrations.py -q`.
- [x] **Step 3: Add ORM models.** Create `CatalystSourceRunORM`,
  `CatalystObservationORM`, `CatalystQuarantineORM`, `CatalystDecisionORM`, and
  `CatalystSummaryORM`. Use `String(512)` for full deterministic keys and
  `String(64)` for SHA-256 digests; make all UTC fields timezone-aware.
- [x] **Step 4: Add migration.** Set `down_revision = "20260719_0003"`; create
  tables/indexes/triggers in dependency order. Downgrade drops triggers, indexes,
  and tables in reverse order without touching Milestones 1-4.
- [x] **Step 5: Run GREEN:** `.venv/bin/ruff check migrations/versions/20260719_0004_catalyst_events.py src/market_trader/db/models.py tests/catalysts/test_schema.py tests/test_migrations.py && .venv/bin/mypy src/market_trader/db/models.py tests/catalysts/test_schema.py tests/test_migrations.py && .venv/bin/pytest tests/catalysts/test_schema.py tests/test_migrations.py -q`.
- [x] **Step 6: Commit:** `git add apps/api/migrations/versions/20260719_0004_catalyst_events.py apps/api/src/market_trader/db/models.py apps/api/tests/catalysts/test_schema.py apps/api/tests/test_migrations.py && git commit -m "feat: add catalyst persistence schema"`.

---

### Task 14: Atomic Catalyst Repositories And Sink

**Interfaces**

- Consumes: complete replay/fetch result and caller-owned SQLAlchemy session.
- Produces: atomic, append-only, idempotent persistence plus bounded journal events.

**Files:**

- Create: `apps/api/src/market_trader/repositories/catalysts.py`
- Modify: `apps/api/src/market_trader/repositories/__init__.py`
- Create: `apps/api/src/market_trader/catalysts/sinks.py`
- Create: `apps/api/tests/catalysts/test_repository_sink.py`

- [x] **Step 1: Write failing repository tests.** Cover each create/get-by-key,
  domain mapping, sorted JSON, symbol/source integrity, source run result counts,
  exact authoritative duplicate return without writes/audit, display-text-only
  duplicate return without conflict, changed authoritative digest conflict, missing
  observation citation, and one bounded audit event per new row.
- [x] **Step 2: Write failing transaction tests.** Persist a complete run; inject
  failure after observations, decisions, and summaries; assert every domain/audit
  row rolls back. Repeat exact result and assert row/audit counts do not change.
- [x] **Step 3: Run RED:** `.venv/bin/pytest tests/catalysts/test_repository_sink.py -q`.
- [x] **Step 4: Implement `CatalystRepository`.** Reuse project ID/time/audit
  helpers, flush but never commit, compare stable key plus payload/input digest for
  idempotency, and raise typed identity conflicts.
- [x] **Step 5: Implement `RepositoryCatalystSink.persist`.** Resolve symbols first;
  store source run, accepted/quarantined observations, decisions, summaries, and
  audit events under the caller's transaction. Never persist unsanitized payloads.
- [x] **Step 6: Run GREEN:** `.venv/bin/ruff check src/market_trader/repositories/catalysts.py src/market_trader/catalysts/sinks.py tests/catalysts/test_repository_sink.py && .venv/bin/mypy src/market_trader/repositories/catalysts.py src/market_trader/catalysts/sinks.py tests/catalysts/test_repository_sink.py && .venv/bin/pytest tests/catalysts/test_repository_sink.py -q`.
- [x] **Step 7: Commit:** `git add apps/api/src/market_trader/repositories apps/api/src/market_trader/catalysts/sinks.py apps/api/tests/catalysts/test_repository_sink.py && git commit -m "feat: persist atomic catalyst outcomes"`.

---

### Task 15: Catalyst CLI And Production Conformance Fixtures

**Interfaces**

- Consumes: catalyst config, fixture datasets or explicit SEC/BLS source, optional
  database URL, explicit as-of.
- Produces: canonical validation/replay/fetch summary and optional atomic
  persistence.

**Files:**

- Create: `apps/api/src/market_trader/catalysts/cli.py`
- Create: `apps/api/tests/catalysts/test_cli.py`
- Create: `apps/api/tests/catalysts/test_fixture_conformance.py`
- Create: `apps/api/scripts/generate_catalyst_fixtures.py`
- Create: `apps/api/fixtures/catalysts/company-and-earnings/*`
- Create: `apps/api/fixtures/catalysts/sec-and-amendments/*`
- Create: `apps/api/fixtures/catalysts/macro-risk-windows/*`
- Create: `apps/api/fixtures/catalysts/social-summary-and-failures/*`

- [x] **Step 1: Write failing CLI tests.** Assert exact `validate`, `replay`, and
  `fetch sec|bls` syntax; database-free defaults; explicit network source; required
  as-of; migrations before persistent writes; one transaction; exact rerun;
  memory/persistent canonical equality; exit `0/2/3/4`; sanitized exceptions; no
  database URL, SEC contact, provider payload, or external text leakage.
- [x] **Step 2: Write failing conformance inventory tests.** Parametrize every
  production scenario from the specification: company categories, earnings
  thresholds/timing, SEC forms/amendments, CPI/employment/FOMC, every risk boundary,
  source faults/recovery, social-only, summaries/injection text, duplicates,
  conflicts, DST, early close, Chicago render, exact rerun, and changed input.
- [x] **Step 3: Run RED:** `.venv/bin/pytest tests/catalysts/test_cli.py tests/catalysts/test_fixture_conformance.py -q`.
- [x] **Step 4: Implement `main(argv: Sequence[str] | None = None) -> int`.** Resolve
  configuration from `Path("config/catalysts")`; keep network clients out of
  validate/replay; run Alembic and one session for persistence; fetch fully before
  opening the write transaction; render compact sorted JSON.
- [x] **Step 5: Build deterministic generator and four production groups.** Freeze
  stream hashes, record counts, expected source states, classifications, risk
  states, decisions, reasons, and result digest. Generator output must be byte-for-
  byte stable and contain no credentials, account data, real article/filing text,
  or customer data.
- [x] **Step 6: Run GREEN:** `.venv/bin/python scripts/generate_catalyst_fixtures.py && .venv/bin/ruff check src/market_trader/catalysts tests/catalysts scripts/generate_catalyst_fixtures.py && MYPYPATH=src .venv/bin/mypy src/market_trader/catalysts tests/catalysts scripts/generate_catalyst_fixtures.py && .venv/bin/pytest tests/catalysts -q`.
- [x] **Step 7: Commit:** `git add apps/api/src/market_trader/catalysts/cli.py apps/api/tests/catalysts apps/api/scripts/generate_catalyst_fixtures.py apps/api/fixtures/catalysts && git commit -m "feat: add catalyst CLI and conformance fixtures"`.

---

### Task 16: Operations, Packaging, And Milestone Verification

**Interfaces**

- Consumes: completed catalyst domain, adapters, config, fixtures, migration, CLI,
  persistence, and scanner integration.
- Produces: operator runbook, offline container smoke coverage, complete verification,
  and roadmap status.

**Files:**

- Create: `docs/milestone-5-catalysts-events-news-and-filings.md`
- Modify: `apps/api/tests/test_container_configuration.py`
- Modify: `scripts/verify-foundation.sh`
- Modify: `docs/development-roadmap.md`

- [x] **Step 1: Write failing packaging tests.** Assert the existing image copy
  includes `/app/config/catalysts` and `/app/fixtures/catalysts`, remains non-root,
  and foundation smoke invokes offline catalyst validation without SEC/BLS network,
  Schwab, FRED/BEA, news/social/model credentials, account, approval, or order data.
- [x] **Step 2: Run RED:** `.venv/bin/pytest tests/test_container_configuration.py -q --no-cov`.
- [x] **Step 3: Update smoke:** run
  `python -m market_trader.catalysts.cli validate /app/fixtures/catalysts/company-and-earnings`
  inside the existing non-root API flow.
- [x] **Step 4: Write runbook.** Cover macOS/Linux setup, offline validation/replay,
  SQLite migration/persistent rerun, source-run/observation/quarantine/decision/
  summary/audit inspection, explicit SEC/BLS fetch setup, SEC identified user-agent
  handling, source limits/outages/recovery, policy hashes, fixture authoring,
  UTC/XNYS/Chicago timing, and all no-Schwab/no-model/no-account/no-approval/no-order
  boundaries.
- [x] **Step 5: Run catalyst acceptance:** `.venv/bin/pytest tests/catalysts -q`.
- [x] **Step 6: Run backend gates:** `.venv/bin/ruff check .`; strict mypy over all
  new/modified files; `.venv/bin/pytest --cov=market_trader --cov-report=term-missing --cov-fail-under=90`. Also run `.venv/bin/mypy src tests` and record whether only the known 44 errors remain.
- [x] **Step 7: Run migration/frontend regressions:**
  `MARKET_TRADER_DATABASE_URL=sqlite:////tmp/market-trader-m5-verify.db .venv/bin/alembic upgrade head`; from `apps/web`, run `npm test && npm run build`.
- [x] **Step 8: Run container acceptance from repository root:**
  `docker compose build api web && docker compose up -d`; wait for health;
  `./scripts/verify-foundation.sh`; always run `docker compose down`.
- [x] **Step 9: Mark only Milestone 5 complete.** Link specification,
  implementation plan, and runbook; set next planning action to Milestone 6; leave
  later milestone statuses unchanged.
- [x] **Step 10: Review and commit:** `git diff --check && git status --short`, then
  `git add docs/milestone-5-catalysts-events-news-and-filings.md docs/development-roadmap.md apps/api/tests/test_container_configuration.py scripts/verify-foundation.sh && git commit -m "docs: complete milestone 5 catalyst delivery"`.
- [x] **Step 11: Final direct review.** Invoke
  `@superpowers:requesting-code-review`; because sub-agents are disabled, perform the
  requirements review directly against the approved specification and full branch
  diff. Address Critical/Important findings with TDD, rerun all applicable gates,
  confirm clean status, then invoke `@superpowers:finishing-a-development-branch`.

## Implementation Completion Criteria

- [x] All 16 tasks and checkboxes are complete in order.
- [x] Every accepted observation and decision has source, timestamp, stable
  identity, policy, digest, correlation, and audit lineage.
- [x] Fixed inputs reproduce classifications, risk windows, decisions,
  explanations, keys, and digests exactly.
- [x] SEC/BLS adapters use only approved origins/methods/limits and fail safely.
- [x] External text, summaries, and social-only evidence cannot confirm catalysts,
  change direction, satisfy scanner gates, alter scores, or change authoritative
  digests.
- [x] Every approved earnings and high-impact macro boundary blocks conservatively.
- [x] Missing, stale, malformed, unavailable, and conflicting required inputs fail
  closed with stable reasons.
- [x] Persistence is append-only, atomic, referentially valid, and idempotent;
  identity conflicts roll back.
- [x] Memory and persistent CLI paths render the same canonical result.
- [x] Catalyst changes create a new scanner input identity without mutating prior
  runs.
- [x] Ruff, new-file strict mypy, backend tests/coverage, migration, frontend,
  Docker, and offline smoke pass; inherited full-mypy debt is explicitly reported.
- [x] User examples use `America/Chicago`; source timestamps remain UTC and exchange
  sessions remain XNYS Eastern.
