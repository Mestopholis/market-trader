# Milestone 6 Options Analysis And Spread Construction Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build deterministic, auditable bull-call and bear-put debit-spread analysis for qualified scanner candidates without adding sizing, broker preview, approval, or order behavior.

**Architecture:** A pure `options_analysis` domain consumes immutable scanner/catalyst lineage and Milestone 3 normalized chains. Versioned configuration validates contracts, constructs and calculates only defined-risk vertical debit spreads, evaluates warnings, and ranks outputs. Fixture replay and optional repositories use that same path, preserving append-only audit records.

**Tech Stack:** Python 3.12/3.13, dataclasses, `Decimal`, SQLAlchemy 2, Alembic, pytest, Ruff, strict mypy, SQLite/PostgreSQL-compatible models, Docker Compose.

**Specification:** `docs/plans/2026-07-19-milestone-6-options-analysis-and-spread-construction-spec.md`

## Global Constraints

- Work from the approved `milestone6` branch in an isolated worktree before Task 1.
- Use test-driven development for every behavior change: write a focused failing test, observe RED, implement the smallest behavior, observe GREEN, then commit.
- Domain modules must not import SQLAlchemy, HTTP clients, environment settings, wall-clock helpers, Schwab, broker, approval, order, or model-provider packages.
- Consume only qualified Milestone 4 candidates and authoritative Milestone 3/5 structured data; raw text and summaries are not inputs.
- Use aware UTC timestamps, `Decimal` values, XNYS sessions for market-time rules, and `America/Chicago` only for display examples.
- Offline validation and analysis must not use credentials or network access.
- Do not implement naked options, credit spreads, 0DTE, sizing, broker previews, approvals, or orders.
- Run backend commands from `apps/api` using `.venv/bin/` executables.
- Run strict mypy on all new or modified Milestone 6 files. Report pre-existing failures outside that set separately.

---

## File Structure

| Path | Responsibility |
| --- | --- |
| `apps/api/src/market_trader/options_analysis/models.py` | Immutable inputs, evaluations, spreads, warnings, run results, and enums. |
| `apps/api/src/market_trader/options_analysis/serialization.py` | Canonical records, stable keys, and SHA-256 digests. |
| `apps/api/src/market_trader/options_analysis/configuration.py` | Strict policy loading and content-hash validation. |
| `apps/api/src/market_trader/options_analysis/validation.py` | Chain and contract quality, DTE, liquidity, and delta validation. |
| `apps/api/src/market_trader/options_analysis/construction.py` | Legal vertical pairing and exact payoff/Greek calculations. |
| `apps/api/src/market_trader/options_analysis/warnings.py` | Earnings, ex-dividend, assignment, expiration, and pin-risk warnings. |
| `apps/api/src/market_trader/options_analysis/engine.py` | Input resolution, blocked analysis, ranking, and final result digest. |
| `apps/api/src/market_trader/options_analysis/fixtures.py` | Strict production-fixture loading and fixture-to-domain assembly. |
| `apps/api/src/market_trader/options_analysis/replay.py` | Deterministic replay over an injected virtual clock. |
| `apps/api/src/market_trader/repositories/options_analysis.py` | Atomic idempotent run/outcome persistence and audit events. |
| `apps/api/migrations/versions/20260719_0005_options_analysis.py` | Append-only schema and SQLite triggers. |
| `apps/api/src/market_trader/options_analysis/cli.py` | Offline `validate` and `analyze` commands. |
| `apps/api/scripts/generate_options_analysis_fixtures.py` | Deterministic fixture generation with frozen manifest outputs. |
| `apps/api/fixtures/options_analysis/*` | Synthetic approved chain and warning datasets. |
| `apps/api/tests/options_analysis/*` | Focused unit, replay, CLI, persistence, and conformance tests. |

---

### Task 1: Immutable Domain Contracts And Canonical Serialization

**Files:**
- Create: `apps/api/src/market_trader/options_analysis/__init__.py`
- Create: `apps/api/src/market_trader/options_analysis/models.py`
- Create: `apps/api/src/market_trader/options_analysis/serialization.py`
- Create: `apps/api/tests/options_analysis/__init__.py`
- Create: `apps/api/tests/options_analysis/test_models.py`
- Create: `apps/api/tests/options_analysis/test_serialization.py`

