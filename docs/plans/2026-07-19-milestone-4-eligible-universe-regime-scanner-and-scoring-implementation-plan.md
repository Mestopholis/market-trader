# Milestone 4 Eligible Universe, Regime, Scanner, And Scoring Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build an offline, deterministic scanner that evaluates a versioned 30-symbol universe, classifies market regime, runs five explainable strategies, scores passing signals, and optionally persists an atomic, idempotent result.

**Architecture:** Add a pure `market_trader.scanner` pipeline over immutable typed inputs, with JSON configuration and fixture loaders at the boundary. Reuse Milestone 3 normalized observations, sanitization, canonical digest, replay clock, and repository ingestion; keep database IDs outside domain result identities. A repository sink resolves stable ingestion keys to primary snapshot IDs and writes every scan artifact plus audit events in one caller-owned transaction.

**Tech Stack:** Python 3.12, frozen dataclasses, `Decimal`, standard-library JSON/CLI, SQLAlchemy 2, Alembic, SQLite/PostgreSQL, pytest, Ruff, strict mypy, Docker.

## Global Constraints

- Work in a Milestone 4 feature worktree created from this planning branch.
- Read `docs/plans/2026-07-19-milestone-4-eligible-universe-regime-scanner-and-scoring-spec.md` before Task 1.
- Use `@superpowers:test-driven-development` for each behavior change and `@superpowers:verification-before-completion` before completion claims.
- Keep scanner domain code free of SQLAlchemy, filesystem, network, wall-clock, Schwab, broker, approval, order, and UI imports.
- Reject naive timestamps and never call `utc_now()` during scanner evaluation.
- Use `Decimal` for prices, ratios, weights, scores, and thresholds. Render scores at six decimal places.
- Sort symbols, reasons, lineage, gates, components, and records before digesting. Exclude database IDs and wall-clock values.
- Use only the stable reason vocabulary in the specification; tests must exercise every listed code and reject unversioned additions.
- Keep fixtures synthetic, bounded, credential-free, and fixed in 2026.
- Run backend commands from `apps/api` with `.venv/bin/` executables.
- Do not mark Milestone 4 complete until Task 16 passes every gate.

---

### Task 1: Scanner Domain Contracts And Stable Serialization

**Interfaces**

- Consumes: Milestone 3 normalized candles/provider states, ingestion keys, payload digests, and explicit `as_of`.
- Produces: immutable scanner records and canonical JSON/digests used by later tasks.

**Files:**

- Create: `apps/api/src/market_trader/scanner/__init__.py`
- Create: `apps/api/src/market_trader/scanner/models.py`
- Create: `apps/api/src/market_trader/scanner/serialization.py`
- Create: `apps/api/tests/scanner/__init__.py`
- Create: `apps/api/tests/scanner/test_models.py`
- Create: `apps/api/tests/scanner/test_serialization.py`

- [ ] **Step 1: Write failing contract tests.** Prove naive `as_of` is rejected, enums contain only approved values, reasons are sorted/deduplicated, mappings are immutable, and differently ordered inputs produce identical JSON and SHA-256 digests. Test these public contracts:

  ```python
  class EligibilityStatus(StrEnum):
      ELIGIBLE = "eligible"
      INELIGIBLE = "ineligible"
      BLOCKED = "blocked"

  class RegimeState(StrEnum):
      BULLISH = "bullish"
      BEARISH = "bearish"
      NEUTRAL = "neutral"
      MIXED = "mixed"
      BLOCKED = "blocked"

  class StrategyStatus(StrEnum):
      PASSED = "passed"
      FAILED = "failed"
      BLOCKED = "blocked"
      NOT_APPLICABLE = "not_applicable"

  @dataclass(frozen=True)
  class EvidenceRef:
      lineage_id: str
      source: str
      event_id: str
      ingestion_key: str
      payload_digest: str
      observed_at: datetime
      ingested_at: datetime

  @dataclass(frozen=True)
  class PolicyVersions:
      universe: str = "eligible-universe-v1"
      eligibility: str = "eligibility-policy-v1"
      features: str = "scanner-features-v1"
      regime: str = "market-regime-v1"
      strategies: str = "scanner-strategies-v1"
      scoring: str = "candidate-scoring-v1"
      evidence: str = "scanner-evidence-v1"
      fixture: str = "scanner-fixture-v1"
  ```

