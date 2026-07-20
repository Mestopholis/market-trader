# Milestone 7 Risk, Sizing, Exposure, And Tax Warnings Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:executing-plans` to implement this plan task-by-task. Use `superpowers:test-driven-development` for every behavior change.

**Goal:** Build deterministic, auditable risk decisions and sizing checks without adding broker account access, approvals, previews, or orders.

**Architecture:** Add a pure `risk` domain with immutable inputs, policy loading, sizing, exposure checks, lock evaluation, tax warnings, and deterministic decision digests. Persistence is optional and append-only through repositories; fixtures and CLI use the same domain path offline.

**Tech Stack:** Python 3.12/3.13, dataclasses, `Decimal`, SQLAlchemy 2, Alembic, pytest, Ruff, strict mypy, SQLite/PostgreSQL-compatible models, Docker Compose.

**Specification:** `docs/plans/2026-07-20-milestone-7-risk-sizing-exposure-and-tax-warnings-spec.md`

## Global Constraints

- Work from the `milestone7` branch in `.worktrees/milestone7`.
- Use TDD: write a focused failing test, observe RED, implement, observe GREEN, then commit.
- Domain modules must not import SQLAlchemy, HTTP clients, environment settings,
  Schwab, broker preview/order, UI, or wall-clock helpers.
- Use aware UTC timestamps, XNYS sessions, `Decimal`, stable digests, and sorted records.
- Do not implement broker balances, margin, broker previews, approvals, orders,
  live trading, or tax advice.
- Run backend commands from `apps/api` using `.venv/bin/`.
- Run strict mypy on all new or modified Milestone 7 files.

## File Structure

| Path | Responsibility |
| --- | --- |
| `apps/api/src/market_trader/risk/models.py` | Immutable risk inputs, proposals, checks, sizing results, decisions, enums. |
| `apps/api/src/market_trader/risk/serialization.py` | Canonical records, stable keys, SHA-256 digests. |
| `apps/api/src/market_trader/risk/configuration.py` | Strict risk-policy loading and hash validation. |
| `apps/api/config/risk/risk-policy-v1.json` | Version-one risk rules. |
| `apps/api/src/market_trader/risk/sizing.py` | Share and debit-spread integer sizing. |
| `apps/api/src/market_trader/risk/exposure.py` | Buying-power, reserved-risk, portfolio, correlation, drawdown checks. |
| `apps/api/src/market_trader/risk/locks.py` | Active risk-lock evaluation. |
| `apps/api/src/market_trader/risk/tax.py` | Wash-sale and holding-period warnings. |
| `apps/api/src/market_trader/risk/engine.py` | Combines checks into final deterministic risk decisions. |
| `apps/api/migrations/versions/20260720_0006_risk_decisions.py` | Append-only risk decision schema. |
| `apps/api/src/market_trader/repositories/risk_decisions.py` | Atomic idempotent decision persistence and audit events. |
| `apps/api/src/market_trader/risk/fixtures.py` | Strict fixture loading. |
| `apps/api/src/market_trader/risk/replay.py` | Deterministic fixture replay. |
| `apps/api/src/market_trader/risk/cli.py` | Offline `validate` and `evaluate` commands. |
| `apps/api/scripts/generate_risk_fixtures.py` | Deterministic fixture generator. |
| `apps/api/fixtures/risk/*` | Synthetic production fixtures. |
| `apps/api/tests/risk/*` | Unit, persistence, CLI, fixture, and conformance tests. |

---

### Task 1: Risk Domain Contracts And Serialization

**Files:**
- Create: `apps/api/src/market_trader/risk/__init__.py`
- Create: `apps/api/src/market_trader/risk/models.py`
- Create: `apps/api/src/market_trader/risk/serialization.py`
- Create: `apps/api/tests/risk/__init__.py`
- Create: `apps/api/tests/risk/test_models.py`
- Create: `apps/api/tests/risk/test_serialization.py`

**Steps:**