**Interfaces:**
- Consumes: `CandidateResult`, `NormalizedOptionChain`, `CatalystDecision`, and aware UTC `as_of`.
- Produces: immutable `OptionsAnalysisInput`, `ContractEvaluation`, `SpreadCandidate`, `SpreadWarning`, and `OptionsAnalysisResult` values used by every later task.

- [ ] **Step 1: Write failing contract tests.** Assert naive timestamps fail, mappings are immutable, tuples are sorted, invalid directions fail, all decimals are finite, and reordered inputs produce identical canonical output. Start with:

  ```python
  class SpreadStrategy(StrEnum):
      BULL_CALL = "bull_call"
      BEAR_PUT = "bear_put"

  class EvaluationState(StrEnum):
      ACCEPTED = "accepted"
      REJECTED = "rejected"
      BLOCKED = "blocked"

  class WarningSeverity(StrEnum):
      INFO = "info"
      WARNING = "warning"
      BLOCK = "block"

  @dataclass(frozen=True)
  class OptionsAnalysisInput:
      scanner_run_key: str
      candidate: CandidateResult
      chain: NormalizedOptionChain
      symbol_catalyst: CatalystDecision
      market_catalyst: CatalystDecision
      corporate_actions: tuple[NormalizedCorporateAction, ...]
      technical_reference: TechnicalReference
      as_of: datetime
      policy_version: str
      policy_hash: str

  @dataclass(frozen=True)
  class TechnicalReference:
      underlying_price: Decimal
      technical_stop: Decimal
      snapshot_digest: str
      observed_at: datetime
  ```

- [ ] **Step 2: Run RED.** Run: `.venv/bin/pytest tests/options_analysis/test_models.py tests/options_analysis/test_serialization.py -q`. Expected: collection fails because `market_trader.options_analysis` does not exist.

- [ ] **Step 3: Implement contracts and serialization.** Add typed enums, all frozen dataclasses, `canonical_record(value)`, `stable_digest(value)`, and `stable_key(*parts)`. Encode `Decimal` as strings; call `ensure_utc`; sort warnings/evaluations/candidates by stable keys; exclude database IDs and wall-clock creation times from canonical records.

- [ ] **Step 4: Prove authority isolation.** Add a test that changing a display-only candidate explanation or catalyst explanation leaves analysis input digest unchanged, while changing a contract bid changes it.

- [ ] **Step 5: Run GREEN.** Run: `.venv/bin/ruff check src/market_trader/options_analysis tests/options_analysis && .venv/bin/mypy src/market_trader/options_analysis tests/options_analysis && .venv/bin/pytest tests/options_analysis/test_models.py tests/options_analysis/test_serialization.py -q`. Expected: all pass.

- [ ] **Step 6: Commit.** Run: `git add apps/api/src/market_trader/options_analysis apps/api/tests/options_analysis && git commit -m "feat: add options analysis domain contracts"`.

### Task 2: Versioned Options-Analysis Policy

**Files:**
- Create: `apps/api/config/options_analysis/options-analysis-policy-v1.json`
- Create: `apps/api/src/market_trader/options_analysis/configuration.py`
- Create: `apps/api/tests/options_analysis/test_configuration.py`

**Interfaces:**
- Consumes: the exact policy JSON document.
- Produces: `OptionsAnalysisPolicy` used by validation, construction, warnings, ranking, fixtures, and run identity.

- [ ] **Step 1: Write failing policy tests.** Assert the policy uses DTE `30` through `60`, multiplier `100`, standard deliverables, a `0.01` display increment, non-overlapping decimal delta bands, inclusive open-interest/volume floors, width ceilings, pin-risk distances, and an explicit ranking tuple. Reject unknown keys, numeric JSON literals for decimals, changed hashes, inverted ranges, unsupported versions, duplicate reason codes, and a policy that weakens standard-deliverable or DTE rules.

- [ ] **Step 2: Run RED.** Run: `.venv/bin/pytest tests/options_analysis/test_configuration.py -q`. Expected: import failure for `load_options_analysis_policy`.

