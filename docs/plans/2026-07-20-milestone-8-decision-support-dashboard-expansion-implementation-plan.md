# Milestone 8 Decision-Support Dashboard Expansion Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use `superpowers:executing-plans` to implement this plan task-by-task. Use `superpowers:test-driven-development` for every behavior change.

**Goal:** Build a read-only decision-support dashboard that exposes market state, candidates, catalysts, options, risk, journal, and analytics without adding approval, broker, preview, execution, or live-mode controls.

**Architecture:** Add backend dashboard read models and FastAPI routes under `/api/dashboard`, backed by existing repositories and bounded DTO assembly. Expand the React app into compact tabbed views with explicit data-state rendering, source timestamps, traceability, error boundaries, and tests proving forbidden controls are absent.

**Tech Stack:** Python 3.12/3.13, FastAPI, Pydantic, SQLAlchemy 2, pytest, Ruff, strict mypy, React 19, TypeScript, Vite, Vitest, Testing Library, Docker Compose.

**Specification:** `docs/plans/2026-07-20-milestone-8-decision-support-dashboard-expansion-spec.md`

## Global Constraints

- Work from a `milestone8` branch or worktree.
- Use TDD: write focused failing tests, observe RED, implement, observe GREEN,
  then commit.
- Dashboard backend code must be read-only and must not mutate records.
- Do not add POST, PUT, PATCH, or DELETE dashboard routes.
- Do not import Schwab, broker preview/order, approval, execution, credential, or
  live-mode code.
- Do not add UI controls that approve, preview, submit, buy, sell, execute,
  connect a broker, clear a lock, or arm live mode.
- Keep all timestamps aware UTC in API contracts and display explicit market-time
  labels in the UI.
- Run backend commands from `apps/api` using `.venv/bin/`.
- Run frontend commands from `apps/web`.

## File Structure

| Path | Responsibility |
| --- | --- |
| `apps/api/src/market_trader/dashboard/models.py` | Pydantic dashboard DTOs and enums. |
| `apps/api/src/market_trader/dashboard/read_models.py` | Read-only assembly services over existing repositories. |
| `apps/api/src/market_trader/api/dashboard.py` | FastAPI dashboard routes. |
| `apps/api/src/market_trader/main.py` | Register dashboard router. |
| `apps/api/tests/dashboard/*` | DTO, read-model, API, safety, and redaction tests. |
| `apps/web/src/api.ts` | Add typed dashboard API contracts and fetchers. |
| `apps/web/src/dashboard/*` | Dashboard components, navigation, panels, formatting, error boundary. |
| `apps/web/src/App.tsx` | Integrate dashboard shell while preserving paper banner. |
| `apps/web/src/index.css` | Extend compact dashboard styling. |
| `apps/web/src/*.test.tsx` and `apps/web/src/dashboard/*.test.tsx` | Frontend behavior and safety tests. |
| `docs/milestone-8-decision-support-dashboard.md` | Operator runbook. |
| `docs/development-roadmap.md` | Mark Milestone 8 complete after verification. |
| `scripts/verify-foundation.sh` | Add dashboard smoke assertions. |

---

### Task 1: Dashboard DTO Contracts

**Files:**
- Create: `apps/api/src/market_trader/dashboard/__init__.py`
- Create: `apps/api/src/market_trader/dashboard/models.py`
- Create: `apps/api/tests/dashboard/__init__.py`
- Create: `apps/api/tests/dashboard/test_models.py`

**Steps:**

- [ ] Write failing tests for `DataState`, source summaries, warning summaries, bounded text, aware UTC timestamps, sorted source order, and secret-like key rejection.
- [ ] Run RED: `.venv/bin/pytest tests/dashboard/test_models.py -q`.
- [ ] Implement Pydantic DTOs for overview, candidate list item, candidate detail, risk summary, journal event summary, analytics summary, source summary, and warning summary.
- [ ] Add tests proving DTOs reject raw payloads containing keys such as `secret`, `token`, `password`, `credential`, and `api_key`.
- [ ] Run GREEN: `.venv/bin/ruff check src/market_trader/dashboard tests/dashboard/test_models.py && .venv/bin/mypy src/market_trader/dashboard tests/dashboard/test_models.py && .venv/bin/pytest tests/dashboard/test_models.py -q`.
- [ ] Commit: `git add apps/api/src/market_trader/dashboard apps/api/tests/dashboard && git commit -m "feat: add dashboard view contracts"`.