- [ ] **Step 2: Run RED:** `.venv/bin/pytest tests/scanner/test_models.py tests/scanner/test_serialization.py -q`. Expected: collection fails because the package is absent.
- [ ] **Step 3: Implement the types.** Include `Direction`, `PolicyVersions`, `SymbolInput`, `ScannerInput`, `FeatureSet`, `RegimeResult`, `EligibilityResult`, `GateResult`, `ComponentScore`, `StrategyResult`, `CandidateResult`, `ScanCounts`, and `ScanResult`. Add `canonical_record(value)` and `stable_digest(value)` using Milestone 3 `canonical_digest`.
- [ ] **Step 4: Render scores exactly:** `format(value.quantize(Decimal("0.000001")), "f")`.
- [ ] **Step 5: Run GREEN:** `.venv/bin/ruff check src/market_trader/scanner tests/scanner && .venv/bin/mypy src/market_trader/scanner tests/scanner && .venv/bin/pytest tests/scanner/test_models.py tests/scanner/test_serialization.py -q`.
- [ ] **Step 6: Commit:** `git add apps/api/src/market_trader/scanner apps/api/tests/scanner && git commit -m "feat: add scanner domain contracts"`.

---

### Task 2: Versioned Scanner Configuration

**Interfaces**

- Consumes: five local JSON files and exact policy versions from the spec.
- Produces: `ScannerConfiguration` with verified allowlist, thresholds, and hashes.

**Files:**

- Create: `apps/api/config/scanner/eligible-universe-v1.json`
- Create: `apps/api/config/scanner/eligibility-policy-v1.json`
- Create: `apps/api/config/scanner/market-regime-v1.json`
- Create: `apps/api/config/scanner/scanner-strategies-v1.json`
- Create: `apps/api/config/scanner/candidate-scoring-v1.json`
- Create: `apps/api/src/market_trader/scanner/configuration.py`
- Create: `apps/api/tests/scanner/test_configuration.py`

- [ ] **Step 1: Write failing tests.** Assert exact versions, exact 30-symbol order/membership, roles/types, inclusive thresholds, 200 sessions, regime weights totaling 100, five strategies, family caps totaling 100, and threshold `70.000000`. Reject unknown keys, duplicates, wrong versions/hashes, JSON numeric decimals, and invalid totals.
- [ ] **Step 2: Run RED:** `.venv/bin/pytest tests/scanner/test_configuration.py -q`.
- [ ] **Step 3: Add exact JSON.** The universe is `SPY QQQ IWM DIA XLB XLC XLE XLF XLI XLK XLP XLRE XLU XLV XLY AAPL MSFT NVDA AMZN META GOOGL TSLA AMD AVGO JPM XOM UNH LLY WMT COST`; encode every decimal as a string.
- [ ] **Step 4: Implement:**

  ```python
  @dataclass(frozen=True)
  class ScannerConfiguration:
      universe: UniversePolicy
      eligibility: EligibilityPolicy
      regime: RegimePolicy
      strategies: StrategyPolicy
      scoring: ScoringPolicy
      content_hashes: Mapping[str, str]

  def load_scanner_configuration(path: Path | str) -> ScannerConfiguration: ...
  ```

  Hash canonical parsed payloads with `content_hash` omitted, compare declared hashes, and reject undeclared fields.
- [ ] **Step 5: Run GREEN:** `.venv/bin/ruff check src/market_trader/scanner/configuration.py tests/scanner/test_configuration.py && .venv/bin/mypy src/market_trader/scanner/configuration.py tests/scanner/test_configuration.py && .venv/bin/pytest tests/scanner/test_configuration.py -q`.
- [ ] **Step 6: Commit:** `git add apps/api/config/scanner apps/api/src/market_trader/scanner/configuration.py apps/api/tests/scanner/test_configuration.py && git commit -m "feat: add versioned scanner configuration"`.

---

### Task 3: Supplemental Evidence Validation

**Interfaces**

- Consumes: bounded breadth, sector, volatility, macro, and catalyst fixture records.
- Produces: immutable `SupplementalEvidence` or a stable validation failure.

**Files:**

- Create: `apps/api/src/market_trader/scanner/evidence.py`
- Create: `apps/api/tests/scanner/test_evidence.py`

- [ ] **Step 1: Write failing tests.** Cover all evidence types, UTC and `as_of` bounds, allowed states, attribution, unique lineage, bounded strings/collections, catalyst materiality/direction, conflicts, and credential-like keys.
- [ ] **Step 2: Run RED:** `.venv/bin/pytest tests/scanner/test_evidence.py -q`.
- [ ] **Step 3: Implement:**

  ```python
  class EvidenceValidationError(ValueError):
      pass

  def parse_supplemental_evidence(
      records: Sequence[Mapping[str, object]], *, as_of: datetime
  ) -> SupplementalEvidence: ...
  ```

  Model breadth counts, all 11 sector returns, volatility level/direction, macro `risk_on|neutral|risk_off|blocked`, and catalyst `positive|negative|unclear`. Preserve references but reject article bodies.