- [ ] **Step 3: Add policy and loader.** Implement:

  ```python
  @dataclass(frozen=True)
  class OptionsAnalysisPolicy:
      version: str
      content_hash: str
      dte_min: int
      dte_max: int
      contract_multiplier: Decimal
      cent_increment: Decimal
      long_delta_min: Decimal
      long_delta_max: Decimal
      short_delta_min: Decimal
      short_delta_max: Decimal
      min_open_interest: int
      min_volume: int
      max_leg_relative_width: Decimal
      max_spread_relative_width: Decimal
      pin_warning_distance: Decimal
      pin_block_distance: Decimal
      minimum_remaining_sessions: int

  def load_options_analysis_policy(path: Path | str) -> OptionsAnalysisPolicy: ...
  ```

  Compute the content hash from canonical JSON with `content_hash` removed. Use string JSON values for every decimal.

- [ ] **Step 4: Run GREEN.** Run: `.venv/bin/ruff check src/market_trader/options_analysis/configuration.py tests/options_analysis/test_configuration.py && .venv/bin/mypy src/market_trader/options_analysis/configuration.py tests/options_analysis/test_configuration.py && .venv/bin/pytest tests/options_analysis/test_configuration.py -q`. Expected: all pass.

- [ ] **Step 5: Commit.** Run: `git add apps/api/config/options_analysis apps/api/src/market_trader/options_analysis/configuration.py apps/api/tests/options_analysis/test_configuration.py && git commit -m "feat: add options analysis policy"`.

### Task 3: Input Resolution And Contract Validation

**Files:**
- Create: `apps/api/src/market_trader/options_analysis/validation.py`
- Create: `apps/api/tests/options_analysis/test_validation.py`

**Interfaces:**
- Consumes: `OptionsAnalysisInput` and `OptionsAnalysisPolicy`.
- Produces: `ValidationOutcome(accepted, evaluations, blocking_reasons)` used by `OptionsAnalysisEngine`.

- [ ] **Step 1: Write failing validation tests.** Cover qualified bullish/bearish candidates; missing or nonqualified candidate lineage; candidate/chain symbol mismatch; missing or blocked symbol/market catalyst; chain `is_complete=False`; non-`valid` chain quality; stale timestamps; adjusted/unsupported deliverables; 29/30/60/61 DTE; zero/crossed bid/ask; missing Greeks; nonfinite values; open-interest and volume exact floors; width exact ceiling; and long/short absolute delta band boundaries.

- [ ] **Step 2: Run RED.** Run: `.venv/bin/pytest tests/options_analysis/test_validation.py -q`. Expected: import failure for `validate_analysis_input`.

- [ ] **Step 3: Implement pure validation.** Add:

  ```python
  @dataclass(frozen=True)
  class ValidationOutcome:
      accepted: tuple[NormalizedOptionContract, ...]
      evaluations: tuple[ContractEvaluation, ...]
      blocking_reasons: tuple[str, ...]

  def validate_analysis_input(
      value: OptionsAnalysisInput,
      policy: OptionsAnalysisPolicy,
  ) -> ValidationOutcome: ...
  ```

  Fail the complete analysis for chain/context errors. Emit a reason-coded evaluation for each individual contract; never coerce an invalid price, deliverable, DTE, or Greek to a usable value. Calculate leg midpoint and relative width with `Decimal` only.

- [ ] **Step 4: Add reason-vocabulary tests.** Assert output reason codes are sorted, unique, and include `candidate_not_qualified`, `chain_symbol_mismatch`, `chain_incomplete`, `chain_not_current`, `contract_nonstandard`, `dte_out_of_range`, `contract_crossed_market`, `contract_no_bid`, `contract_no_ask`, `liquidity_insufficient`, `width_excessive`, and `delta_out_of_range` exactly where expected.

- [ ] **Step 5: Run GREEN.** Run: `.venv/bin/ruff check src/market_trader/options_analysis/validation.py tests/options_analysis/test_validation.py && .venv/bin/mypy src/market_trader/options_analysis/validation.py tests/options_analysis/test_validation.py && .venv/bin/pytest tests/options_analysis/test_validation.py -q`. Expected: all pass.

- [ ] **Step 6: Commit.** Run: `git add apps/api/src/market_trader/options_analysis/validation.py apps/api/tests/options_analysis/test_validation.py && git commit -m "feat: validate option analysis contracts"`.

### Task 4: Defined-Risk Spread Construction And Exact Calculations