- [ ] Write failing tests for immutable dataclasses, UTC enforcement, finite decimals, sorted checks, valid severities/states, and stable digests independent of input order.
- [ ] Run RED: `.venv/bin/pytest tests/risk/test_models.py tests/risk/test_serialization.py -q`.
- [ ] Implement enums `RiskDecisionStatus`, `RiskCheckSeverity`, `RiskCheckState`, `ProposalKind`, immutable proposal/input/check/result dataclasses, `canonical_record`, `stable_digest`, and `stable_key`.
- [ ] Add tests proving display-only explanation fields are excluded from identity while prices, quantities, and policy hashes change digests.
- [ ] Run GREEN: `.venv/bin/ruff check src/market_trader/risk tests/risk && .venv/bin/mypy src/market_trader/risk tests/risk && .venv/bin/pytest tests/risk/test_models.py tests/risk/test_serialization.py -q`.
- [ ] Commit: `git add apps/api/src/market_trader/risk apps/api/tests/risk && git commit -m "feat: add risk decision domain contracts"`.

### Task 2: Versioned Risk Policy

**Files:**
- Create: `apps/api/config/risk/risk-policy-v1.json`
- Create: `apps/api/src/market_trader/risk/configuration.py`
- Create: `apps/api/tests/risk/test_configuration.py`

**Steps:**

- [ ] Write failing tests for strict keys, string decimals, content hash validation, positive limits, non-overlapping windows, required lock types, tax disclaimer, and unsupported-version rejection.
- [ ] Run RED: `.venv/bin/pytest tests/risk/test_configuration.py -q`.
- [ ] Implement `RiskPolicy` and `load_risk_policy(path)`.
- [ ] Run GREEN: `.venv/bin/ruff check src/market_trader/risk/configuration.py tests/risk/test_configuration.py && .venv/bin/mypy src/market_trader/risk/configuration.py tests/risk/test_configuration.py && .venv/bin/pytest tests/risk/test_configuration.py -q`.
- [ ] Commit: `git add apps/api/config/risk apps/api/src/market_trader/risk/configuration.py apps/api/tests/risk/test_configuration.py && git commit -m "feat: add risk policy"`.

### Task 3: Share And Debit-Spread Sizing

**Files:**
- Create: `apps/api/src/market_trader/risk/sizing.py`
- Create: `apps/api/tests/risk/test_sizing.py`

**Steps:**

- [ ] Write failing tests for share sizing, spread sizing, zero quantity rejection, one-contract boundary, per-trade risk ceilings, cash ceilings, round-down behavior, and assignment stress.
- [ ] Run RED: `.venv/bin/pytest tests/risk/test_sizing.py -q`.
- [ ] Implement `size_proposal(input, policy) -> SizingResult`.
- [ ] Add tests proving sizing never rounds up and all calculations use `Decimal`.
- [ ] Run GREEN: `.venv/bin/ruff check src/market_trader/risk/sizing.py tests/risk/test_sizing.py && .venv/bin/mypy src/market_trader/risk/sizing.py tests/risk/test_sizing.py && .venv/bin/pytest tests/risk/test_sizing.py -q`.
- [ ] Commit: `git add apps/api/src/market_trader/risk/sizing.py apps/api/tests/risk/test_sizing.py && git commit -m "feat: size risk proposals"`.

### Task 4: Exposure, Buying Power, And Limits

**Files:**
- Create: `apps/api/src/market_trader/risk/exposure.py`
- Create: `apps/api/tests/risk/test_exposure.py`

**Steps:**

- [ ] Write failing tests for settled cash, unsettled cash policy, borrowed-buying-power exclusion, existing reservations, working orders, aggregate exposure, daily/weekly loss, position count, trade count, correlation groups, and drawdown.
- [ ] Run RED: `.venv/bin/pytest tests/risk/test_exposure.py -q`.
- [ ] Implement `evaluate_exposure(input, sizing, policy) -> tuple[RiskCheck, ...]`.
- [ ] Add boundary tests for exactly-at-limit accepted and one-cent/one-count-over blocked.
- [ ] Run GREEN: `.venv/bin/ruff check src/market_trader/risk/exposure.py tests/risk/test_exposure.py && .venv/bin/mypy src/market_trader/risk/exposure.py tests/risk/test_exposure.py && .venv/bin/pytest tests/risk/test_exposure.py -q`.
- [ ] Commit: `git add apps/api/src/market_trader/risk/exposure.py apps/api/tests/risk/test_exposure.py && git commit -m "feat: evaluate risk exposure limits"`.