### Task 2: Overview Read Model And API

**Files:**
- Create: `apps/api/src/market_trader/dashboard/read_models.py`
- Create: `apps/api/src/market_trader/api/dashboard.py`
- Modify: `apps/api/src/market_trader/main.py`
- Create: `apps/api/tests/dashboard/test_overview_api.py`

**Steps:**

- [ ] Write failing API tests for `GET /api/dashboard/overview`, no-store cache headers, paper-mode visibility, market-state summary, source states, empty database behavior, and no mutation.
- [ ] Run RED: `.venv/bin/pytest tests/dashboard/test_overview_api.py -q`.
- [ ] Implement a read-only overview assembler that combines health-like status, current market state, and latest known source summaries from existing tables where available.
- [ ] Register the dashboard router under `/api/dashboard`.
- [ ] Add tests proving unsupported write methods return 405 or 404.
- [ ] Run GREEN: `.venv/bin/ruff check src/market_trader/dashboard src/market_trader/api/dashboard.py src/market_trader/main.py tests/dashboard/test_overview_api.py && .venv/bin/mypy src/market_trader/dashboard src/market_trader/api/dashboard.py src/market_trader/main.py tests/dashboard/test_overview_api.py && .venv/bin/pytest tests/dashboard/test_overview_api.py -q`.
- [ ] Commit: `git add apps/api/src/market_trader/dashboard apps/api/src/market_trader/api/dashboard.py apps/api/src/market_trader/main.py apps/api/tests/dashboard && git commit -m "feat: expose dashboard overview"`.

### Task 3: Candidate List And Detail APIs

**Files:**
- Modify: `apps/api/src/market_trader/dashboard/read_models.py`
- Modify: `apps/api/src/market_trader/api/dashboard.py`
- Create: `apps/api/tests/dashboard/test_candidates_api.py`

**Steps:**

- [ ] Write failing tests for `GET /api/dashboard/candidates` with limit/cursor handling, sorted candidates, qualified/blocked/stale states, and bounded reason summaries.
- [ ] Write failing tests for `GET /api/dashboard/candidates/{candidate_key}` tracing scanner evidence, catalyst state, options outcome, risk decision, versions, digests, and missing downstream states.
- [ ] Run RED: `.venv/bin/pytest tests/dashboard/test_candidates_api.py -q`.
- [ ] Implement candidate list and detail assemblers using existing scanner, catalyst, options-analysis, and risk persistence records.
- [ ] Add cursor validation and safe empty-state responses.
- [ ] Run GREEN: `.venv/bin/ruff check src/market_trader/dashboard src/market_trader/api/dashboard.py tests/dashboard/test_candidates_api.py && .venv/bin/mypy src/market_trader/dashboard src/market_trader/api/dashboard.py tests/dashboard/test_candidates_api.py && .venv/bin/pytest tests/dashboard/test_candidates_api.py -q`.
- [ ] Commit: `git add apps/api/src/market_trader/dashboard apps/api/src/market_trader/api/dashboard.py apps/api/tests/dashboard/test_candidates_api.py && git commit -m "feat: expose dashboard candidate traces"`.

### Task 4: Risk, Journal, And Analytics APIs

**Files:**
- Modify: `apps/api/src/market_trader/dashboard/read_models.py`
- Modify: `apps/api/src/market_trader/api/dashboard.py`
- Create: `apps/api/tests/dashboard/test_risk_journal_analytics_api.py`

**Steps:**