**Files:**
- Create: `apps/api/src/market_trader/options_analysis/construction.py`
- Create: `apps/api/tests/options_analysis/test_construction.py`

**Interfaces:**
- Consumes: accepted contracts, scanner direction, explicit `TechnicalReference`, and policy.
- Produces: unranked `SpreadCandidate` values with exact payoff, Greek, and execution metrics.

- [ ] **Step 1: Write failing construction tests.** Verify bullish candidates create only lower-long/higher-short calls; bearish candidates create only higher-long/lower-short puts; pair legs share expiration; positive debit is below width; same chain in a different order produces the same spreads; invalid debit and reversed strikes are rejected; maximum loss/gain, break-even, net Greeks, multiplier, and cent midpoint are exact.

- [ ] **Step 2: Run RED.** Run: `.venv/bin/pytest tests/options_analysis/test_construction.py -q`. Expected: import failure for `construct_spreads`.

- [ ] **Step 3: Implement legal pairing and calculations.** Add:

  ```python
  def construct_spreads(
      *,
      candidate: CandidateResult,
      contracts: tuple[NormalizedOptionContract, ...],
      technical_reference: TechnicalReference,
      policy: OptionsAnalysisPolicy,
      run_key: str,
  ) -> tuple[SpreadCandidate, ...]: ...
  ```

  Use long-leg ask minus short-leg bid as debit. For bull calls use `K_long < K_short` and break-even `K_long + debit`; for bear puts use `K_long > K_short` and break-even `K_long - debit`. Compute max loss as `debit * 100`, max gain as `(width - debit) * 100`, and net Greeks as long minus short. Read the underlying mark and stop from `technical_reference`; reject absent, nonpositive, or directionally inconsistent references.

- [ ] **Step 4: Add execution-quality tests.** Assert spread liquidity is the minimum per-leg open interest/volume, spread relative width uses executable-side prices and debit midpoint, `poor` quality blocks selection, and midpoint rounding changes display only, not debit or risk calculation.

- [ ] **Step 5: Run GREEN.** Run: `.venv/bin/ruff check src/market_trader/options_analysis/construction.py tests/options_analysis/test_construction.py && .venv/bin/mypy src/market_trader/options_analysis/construction.py tests/options_analysis/test_construction.py && .venv/bin/pytest tests/options_analysis/test_construction.py -q`. Expected: all pass.

- [ ] **Step 6: Commit.** Run: `git add apps/api/src/market_trader/options_analysis/construction.py apps/api/tests/options_analysis/test_construction.py && git commit -m "feat: construct defined risk spreads"`.

### Task 5: Event And Position Warning Evaluation

**Files:**
- Create: `apps/api/src/market_trader/options_analysis/warnings.py`
- Create: `apps/api/tests/options_analysis/test_warnings.py`

**Interfaces:**
- Consumes: a spread, current symbol/market catalyst decisions, corporate actions, policy, `as_of`, and XNYS calendar.
- Produces: sorted `SpreadWarning` records and a boolean blocked state.

- [ ] **Step 1: Write failing warning tests.** Assert active, stale, unresolved, and missing earnings evidence blocks; known ex-dividend before expiration warns; next-session ex-dividend plus an in-the-money short call blocks; short put assignment caveat is informational; expiry at the remaining-session boundary warns; and pin distances produce warning/block boundaries. Run-level macro blocks are covered by the engine tests in Task 6.

- [ ] **Step 2: Run RED.** Run: `.venv/bin/pytest tests/options_analysis/test_warnings.py -q`. Expected: import failure for `evaluate_spread_warnings`.

- [ ] **Step 3: Implement deterministic warnings.** Add:

  ```python
  def evaluate_spread_warnings(
      *,
      spread: SpreadCandidate,
      symbol_catalyst: CatalystDecision,
      market_catalyst: CatalystDecision,
      corporate_actions: tuple[NormalizedCorporateAction, ...],
      as_of: datetime,
      calendar: ExchangeCalendar,
      policy: OptionsAnalysisPolicy,
  ) -> tuple[SpreadWarning, ...]: ...
  ```

  Read only structured catalyst risk state and `CASH_DIVIDEND` dates. Include source keys/facts but no prose. Sort warnings by `(severity, code, warning_key)` and derive blocked state only from `WarningSeverity.BLOCK`.