- [ ] **Step 4: Run GREEN:** `.venv/bin/ruff check src/market_trader/scanner/evidence.py tests/scanner/test_evidence.py && .venv/bin/mypy src/market_trader/scanner/evidence.py tests/scanner/test_evidence.py && .venv/bin/pytest tests/scanner/test_evidence.py -q`.
- [ ] **Step 5: Commit:** `git add apps/api/src/market_trader/scanner/evidence.py apps/api/tests/scanner/test_evidence.py && git commit -m "feat: validate scanner evidence contracts"`.

---

### Task 4: Deterministic Feature Calculation

**Interfaces**

- Consumes: daily/one-minute normalized candles ending at `as_of`.
- Produces: `FeatureResult` values and stable shared-feature reasons.

**Files:**

- Create: `apps/api/src/market_trader/scanner/features.py`
- Create: `apps/api/tests/scanner/test_features.py`

- [ ] **Step 1: Write failing formula tests.** Cover adjusted close, SMA 20/50/200, 20-session SMA-50 slope, prior 20 high/low excluding latest, median dollar volume 20, relative volume 20, regular-session VWAP, completed XNYS-aligned five-minute bars, session OHLC, and cross-sectional percentiles. Include insufficient history, zero division, missing VWAP, nonfinite/conflicting intervals, partial buckets, early close, DST, reordered input, and future observations.
- [ ] **Step 2: Run RED:** `.venv/bin/pytest tests/scanner/test_features.py -q`.
- [ ] **Step 3: Implement:**

  ```python
  class FeatureCalculator:
      version = "scanner-features-v1"

      def calculate(
          self, symbol: SymbolInput, *, as_of: datetime, session: ExchangeSession
      ) -> FeatureResult: ...

  def assign_relative_performance_percentiles(
      features: Sequence[FeatureResult],
  ) -> tuple[FeatureResult, ...]: ...
  ```

  Use only candles with `end <= as_of`, align five-minute buckets from session open, assign deterministic minimum rank for ties, and return reasons instead of zeros.
- [ ] **Step 4: Run GREEN:** `.venv/bin/ruff check src/market_trader/scanner/features.py tests/scanner/test_features.py && .venv/bin/mypy src/market_trader/scanner/features.py tests/scanner/test_features.py && .venv/bin/pytest tests/scanner/test_features.py -q`.
- [ ] **Step 5: Commit:** `git add apps/api/src/market_trader/scanner/features.py apps/api/tests/scanner/test_features.py && git commit -m "feat: calculate deterministic scanner features"`.

---

### Task 5: Global Eligibility Evaluation

**Interfaces**

- Consumes: universe member, features, provider/freshness/halt/action evidence.
- Produces: one `EligibilityResult` per symbol.

**Files:**

- Create: `apps/api/src/market_trader/scanner/eligibility.py`
- Create: `apps/api/tests/scanner/test_eligibility.py`

- [ ] **Step 1: Write failing tests.** Exercise below/equal/above $10, $1,000, 200 sessions, and $25m median dollar volume; allowed/unsupported instruments; inactive symbols; unavailable provider; stale/missing data; halt/non-update; unsupported adjustment; unresolved action; and sorted multiple reasons. Incomplete evidence must be `blocked`, not `ineligible`.
- [ ] **Step 2: Run RED:** `.venv/bin/pytest tests/scanner/test_eligibility.py -q`.
- [ ] **Step 3: Implement `EligibilityEvaluator.evaluate(member, features, quality) -> EligibilityResult` with version `eligibility-policy-v1`.** Evaluate blockers first, factual eligibility failures second, and retain bounded observed values.
- [ ] **Step 4: Run GREEN:** `.venv/bin/ruff check src/market_trader/scanner/eligibility.py tests/scanner/test_eligibility.py && .venv/bin/mypy src/market_trader/scanner/eligibility.py tests/scanner/test_eligibility.py && .venv/bin/pytest tests/scanner/test_eligibility.py -q`.
- [ ] **Step 5: Commit:** `git add apps/api/src/market_trader/scanner/eligibility.py apps/api/tests/scanner/test_eligibility.py && git commit -m "feat: evaluate scanner eligibility"`.

---

### Task 6: Market Regime Classification

**Interfaces**

- Consumes: broad ETF features and supplemental regime evidence.
- Produces: six components, signed score -100..100, and approved regime state.

**Files:**