### Task 5: Lock Evaluation

**Files:**
- Create: `apps/api/src/market_trader/risk/locks.py`
- Create: `apps/api/tests/risk/test_locks.py`

**Steps:**

- [ ] Write failing tests for all required active lock types, cleared locks ignored, policy informational locks, stable facts, and sorted output.
- [ ] Run RED: `.venv/bin/pytest tests/risk/test_locks.py -q`.
- [ ] Implement `evaluate_locks(input, policy) -> tuple[RiskCheck, ...]`.
- [ ] Run GREEN: `.venv/bin/ruff check src/market_trader/risk/locks.py tests/risk/test_locks.py && .venv/bin/mypy src/market_trader/risk/locks.py tests/risk/test_locks.py && .venv/bin/pytest tests/risk/test_locks.py -q`.
- [ ] Commit: `git add apps/api/src/market_trader/risk/locks.py apps/api/tests/risk/test_locks.py && git commit -m "feat: evaluate active risk locks"`.

### Task 6: Tax Warnings

**Files:**
- Create: `apps/api/src/market_trader/risk/tax.py`
- Create: `apps/api/tests/risk/test_tax.py`

**Steps:**

- [ ] Write failing tests for wash-sale window boundaries, equivalent-symbol groups, short-term and long-term holding-period warnings, taxable-account-only behavior, and non-advice disclaimer inclusion.
- [ ] Run RED: `.venv/bin/pytest tests/risk/test_tax.py -q`.
- [ ] Implement `evaluate_tax_warnings(input, policy) -> tuple[RiskCheck, ...]`.
- [ ] Run GREEN: `.venv/bin/ruff check src/market_trader/risk/tax.py tests/risk/test_tax.py && .venv/bin/mypy src/market_trader/risk/tax.py tests/risk/test_tax.py && .venv/bin/pytest tests/risk/test_tax.py -q`.
- [ ] Commit: `git add apps/api/src/market_trader/risk/tax.py apps/api/tests/risk/test_tax.py && git commit -m "feat: add tax risk warnings"`.

### Task 7: Risk Engine

**Files:**
- Create: `apps/api/src/market_trader/risk/engine.py`
- Create: `apps/api/tests/risk/test_engine.py`

**Steps:**

- [ ] Write failing tests that combine sizing, exposure, locks, and tax warnings into `approved`, `warning`, and `blocked` decisions with stable result digests.
- [ ] Run RED: `.venv/bin/pytest tests/risk/test_engine.py -q`.
- [ ] Implement `RiskEngine.evaluate(input, policy) -> RiskDecision`.
- [ ] Add tests proving deterministic ordering, reason summaries, and no order-shaped payloads.
- [ ] Run GREEN: `.venv/bin/ruff check src/market_trader/risk/engine.py tests/risk/test_engine.py && .venv/bin/mypy src/market_trader/risk/engine.py tests/risk/test_engine.py && .venv/bin/pytest tests/risk/test_engine.py -q`.
- [ ] Commit: `git add apps/api/src/market_trader/risk/engine.py apps/api/tests/risk/test_engine.py && git commit -m "feat: evaluate risk decisions"`.

### Task 8: Append-Only Risk Persistence

**Files:**
- Modify: `apps/api/src/market_trader/db/models.py`
- Create: `apps/api/migrations/versions/20260720_0006_risk_decisions.py`
- Create: `apps/api/src/market_trader/repositories/risk_decisions.py`
- Modify: `apps/api/src/market_trader/repositories/__init__.py`
- Create: `apps/api/tests/risk/test_schema.py`
- Create: `apps/api/tests/risk/test_repository.py`

**Steps:**