- [ ] **Step 4: Run GREEN.** Run: `.venv/bin/ruff check src/market_trader/options_analysis/warnings.py tests/options_analysis/test_warnings.py && .venv/bin/mypy src/market_trader/options_analysis/warnings.py tests/options_analysis/test_warnings.py && .venv/bin/pytest tests/options_analysis/test_warnings.py -q`. Expected: all pass.

- [ ] **Step 5: Commit.** Run: `git add apps/api/src/market_trader/options_analysis/warnings.py apps/api/tests/options_analysis/test_warnings.py && git commit -m "feat: evaluate options risk warnings"`.

### Task 6: Analysis Engine, Ranking, And Deterministic Results

**Files:**
- Create: `apps/api/src/market_trader/options_analysis/engine.py`
- Create: `apps/api/tests/options_analysis/test_engine.py`

**Interfaces:**
- Consumes: all pure domain services from Tasks 2-5.
- Produces: `OptionsAnalysisResult` for replay, CLI, and repository use.

- [ ] **Step 1: Write failing engine tests.** Test a valid bullish run, valid bearish run, whole-run block on context/chain failure or active/unresolved market macro state, per-spread blocking with retained result, canonical ranking under shuffled contracts, rank tie-breakers, changed contract price changing digest, changed display explanation not changing digest, and no strategy outside `bull_call`/`bear_put`.

- [ ] **Step 2: Run RED.** Run: `.venv/bin/pytest tests/options_analysis/test_engine.py -q`. Expected: import failure for `OptionsAnalysisEngine`.

- [ ] **Step 3: Implement orchestration.** Add:

  ```python
  class OptionsAnalysisEngine:
      def __init__(self, policy: OptionsAnalysisPolicy, calendar: ExchangeCalendar) -> None: ...

      def analyze(self, value: OptionsAnalysisInput) -> OptionsAnalysisResult: ...
  ```

  Build run key from scanner/candidate identity, authoritative chain/catalyst/corporate-action digests, `as_of`, and policy version/hash. Rank nonblocked spreads by policy tuple `(execution_quality, spread_relative_width, max_loss, expiration, long_contract_id, short_contract_id)`; append blocked spreads deterministically after eligible ranks. Produce result counts, reason summary, and a result digest from authoritative fields only.

- [ ] **Step 4: Run GREEN.** Run: `.venv/bin/ruff check src/market_trader/options_analysis/engine.py tests/options_analysis/test_engine.py && .venv/bin/mypy src/market_trader/options_analysis/engine.py tests/options_analysis/test_engine.py && .venv/bin/pytest tests/options_analysis/test_engine.py -q`. Expected: all pass.

- [ ] **Step 5: Commit.** Run: `git add apps/api/src/market_trader/options_analysis/engine.py apps/api/tests/options_analysis/test_engine.py && git commit -m "feat: analyze and rank option spreads"`.

### Task 7: Fixture Loading, Replay, And Production Scenarios

**Files:**
- Create: `apps/api/src/market_trader/options_analysis/fixtures.py`
- Create: `apps/api/src/market_trader/options_analysis/replay.py`
- Create: `apps/api/tests/options_analysis/test_fixtures.py`
- Create: `apps/api/tests/options_analysis/test_replay.py`
- Create: `apps/api/tests/options_analysis/fixtures/minimal/manifest.json`
- Create: `apps/api/tests/options_analysis/fixtures/minimal/events.ndjson`

**Interfaces:**
- Consumes: fixture manifests and synthetic NDJSON records.
- Produces: verified `OptionsFixtureDataset` and deterministic `OptionsAnalysisResult` without a database or network.

- [ ] **Step 1: Write failing fixture tests.** Reject missing files, unknown schema/version, mismatched SHA-256, sensitive keys, naive timestamps, out-of-order records, mismatched scanner/chain symbol, unknown policy hash, changed expected digest, and malformed decimal strings. Prove replay of shuffled equivalent records is deterministic and that a virtual clock cannot move backward.

- [ ] **Step 2: Run RED.** Run: `.venv/bin/pytest tests/options_analysis/test_fixtures.py tests/options_analysis/test_replay.py -q`. Expected: import failure for `OptionsFixtureDataset`.