- Create: `apps/api/src/market_trader/scanner/regime.py`
- Create: `apps/api/tests/scanner/test_regime.py`

- [ ] **Step 1: Write failing tests.** Cover component weights 30/20/15/10/15/10, positive/zero/negative values, exact +/-35 boundaries, all five states, trend/breadth divergence, fewer-than-seven sector dispersion, stale/missing/conflicting critical data, macro blocked, reason ordering, and order independence.
- [ ] **Step 2: Run RED:** `.venv/bin/pytest tests/scanner/test_regime.py -q`.
- [ ] **Step 3: Implement `RegimeClassifier.classify(broad_features, evidence) -> RegimeResult` with version `market-regime-v1`.** Block invalid critical families and preserve signed context for mixed state.
- [ ] **Step 4: Run GREEN:** `.venv/bin/ruff check src/market_trader/scanner/regime.py tests/scanner/test_regime.py && .venv/bin/mypy src/market_trader/scanner/regime.py tests/scanner/test_regime.py && .venv/bin/pytest tests/scanner/test_regime.py -q`.
- [ ] **Step 5: Commit:** `git add apps/api/src/market_trader/scanner/regime.py apps/api/tests/scanner/test_regime.py && git commit -m "feat: classify deterministic market regime"`.

---

### Task 7: Breakout And Breakdown Strategies

**Interfaces**

- Consumes: eligible features and regime.
- Produces: bullish-breakout and bearish-breakdown strategy results.

**Files:**

- Create: `apps/api/src/market_trader/scanner/strategies/__init__.py`
- Create: `apps/api/src/market_trader/scanner/strategies/base.py`
- Create: `apps/api/src/market_trader/scanner/strategies/momentum.py`
- Create: `apps/api/tests/scanner/strategies/__init__.py`
- Create: `apps/api/tests/scanner/strategies/test_momentum.py`

- [ ] **Step 1: Write failing tests.** For both directions test pass, each failed gate, unavailable features, blocked/incompatible/mixed regime, relative volume exactly 1.50, VWAP equality, trigger equality, multiple failures, and stable ordering. False gates yield `failed`; unavailable evidence yields `blocked`.
- [ ] **Step 2: Run RED:** `.venv/bin/pytest tests/scanner/strategies/test_momentum.py -q`.
- [ ] **Step 3: Define `StrategyEvaluator` protocol with `strategy_id`, `version`, and `evaluate(features, regime, evidence) -> StrategyResult`; implement `BullishBreakoutEvaluator` and `BearishBreakdownEvaluator`.** Do not score in evaluators.
- [ ] **Step 4: Run GREEN:** `.venv/bin/ruff check src/market_trader/scanner/strategies tests/scanner/strategies && .venv/bin/mypy src/market_trader/scanner/strategies tests/scanner/strategies && .venv/bin/pytest tests/scanner/strategies/test_momentum.py -q`.
- [ ] **Step 5: Commit:** `git add apps/api/src/market_trader/scanner/strategies apps/api/tests/scanner/strategies && git commit -m "feat: evaluate breakout and breakdown strategies"`.

---

### Task 8: Pullback And Failed-Rally Strategies

**Interfaces**

- Consumes: eligible features with complete five-minute aggregates and regime.
- Produces: bullish-pullback and bearish-failed-rally strategy results.

**Files:**

- Create: `apps/api/src/market_trader/scanner/strategies/reversal.py`
- Create: `apps/api/tests/scanner/strategies/test_reversal.py`

- [ ] **Step 1: Write failing tests.** Cover exact 1% SMA-20 boundaries, strict SMA-50 hold/rejection, candle body and prior extreme confirmation, missing/partial aggregates, neutral/mixed direction, all statuses, and mirrored logic.
- [ ] **Step 2: Run RED:** `.venv/bin/pytest tests/scanner/strategies/test_reversal.py -q`.
- [ ] **Step 3: Implement `BullishPullbackEvaluator` and `BearishFailedRallyEvaluator`.** Keep explicit named gates; share only direction helpers.
- [ ] **Step 4: Run GREEN:** `.venv/bin/ruff check src/market_trader/scanner/strategies/reversal.py tests/scanner/strategies/test_reversal.py && .venv/bin/mypy src/market_trader/scanner/strategies/reversal.py tests/scanner/strategies/test_reversal.py && .venv/bin/pytest tests/scanner/strategies/test_reversal.py -q`.
- [ ] **Step 5: Commit:** `git add apps/api/src/market_trader/scanner/strategies/reversal.py apps/api/tests/scanner/strategies/test_reversal.py && git commit -m "feat: evaluate scanner reversal strategies"`.