- [ ] Write failing tests for `GET /api/dashboard/risk` showing latest decisions, checks, locks, reservations, sizing, exposure, tax disclaimer, and stale/unavailable states.
- [ ] Write failing tests for `GET /api/dashboard/journal` with limit/cursor, event type filter, correlation-id filter, redacted bounded payload summaries, and sorted append-only event order.
- [ ] Write failing tests for `GET /api/dashboard/analytics` with candidate counts, strategy mix, block reasons, stale counts, and risk-status distribution.
- [ ] Run RED: `.venv/bin/pytest tests/dashboard/test_risk_journal_analytics_api.py -q`.
- [ ] Implement risk, journal, and analytics assemblers over existing persisted records.
- [ ] Run GREEN: `.venv/bin/ruff check src/market_trader/dashboard src/market_trader/api/dashboard.py tests/dashboard/test_risk_journal_analytics_api.py && .venv/bin/mypy src/market_trader/dashboard src/market_trader/api/dashboard.py tests/dashboard/test_risk_journal_analytics_api.py && .venv/bin/pytest tests/dashboard/test_risk_journal_analytics_api.py -q`.
- [ ] Commit: `git add apps/api/src/market_trader/dashboard apps/api/src/market_trader/api/dashboard.py apps/api/tests/dashboard/test_risk_journal_analytics_api.py && git commit -m "feat: expose dashboard risk and audit summaries"`.

### Task 5: Frontend Dashboard API Client

**Files:**
- Modify: `apps/web/src/api.ts`
- Create: `apps/web/src/dashboard/types.ts`
- Create: `apps/web/src/dashboard/api.test.ts`

**Steps:**

- [ ] Write failing tests for typed dashboard fetchers, no-store requests, API error handling, unavailable response handling, and cursor parameter encoding.
- [ ] Run RED: `npm test -- dashboard/api.test.ts`.
- [ ] Add dashboard TypeScript types and fetch functions for overview, candidates, candidate detail, risk, journal, and analytics.
- [ ] Run GREEN: `npm run lint && npm test -- dashboard/api.test.ts && npm run build`.
- [ ] Commit: `git add apps/web/src/api.ts apps/web/src/dashboard && git commit -m "feat: add dashboard web client contracts"`.

### Task 6: Dashboard Shell, Navigation, And Error Boundaries

**Files:**
- Modify: `apps/web/src/App.tsx`
- Create: `apps/web/src/dashboard/DashboardShell.tsx`
- Create: `apps/web/src/dashboard/DashboardErrorBoundary.tsx`
- Create: `apps/web/src/dashboard/navigation.ts`
- Modify: `apps/web/src/index.css`
- Create: `apps/web/src/dashboard/DashboardShell.test.tsx`

**Steps:**

- [ ] Write failing tests for persistent paper banner, tab navigation, accessible labels, panel-level error fallback, mobile-safe landmarks, and forbidden-control absence.
- [ ] Run RED: `npm test -- DashboardShell.test.tsx`.
- [ ] Implement the dashboard shell with overview, scanner, candidate detail, risk, journal, and analytics tabs backed by local state.
- [ ] Extend CSS with compact dashboard layout, stable grid dimensions, status colors, and 320px responsive behavior.
- [ ] Run GREEN: `npm run lint && npm test -- DashboardShell.test.tsx && npm run build`.
- [ ] Commit: `git add apps/web/src/App.tsx apps/web/src/index.css apps/web/src/dashboard && git commit -m "feat: add read-only dashboard shell"`.

### Task 7: Overview And Scanner Views

**Files:**
- Create: `apps/web/src/dashboard/OverviewPanel.tsx`
- Create: `apps/web/src/dashboard/ScannerPanel.tsx`
- Create: `apps/web/src/dashboard/formatting.ts`
- Create: `apps/web/src/dashboard/OverviewPanel.test.tsx`
- Create: `apps/web/src/dashboard/ScannerPanel.test.tsx`

**Steps:**

- [ ] Write failing tests for overview source states, market timestamps, stale/unavailable display, candidate rows, local display filters, score components, and no action controls.
- [ ] Run RED: `npm test -- OverviewPanel.test.tsx ScannerPanel.test.tsx`.
- [ ] Implement overview and scanner panels using dashboard API data and existing market-time formatting patterns.
- [ ] Add loading, partial, stale, and unavailable states for each panel.
- [ ] Run GREEN: `npm run lint && npm test -- OverviewPanel.test.tsx ScannerPanel.test.tsx && npm run build`.
- [ ] Commit: `git add apps/web/src/dashboard && git commit -m "feat: render dashboard overview and scanner views"`.

### Task 8: Candidate Detail, Risk, Journal, And Analytics Views