- [ ] **Step 3: Implement fixture/replay contracts.** Implement `OptionsFixtureDataset.load(path)`, `VirtualOptionsAnalysisClock`, and `replay_options_analysis(dataset, policy)`. Require manifest fields `options_analysis_fixture_schema_version`, `dataset_id`, `as_of`, `policy_version`, `policy_hash`, streams, expected counts, expected reason summary, and expected result digest. Reuse canonical fixture hash behavior from the scanner fixture loader; redact authorization/cookie/token/secret/password/api_key/account/approval/order-shaped keys before diagnostics.

- [ ] **Step 4: Add initial production datasets.** Create fixture directories `bull-call-qualified`, `bear-put-qualified`, `contract-boundaries`, and `risk-warnings`, each with stable manifest hashes and a single expected result digest. Keep all events synthetic and fixed in 2026.

- [ ] **Step 5: Run GREEN.** Run: `.venv/bin/pytest tests/options_analysis/test_fixtures.py tests/options_analysis/test_replay.py -q`. Expected: all pass.

- [ ] **Step 6: Commit.** Run: `git add apps/api/src/market_trader/options_analysis/fixtures.py apps/api/src/market_trader/options_analysis/replay.py apps/api/fixtures/options_analysis apps/api/tests/options_analysis && git commit -m "feat: replay option analysis fixtures"`.

### Task 8: Append-Only Persistence Schema

**Files:**
- Modify: `apps/api/src/market_trader/db/models.py`
- Create: `apps/api/migrations/versions/20260719_0005_options_analysis.py`
- Modify: `apps/api/tests/test_migrations.py`
- Create: `apps/api/tests/options_analysis/test_schema.py`

**Interfaces:**
- Consumes: completed `OptionsAnalysisResult` objects.
- Produces: ORM schema for immutable analysis runs, contract evaluations, spreads, and warnings.

- [ ] **Step 1: Write failing schema tests.** Assert upgrade reaches revision `20260719_0005`; tables, foreign keys, unique stable keys, JSON reason/warning fields, PostgreSQL GIN indexes, and SQLite append-only triggers exist. Attempt update/delete on every options-analysis table and assert SQLite aborts.

- [ ] **Step 2: Run RED.** Run: `.venv/bin/pytest tests/options_analysis/test_schema.py tests/test_migrations.py -q`. Expected: migration revision and ORM classes do not exist.

- [ ] **Step 3: Add ORM and migration.** Add `OptionsAnalysisRunORM`, `OptionContractEvaluationORM`, `OptionSpreadCandidateORM`, and `OptionSpreadWarningORM`. Create `options_analysis_runs`, `option_contract_evaluations`, `option_spread_candidates`, and `option_spread_warnings` with the keys, authoritative digests, policy metadata, structured calculation payloads, foreign keys, and indexes specified in the approved spec. Reuse the exact SQLite no-update/no-delete trigger pattern from `20260719_0004_catalyst_events.py`.

- [ ] **Step 4: Run GREEN.** Run: `.venv/bin/pytest tests/options_analysis/test_schema.py tests/test_migrations.py -q`. Expected: all pass.

- [ ] **Step 5: Commit.** Run: `git add apps/api/src/market_trader/db/models.py apps/api/migrations/versions/20260719_0005_options_analysis.py apps/api/tests/test_migrations.py apps/api/tests/options_analysis/test_schema.py && git commit -m "feat: add options analysis persistence schema"`.

### Task 9: Atomic Idempotent Repository And Audit Records

**Files:**
- Create: `apps/api/src/market_trader/repositories/options_analysis.py`
- Modify: `apps/api/src/market_trader/repositories/__init__.py`
- Create: `apps/api/tests/options_analysis/test_repository.py`

**Interfaces:**
- Consumes: a SQLAlchemy `Session` and `OptionsAnalysisResult`.
- Produces: `PersistedOptionsAnalysisRun`; caller controls commit/rollback.

- [ ] **Step 1: Write failing repository tests.** Seed symbols, scanner records, market snapshots, and catalyst records from existing repositories. Prove a run persists with children and four expected audit events; exact rerun returns existing IDs with no duplicate rows/events; a changed result digest for the same run key raises `OptionsAnalysisPersistenceConflict`; a missing candidate, symbol mismatch, or forced child insert failure rolls back the entire transaction.