---

### Task 9: News Continuation Strategy

**Interfaces**

- Consumes: eligible features, regime, and attributed catalysts.
- Produces: one news-continuation result; `not_applicable` only when no current material catalyst exists.

**Files:**

- Create: `apps/api/src/market_trader/scanner/strategies/news.py`
- Create: `apps/api/tests/scanner/strategies/test_news.py`

- [ ] **Step 1: Write failing tests.** Cover positive/negative passes, no catalyst, stale, non-material, unclear, missing attribution, duplicate lineage, independent conflict, relative volume, VWAP, session-open hold, regime opposition exactly 35, blocked regime, and ordering.
- [ ] **Step 2: Run RED:** `.venv/bin/pytest tests/scanner/strategies/test_news.py -q`.
- [ ] **Step 3: Implement `NewsContinuationEvaluator`.** Deduplicate by lineage before conflict checks; block malformed/stale/conflicting supplied evidence; never inspect article text.
- [ ] **Step 4: Run GREEN:** `.venv/bin/ruff check src/market_trader/scanner/strategies/news.py tests/scanner/strategies/test_news.py && .venv/bin/mypy src/market_trader/scanner/strategies/news.py tests/scanner/strategies/test_news.py && .venv/bin/pytest tests/scanner/strategies/test_news.py -q`.
- [ ] **Step 5: Commit:** `git add apps/api/src/market_trader/scanner/strategies/news.py apps/api/tests/scanner/strategies/test_news.py && git commit -m "feat: evaluate news continuation strategy"`.

---

### Task 10: Evidence-Family Scoring And Candidate Selection

**Interfaces**

- Consumes: eligibility, strategy result, features, regime, and scoring policy.
- Produces: capped component scores, total, and optional qualified candidate.

**Files:**

- Create: `apps/api/src/market_trader/scanner/scoring.py`
- Create: `apps/api/tests/scanner/test_scoring.py`

- [ ] **Step 1: Write failing tests.** Cover every contribution and cap: market direction 25, price structure 30, participation/liquidity 20, relative performance 15, catalyst 10. Test pre-cap/final values, duplicate lineage, Decimal arithmetic, clamp, technical maximum without catalyst, `69.999999`, `70.000000`, `70.000001`, failed high-score gates, blocked/ineligible symbols, and traceability.
- [ ] **Step 2: Run RED:** `.venv/bin/pytest tests/scanner/test_scoring.py -q`.
- [ ] **Step 3: Implement:**

  ```python
  class CandidateScorer:
      version = "candidate-scoring-v1"
      def score(self, strategy: StrategyResult, features: FeatureResult,
                regime: RegimeResult) -> ScoredStrategyResult: ...

  class CandidateSelector:
      def select(self, eligibility: EligibilityResult,
                 scored: ScoredStrategyResult) -> CandidateResult | None: ...
  ```

  Deduplicate by `(family, lineage_id)`, cap families independently, and emit status exactly `qualified` only when all gates pass and score is at least `70.000000`.
- [ ] **Step 4: Run GREEN:** `.venv/bin/ruff check src/market_trader/scanner/scoring.py tests/scanner/test_scoring.py && .venv/bin/mypy src/market_trader/scanner/scoring.py tests/scanner/test_scoring.py && .venv/bin/pytest tests/scanner/test_scoring.py -q`.
- [ ] **Step 5: Commit:** `git add apps/api/src/market_trader/scanner/scoring.py apps/api/tests/scanner/test_scoring.py && git commit -m "feat: score signals and select candidates"`.

---

### Task 11: Deterministic Scan Engine

**Interfaces**

- Consumes: `ScannerInput`, configuration, and XNYS session.
- Produces: ordered `ScanResult` with stable keys, counts, input digest, and result digest.

**Files:**

- Create: `apps/api/src/market_trader/scanner/engine.py`
- Create: `apps/api/tests/scanner/test_engine.py`

- [ ] **Step 1: Write failing invariant tests.** Assert one eligibility result per member; five signals per eligible symbol; none for blocked/ineligible symbols; no candidate without passing signal; failed gates cannot be overcome; stable keys include versions; order changes and future observations cannot affect output; exact input reproduces digest.
- [ ] **Step 2: Run RED:** `.venv/bin/pytest tests/scanner/test_engine.py -q`.
- [ ] **Step 3: Implement `ScannerEngine.__init__(configuration)` and `scan(scanner_input) -> ScanResult`.** Sequence validation, features, regime, eligibility, five evaluators, scoring, selection, stable identities, and digests. Retain one primary market ingestion key per signal for FK resolution.
- [ ] **Step 4: Run GREEN:** `.venv/bin/ruff check src/market_trader/scanner tests/scanner/test_engine.py && .venv/bin/mypy src/market_trader/scanner tests/scanner/test_engine.py && .venv/bin/pytest tests/scanner -q`.
- [ ] **Step 5: Commit:** `git add apps/api/src/market_trader/scanner apps/api/tests/scanner && git commit -m "feat: orchestrate deterministic scanner runs"`.