- [ ] Write failing schema tests for `risk_decisions`, `risk_checks`, `risk_reservations`, stable unique keys, JSONB/GIN payloads, foreign keys, and SQLite append-only triggers.
- [ ] Write failing repository tests for atomic persist, exact rerun idempotence, digest conflict, child rollback, and audit events.
- [ ] Run RED: `.venv/bin/pytest tests/risk/test_schema.py tests/risk/test_repository.py -q`.
- [ ] Implement ORM models, Alembic migration, repository, persisted DTO, and audit events.
- [ ] Run GREEN: `.venv/bin/ruff check src/market_trader/db/models.py src/market_trader/repositories/risk_decisions.py src/market_trader/repositories/__init__.py tests/risk/test_schema.py tests/risk/test_repository.py && .venv/bin/mypy src/market_trader/db/models.py src/market_trader/repositories/risk_decisions.py src/market_trader/repositories/__init__.py tests/risk/test_schema.py tests/risk/test_repository.py && .venv/bin/pytest tests/risk/test_schema.py tests/risk/test_repository.py -q`.
- [ ] Commit: `git add apps/api/src/market_trader/db/models.py apps/api/migrations/versions/20260720_0006_risk_decisions.py apps/api/src/market_trader/repositories apps/api/tests/risk/test_schema.py apps/api/tests/risk/test_repository.py && git commit -m "feat: persist risk decisions"`.

### Task 9: Fixtures, Replay, And CLI

**Files:**
- Create: `apps/api/src/market_trader/risk/fixtures.py`
- Create: `apps/api/src/market_trader/risk/replay.py`
- Create: `apps/api/src/market_trader/risk/cli.py`
- Create: `apps/api/scripts/generate_risk_fixtures.py`
- Create: `apps/api/fixtures/risk/*`
- Create: `apps/api/tests/risk/test_fixtures.py`
- Create: `apps/api/tests/risk/test_replay.py`
- Create: `apps/api/tests/risk/test_cli.py`
- Create: `apps/api/tests/risk/test_fixture_conformance.py`

**Steps:**

- [ ] Write failing tests for strict fixture loading, hash validation, sensitive-key rejection, deterministic replay, CLI output, and four production fixture groups.
- [ ] Run RED: `.venv/bin/pytest tests/risk/test_fixtures.py tests/risk/test_replay.py tests/risk/test_cli.py tests/risk/test_fixture_conformance.py -q`.
- [ ] Implement loader, replay, CLI `validate/evaluate`, and deterministic fixture generator.
- [ ] Generate fixtures.
- [ ] Run GREEN: `.venv/bin/ruff check src/market_trader/risk scripts/generate_risk_fixtures.py tests/risk && .venv/bin/mypy src/market_trader/risk scripts/generate_risk_fixtures.py tests/risk && .venv/bin/pytest tests/risk -q`.
- [ ] Commit: `git add apps/api/src/market_trader/risk apps/api/scripts/generate_risk_fixtures.py apps/api/fixtures/risk apps/api/tests/risk && git commit -m "test: add risk fixture conformance"`.

### Task 10: Runbook, Roadmap, Smoke, And Full Verification

**Files:**
- Create: `docs/milestone-7-risk-sizing-exposure-and-tax-warnings.md`
- Modify: `docs/development-roadmap.md`
- Modify: `scripts/verify-foundation.sh`

**Steps:**

- [ ] Write the runbook with local setup, offline validation, evaluation, persistence notes, lock meanings, tax-warning disclaimer, fixture regeneration, and explicit non-capabilities.
- [ ] Update roadmap Milestone 7 status to Complete and next planning action to Milestone 8.
- [ ] Add risk fixture validation to `scripts/verify-foundation.sh`.
- [ ] Run full backend gates: `.venv/bin/ruff check src tests scripts`, `.venv/bin/mypy src tests scripts`, `.venv/bin/pytest -q`.
- [ ] Run frontend gates from `apps/web`: `npm run lint`, `npm test`, `npm run build`.
- [ ] Run Alembic SQLite head upgrade.
- [ ] Run Docker compose build/start and `./scripts/verify-foundation.sh`; stop compose after verification.
- [ ] Commit: `git add docs scripts/verify-foundation.sh && git commit -m "docs: complete risk milestone"`.