- [ ] **Step 2: Run RED.** Run: `.venv/bin/pytest tests/options_analysis/test_repository.py -q`. Expected: import failure for `OptionsAnalysisRepository`.

- [ ] **Step 3: Implement repository.** Add:

  ```python
  class OptionsAnalysisRepository:
      def __init__(self, session: Session) -> None: ...

      def persist(self, result: OptionsAnalysisResult) -> PersistedOptionsAnalysisRun: ...
  ```

  Resolve the qualified candidate and its symbol from existing scanner rows. Persist source identities and stable calculations only. Append `options_analysis_run.recorded`, `option_contract_evaluation.recorded`, `option_spread_candidate.recorded`, and `option_spread_warning.recorded` through `AuditRepository`; flush but never commit.

- [ ] **Step 4: Run GREEN.** Run: `.venv/bin/ruff check src/market_trader/repositories/options_analysis.py tests/options_analysis/test_repository.py && .venv/bin/mypy src/market_trader/repositories/options_analysis.py tests/options_analysis/test_repository.py && .venv/bin/pytest tests/options_analysis/test_repository.py -q`. Expected: all pass.

- [ ] **Step 5: Commit.** Run: `git add apps/api/src/market_trader/repositories/options_analysis.py apps/api/src/market_trader/repositories/__init__.py apps/api/tests/options_analysis/test_repository.py && git commit -m "feat: persist option analysis results"`.

### Task 10: Offline CLI And Persistent Analysis Workflow

**Files:**
- Create: `apps/api/src/market_trader/options_analysis/cli.py`
- Create: `apps/api/tests/options_analysis/test_cli.py`

**Interfaces:**
- Consumes: a fixture path, policy path, optional database URL.
- Produces: compact canonical JSON and exit codes `0`, `2`, or `3`.

- [ ] **Step 1: Write failing CLI tests.** Assert `validate` never touches a database; `analyze` returns the expected result/digest in memory; `analyze --database-url` runs migrations and persists atomically; invalid manifest/policy exits `2`; repository/migration failures exit `3`; output excludes database URLs, credentials, raw payloads, and order-shaped strings.

- [ ] **Step 2: Run RED.** Run: `.venv/bin/pytest tests/options_analysis/test_cli.py -q`. Expected: module import failure.

- [ ] **Step 3: Implement commands.** Implement:

  ```text
  python -m market_trader.options_analysis.cli validate <dataset-path>
  python -m market_trader.options_analysis.cli analyze <dataset-path> [--database-url URL]
  ```

  Load the checked policy, replay production code, compare the expected result, and use `upgrade_to_head` plus `OptionsAnalysisRepository` only when persistence is explicitly requested. Print exactly one sorted JSON object on success or one sanitized JSON error on failure.

- [ ] **Step 4: Run GREEN.** Run: `.venv/bin/ruff check src/market_trader/options_analysis/cli.py tests/options_analysis/test_cli.py && .venv/bin/mypy src/market_trader/options_analysis/cli.py tests/options_analysis/test_cli.py && .venv/bin/pytest tests/options_analysis/test_cli.py -q`. Expected: all pass.

- [ ] **Step 5: Commit.** Run: `git add apps/api/src/market_trader/options_analysis/cli.py apps/api/tests/options_analysis/test_cli.py && git commit -m "feat: add options analysis CLI"`.

### Task 11: Fixture Generator And Full Conformance Coverage

**Files:**
- Create: `apps/api/scripts/generate_options_analysis_fixtures.py`
- Modify: `apps/api/fixtures/options_analysis/*/manifest.json`
- Create: `apps/api/tests/options_analysis/test_fixture_conformance.py`

**Interfaces:**
- Consumes: production fixture source data and policy.
- Produces: byte-stable NDJSON/manifest hashes, counts, reason summaries, and expected digests.

- [ ] **Step 1: Write failing conformance tests.** Execute the generator in a temporary copy and assert byte-for-byte equality with checked-in fixtures. Validate all four baseline datasets plus cases for adjusted contracts, 29/30/60/61 DTE, liquidity/width/delta boundaries, duplicate identity, changed authoritative chain conflict, earnings, ex-dividend, early assignment, expiration, pin risk, macro block, early close, daylight saving, and Chicago display-only rendering.