---

### Task 12: Scanner Fixture Manifest And Loader

**Interfaces**

- Consumes: manifest, Milestone 3 provider streams, and supplemental NDJSON.
- Produces: validated fixture dataset, assembled scanner input, expected outcomes.

**Files:**

- Create: `apps/api/src/market_trader/scanner/fixtures.py`
- Create: `apps/api/tests/scanner/test_fixture_loader.py`
- Create: `apps/api/tests/scanner/fixtures/minimal/manifest.json`
- Create: `apps/api/tests/scanner/fixtures/minimal/market.ndjson`
- Create: `apps/api/tests/scanner/fixtures/minimal/supplemental.ndjson`

- [ ] **Step 1: Write failing tests.** Cover `scanner-fixture-v1`, fixed UTC `as_of`, XNYS session date, versions/hashes, filename confinement, SHA-256/counts, ingestion order, post-`as_of` records, undeclared/missing files, sensitive keys, expected result schema, and sanitized malformed JSON.
- [ ] **Step 2: Run RED:** `.venv/bin/pytest tests/scanner/test_fixture_loader.py -q`.
- [ ] **Step 3: Implement `ScannerFixtureDataset.load(path)` and `assemble_scanner_input(dataset, accepted)`.** Reuse `FixtureDataset` and `ReplayEngine`; do not add a second normalizer.
- [ ] **Step 4: Run GREEN:** `.venv/bin/ruff check src/market_trader/scanner/fixtures.py tests/scanner/test_fixture_loader.py && .venv/bin/mypy src/market_trader/scanner/fixtures.py tests/scanner/test_fixture_loader.py && .venv/bin/pytest tests/scanner/test_fixture_loader.py -q`.
- [ ] **Step 5: Commit:** `git add apps/api/src/market_trader/scanner/fixtures.py apps/api/tests/scanner && git commit -m "feat: load deterministic scanner fixtures"`.

---

### Task 13: Scanner Persistence Schema

**Interfaces**

- Consumes: Milestone 3 schema revision `20260718_0002`.
- Produces: scanner tables and lineage columns/constraints on decisions.

**Files:**

- Create: `apps/api/migrations/versions/20260719_0003_scanner_decisions.py`
- Modify: `apps/api/src/market_trader/db/models.py`
- Modify: `apps/api/tests/test_migrations.py`
- Create: `apps/api/tests/scanner/test_schema.py`

- [ ] **Step 1: Write failing tests.** Upgrade a Milestone 3 DB to head and assert `scanner_runs`, `eligibility_decisions`, specified columns/FKs/uniques/indexes, SQLite JSON, PostgreSQL JSONB/GIN compilation, and preservation of existing decision rows with nullable scanner columns.
- [ ] **Step 2: Run RED:** `.venv/bin/pytest tests/test_migrations.py tests/scanner/test_schema.py -q`.
- [ ] **Step 3: Add revision `20260719_0003`.** Add `ScannerRunORM` and `EligibilityDecisionORM`. Extend `SignalORM` with nullable `signal_key`, `scanner_run_id`, `strategy_id`, `input_digest`, `reason_codes`, `gate_payload`, `component_score_payload`, `scoring_policy_version`; extend `CandidateORM` with nullable `candidate_key`, `scanner_run_id`, `strategy_id`, `direction`, `input_digest`, `scoring_policy_version`. Stable keys are unique when non-null.
- [ ] **Step 4: Run GREEN:** `.venv/bin/ruff check migrations/versions/20260719_0003_scanner_decisions.py src/market_trader/db/models.py tests/test_migrations.py tests/scanner/test_schema.py && .venv/bin/mypy src/market_trader/db/models.py tests/scanner/test_schema.py && .venv/bin/pytest tests/test_migrations.py tests/scanner/test_schema.py -q`.
- [ ] **Step 5: Commit:** `git add apps/api/migrations/versions/20260719_0003_scanner_decisions.py apps/api/src/market_trader/db/models.py apps/api/tests/test_migrations.py apps/api/tests/scanner/test_schema.py && git commit -m "feat: add scanner persistence schema"`.

---

### Task 14: Atomic And Idempotent Scanner Repository Sink