**Files:**
- Create: `apps/web/src/dashboard/CandidateDetailPanel.tsx`
- Create: `apps/web/src/dashboard/RiskPanel.tsx`
- Create: `apps/web/src/dashboard/JournalPanel.tsx`
- Create: `apps/web/src/dashboard/AnalyticsPanel.tsx`
- Create: `apps/web/src/dashboard/CandidateDetailPanel.test.tsx`
- Create: `apps/web/src/dashboard/RiskPanel.test.tsx`
- Create: `apps/web/src/dashboard/JournalPanel.test.tsx`
- Create: `apps/web/src/dashboard/AnalyticsPanel.test.tsx`

**Steps:**

- [ ] Write failing tests for candidate trace sections, source keys, policy versions, risk checks, lock display, tax disclaimer, journal redaction, analytics summaries, and forbidden-control absence.
- [ ] Run RED: `npm test -- CandidateDetailPanel.test.tsx RiskPanel.test.tsx JournalPanel.test.tsx AnalyticsPanel.test.tsx`.
- [ ] Implement candidate detail, risk, journal, and analytics panels.
- [ ] Add empty-state and unavailable-state handling for missing downstream records.
- [ ] Run GREEN: `npm run lint && npm test -- CandidateDetailPanel.test.tsx RiskPanel.test.tsx JournalPanel.test.tsx AnalyticsPanel.test.tsx && npm run build`.
- [ ] Commit: `git add apps/web/src/dashboard && git commit -m "feat: render dashboard detail and audit views"`.

### Task 9: Dashboard Safety, Accessibility, And Smoke Coverage

**Files:**
- Create: `apps/api/tests/dashboard/test_safety.py`
- Create: `apps/web/src/dashboard/safety.test.tsx`
- Modify: `scripts/verify-foundation.sh`

**Steps:**

- [ ] Write failing backend safety tests proving dashboard routes expose no write methods, no forbidden action fields, no secret-like payload keys, and no order-shaped DTOs.
- [ ] Write failing frontend safety tests scanning rendered dashboard text/roles for forbidden approval, broker, order, and live-mode controls.
- [ ] Add smoke checks for `/api/dashboard/overview` and the dashboard root render to `scripts/verify-foundation.sh`.
- [ ] Run RED: `.venv/bin/pytest tests/dashboard/test_safety.py -q` and `npm test -- safety.test.tsx`.
- [ ] Implement any missing safety guards or redaction needed to pass.
- [ ] Run GREEN from `apps/api`: `.venv/bin/ruff check src/market_trader/dashboard src/market_trader/api/dashboard.py tests/dashboard && .venv/bin/mypy src/market_trader/dashboard src/market_trader/api/dashboard.py tests/dashboard && .venv/bin/pytest tests/dashboard -q`.
- [ ] Run GREEN from `apps/web`: `npm run lint && npm test -- dashboard && npm run build`.
- [ ] Commit: `git add apps/api/src/market_trader/dashboard apps/api/src/market_trader/api/dashboard.py apps/api/tests/dashboard apps/web/src scripts/verify-foundation.sh && git commit -m "test: verify dashboard safety gates"`.

### Task 10: Runbook, Roadmap, And Full Verification

**Files:**
- Create: `docs/milestone-8-decision-support-dashboard.md`
- Modify: `docs/development-roadmap.md`

**Steps:**

- [ ] Write the runbook with local startup, dashboard views, data-state meanings, stale/unavailable behavior, safety boundaries, fixture expectations, and explicit non-capabilities.
- [ ] Update the roadmap Milestone 8 status to Complete and next planning action to Milestone 9.
- [ ] Run full backend gates from `apps/api`: `.venv/bin/ruff check src tests scripts`, `.venv/bin/mypy src tests scripts`, `.venv/bin/pytest -q`.
- [ ] Run frontend gates from `apps/web`: `npm run lint`, `npm test`, `npm run build`.
- [ ] Run Alembic SQLite head upgrade.
- [ ] Run Docker compose build/start and `./scripts/verify-foundation.sh`; stop compose after verification.
- [ ] Commit: `git add docs && git commit -m "docs: complete dashboard milestone"`.

## Completion Criteria

Milestone 8 is complete only when every task has passed its verification command,
the runbook is written, the roadmap points to Milestone 9 as the next planning
action, and the dashboard remains provably read-only with no approval, broker,
order, or live-mode controls.