- [ ] **Step 2: Run RED.** Run: `.venv/bin/pytest tests/options_analysis/test_fixture_conformance.py -q`. Expected: missing generator or fixture groups.

- [ ] **Step 3: Implement generator.** Build all fixture records from fixed UTC constants and exact decimal strings. Sort streams by ingestion time and stable identity; write hashes and expected results only in generator output. Never make tests regenerate expected output in place.

- [ ] **Step 4: Run GREEN.** Run: `.venv/bin/python scripts/generate_options_analysis_fixtures.py && .venv/bin/pytest tests/options_analysis/test_fixture_conformance.py -q`. Expected: generator is byte-stable and all conformance tests pass.

- [ ] **Step 5: Commit.** Run: `git add apps/api/scripts/generate_options_analysis_fixtures.py apps/api/fixtures/options_analysis apps/api/tests/options_analysis/test_fixture_conformance.py && git commit -m "feat: add options analysis conformance fixtures"`.

### Task 12: Operations Documentation, Packaging, And Completion Gates

**Files:**
- Create: `docs/milestone-6-options-analysis-and-spread-construction.md`
- Modify: `docs/development-roadmap.md`
- Modify: `docker-compose.yml` only if the API image does not already copy `config/options_analysis` and `fixtures/options_analysis` through existing broad copy rules.
- Modify: `scripts/verify-foundation.sh` to validate the `bull-call-qualified` fixture offline.
- Modify: `apps/api/tests/test_container_configuration.py`

**Interfaces:**
- Consumes: final CLI, fixtures, policy, migrations, and image configuration.
- Produces: an operator runbook, packaged offline validation, and milestone status update.

- [ ] **Step 1: Write failing packaging tests.** Assert the non-root container includes the policy and qualified fixture, can run `python -m market_trader.options_analysis.cli validate fixtures/options_analysis/bull-call-qualified`, and has no environment/config path for broker credentials, approval, preview, or order execution.

- [ ] **Step 2: Run RED.** Run: `.venv/bin/pytest tests/test_container_configuration.py -q`. Expected: container smoke assertion for the options-analysis fixture is absent.

- [ ] **Step 3: Write the runbook and smoke hook.** Document local setup, offline validation, memory analysis, persistent SQLite analysis, read-only inspection queries, policy/fixture review rules, exit codes, supported spread types, warning meanings, and explicit non-capabilities. Mark Milestone 6 complete only after all exit criteria pass; update the roadmap’s next planning action to Milestone 7.

- [ ] **Step 4: Run focused verification.** Run: `.venv/bin/python scripts/generate_options_analysis_fixtures.py && .venv/bin/pytest tests/options_analysis tests/test_migrations.py tests/test_container_configuration.py -q && .venv/bin/ruff check . && .venv/bin/mypy src/market_trader/options_analysis src/market_trader/repositories/options_analysis.py tests/options_analysis`.

- [ ] **Step 5: Run full verification.** Run backend `pytest`; run frontend `npm test` and production build; upgrade a fresh SQLite database to head; build Docker Compose; run `./scripts/verify-foundation.sh`; then bring Compose down. Record any unrelated pre-existing failures exactly.

- [ ] **Step 6: Commit.** Run: `git add docs/milestone-6-options-analysis-and-spread-construction.md docs/development-roadmap.md scripts/verify-foundation.sh apps/api/tests/test_container_configuration.py docker-compose.yml && git commit -m "docs: complete milestone 6 options analysis delivery"`.

## Implementation Completion Criteria

- [ ] All production fixture groups validate and analyze with frozen hashes, counts, reasons, and result digests.
- [ ] Identical authoritative inputs produce identical candidates, warnings, ranks, and persisted records; display-only changes do not.
- [ ] Invalid, adjusted, stale, incomplete, illiquid, crossed, zero-priced, or out-of-range contracts are retained as reason-coded rejections and cannot form a spread.
- [ ] Only qualified scanner candidates produce bull-call or bear-put debit-spread analysis, with exact maximum-loss and assignment-stress visibility.
- [ ] Persistent reruns are idempotent; conflicts and missing lineage roll back atomically; append-only and audit contracts hold.
- [ ] CLI, runbook, Docker fixture packaging, and smoke validation remain offline and contain no broker, approval, or order capability.