**Interfaces**

- Consumes: complete `ScanResult`, existing symbols, and snapshots ingested in the same session.
- Produces: atomic run/decisions/signals/candidates/audits, or matching existing run.

**Files:**

- Create: `apps/api/src/market_trader/repositories/scanner.py`
- Modify: `apps/api/src/market_trader/repositories/decisions.py`
- Modify: `apps/api/src/market_trader/repositories/__init__.py`
- Create: `apps/api/tests/scanner/test_repository_sink.py`
- Modify: `apps/api/tests/test_decision_repositories.py`

- [ ] **Step 1: Write failing integration tests.** Seed symbols and observations through `RepositoryIngestionSink`; assert one transaction writes run, 30 decisions, five signals per eligible symbol, candidates only for qualifiers, and exactly `scanner_run.completed`, `eligibility_decision.recorded`, `scanner_signal.recorded`, and `scanner_candidate.qualified` audits. Cover exact rerun, changed digest conflict, missing symbol/snapshot, injected audit/flush failure, and rollback.
- [ ] **Step 2: Run RED:** `.venv/bin/pytest tests/scanner/test_repository_sink.py tests/test_decision_repositories.py -q`.
- [ ] **Step 3: Implement:**

  ```python
  class ScannerPersistenceConflict(RuntimeError):
      pass

  class ScannerRepository:
      def __init__(self, session: Session) -> None: ...
      def persist(self, result: ScanResult) -> PersistedScanRun: ...
  ```

  Resolve display symbols and `MarketDataRepository.get_snapshot_by_ingestion_key`. Existing `run_key` returns only when input/result digests match; otherwise conflict. Add append-only scanner methods to `DecisionRepository`, preserve old APIs/audit names, and never commit/rollback inside repositories.
- [ ] **Step 4: Run GREEN:** `.venv/bin/ruff check src/market_trader/repositories tests/scanner/test_repository_sink.py tests/test_decision_repositories.py && .venv/bin/mypy src/market_trader/repositories tests/scanner/test_repository_sink.py && .venv/bin/pytest tests/scanner/test_repository_sink.py tests/test_decision_repositories.py tests/test_market_data_repository.py -q`.
- [ ] **Step 5: Commit:** `git add apps/api/src/market_trader/repositories apps/api/tests/scanner/test_repository_sink.py apps/api/tests/test_decision_repositories.py && git commit -m "feat: persist atomic scanner decisions"`.

---

### Task 15: Scanner CLI And Production Fixture Matrix

**Interfaces**

- Consumes: `validate|scan`, dataset, optional database URL, config, fixtures.
- Produces: sorted JSON stdout, sanitized JSON stderr, exit code 0/2/3.

**Files:**

- Create: `apps/api/src/market_trader/scanner/cli.py`
- Create: `apps/api/tests/scanner/test_cli.py`
- Create: `apps/api/tests/scanner/test_fixture_conformance.py`
- Create: `apps/api/fixtures/scanner/bullish/manifest.json`
- Create: `apps/api/fixtures/scanner/bullish/market.ndjson`
- Create: `apps/api/fixtures/scanner/bullish/supplemental.ndjson`
- Create: `apps/api/fixtures/scanner/bearish/manifest.json`
- Create: `apps/api/fixtures/scanner/bearish/market.ndjson`
- Create: `apps/api/fixtures/scanner/bearish/supplemental.ndjson`
- Create: `apps/api/fixtures/scanner/neutral-mixed-blocked/manifest.json`
- Create: `apps/api/fixtures/scanner/neutral-mixed-blocked/market.ndjson`
- Create: `apps/api/fixtures/scanner/neutral-mixed-blocked/supplemental.ndjson`
- Create: `apps/api/fixtures/scanner/boundaries-and-conflicts/manifest.json`
- Create: `apps/api/fixtures/scanner/boundaries-and-conflicts/market.ndjson`
- Create: `apps/api/fixtures/scanner/boundaries-and-conflicts/supplemental.ndjson`

- [ ] **Step 1: Write failing tests.** Assert exact commands, deterministic output, database-free default, `validate` expected comparisons, persistent migration/ingestion/scan transaction, exact rerun, exit codes, no URL leakage, and sanitized exceptions. Parametrize every production scenario in the spec: five strategies, all regimes, normal/early-close/DST timing, boundaries, stale/missing/conflicting/halted/action inputs, caps, idempotence, and changed-input conflict.
- [ ] **Step 2: Run RED:** `.venv/bin/pytest tests/scanner/test_cli.py tests/scanner/test_fixture_conformance.py -q`.
- [ ] **Step 3: Implement `main(argv: Sequence[str] | None = None) -> int`.** Persistent scan runs Alembic, opens one session, replays with `RepositoryIngestionSink`, assembles the same input, scans, persists, and commits once; any error rolls back. Memory/persistent paths render the same domain result.
- [ ] **Step 4: Build four compact synthetic datasets.** Freeze stream hashes, counts, reason summaries, regimes, and result digests in manifests. Replay each twice into fresh memory sinks.
- [ ] **Step 5: Run GREEN:** `.venv/bin/ruff check src/market_trader/scanner tests/scanner && .venv/bin/mypy src/market_trader/scanner tests/scanner && .venv/bin/pytest tests/scanner -q`.
- [ ] **Step 6: Commit:** `git add apps/api/src/market_trader/scanner/cli.py apps/api/tests/scanner apps/api/fixtures/scanner && git commit -m "feat: add scanner CLI and conformance fixtures"`.

---

### Task 16: Operations, Packaging, And Milestone Verification

**Interfaces**

- Consumes: completed scanner, config, fixtures, migration, CLI, persistence.
- Produces: runbook, container smoke coverage, complete verification, roadmap status.

**Files:**

- Create: `docs/milestone-4-scanner-and-scoring.md`
- Modify: `apps/api/Dockerfile`
- Modify: `apps/api/tests/test_container_configuration.py`
- Modify: `scripts/verify-foundation.sh`
- Modify: `docs/development-roadmap.md`

- [ ] **Step 1: Write failing packaging tests.** Assert image copies `/app/config/scanner` and `/app/fixtures/scanner`, remains non-root, and foundation script invokes offline scanner validation without provider URL/credential.
- [ ] **Step 2: Run RED:** `.venv/bin/pytest tests/test_container_configuration.py -q`.
- [ ] **Step 3: Update packaging/smoke.** Run `python -m market_trader.scanner.cli validate /app/fixtures/scanner/bullish` inside the existing non-root API container flow.
- [ ] **Step 4: Write runbook.** Cover macOS/Linux setup, memory validation/scan, SQLite migration/symbol seeding/persistent rerun, DB/audit inspection, policy hash changes, fixture authoring, state interpretation, UTC/XNYS/`America/Chicago`, and no-network/no-Schwab/no-approval/no-order boundaries.
- [ ] **Step 5: Run scanner acceptance:** `.venv/bin/pytest tests/scanner -q`.
- [ ] **Step 6: Run backend gate:** `.venv/bin/ruff check . && .venv/bin/mypy src tests && .venv/bin/pytest --cov=market_trader --cov-report=term-missing --cov-fail-under=90`.
- [ ] **Step 7: Run migration/frontend regressions:** `.venv/bin/alembic upgrade head`, then from `apps/web`, `npm test && npm run build`.
- [ ] **Step 8: Run from repository root:** `docker compose build api web && ./scripts/verify-foundation.sh`.
- [ ] **Step 9: Mark only Milestone 4 complete.** Add completed deliverables and plan/runbook links; set next action to Milestone 5; leave later statuses unchanged.
- [ ] **Step 10: Review and commit:** `git diff --check && git status --short`, then `git add docs/milestone-4-scanner-and-scoring.md docs/development-roadmap.md apps/api/Dockerfile apps/api/tests/test_container_configuration.py scripts/verify-foundation.sh && git commit -m "docs: complete milestone 4 scanner delivery"`.
- [ ] **Step 11: Final review.** Invoke `@superpowers:requesting-code-review`, address findings, rerun all gates, confirm clean status, then invoke `@superpowers:finishing-a-development-branch`.

## Implementation Completion Criteria

- [ ] All 16 tasks and checkboxes are complete in order.
- [ ] Exact approved versions and 30-symbol universe are used.
- [ ] Fixed inputs reproduce regime, decisions, scores, candidates, explanations, keys, and digests.
- [ ] Every member has one eligibility decision; only eligible symbols have five signals; only passing threshold signals have qualified candidates.
- [ ] Missing, stale, conflicting, halted, and unresolved-action inputs fail closed.
- [ ] Duplicate evidence cannot raise a family score or exceed a cap.
- [ ] Persistence is append-only, atomic, referentially valid, and idempotent; identity conflicts roll back.
- [ ] Memory and persistent CLI paths render the same canonical result.
- [ ] Ruff, strict mypy, backend tests/coverage, migrations, frontend tests/build, Docker, and foundation smoke pass.
- [ ] User examples use `America/Chicago`; source timestamps remain UTC and exchange sessions remain XNYS Eastern.
