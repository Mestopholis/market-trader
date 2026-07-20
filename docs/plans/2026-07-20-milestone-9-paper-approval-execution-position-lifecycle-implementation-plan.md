# Milestone 9 Paper Approval, Execution, And Position Lifecycle Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use `superpowers:executing-plans` to implement this plan task-by-task. Use `superpowers:test-driven-development` for every behavior change.

**Goal:** Build a deterministic paper approval, execution, and position lifecycle for risk-approved candidates without adding Schwab, broker, credential, or live-mode capability.

**Architecture:** Add a pure paper lifecycle domain above the existing trade lifecycle repository tables. FastAPI paper routes orchestrate approval cards, previews, simulated broker submission, order transitions, fills, positions, and recovery while preserving audit events. React adds paper lifecycle views that clearly label every action as paper-only.

**Tech Stack:** Python 3.12/3.13, FastAPI, Pydantic, SQLAlchemy 2, Alembic, pytest, Ruff, strict mypy, React 19, TypeScript, Vite, Vitest, Testing Library, Docker Compose.

**Specification:** `docs/plans/2026-07-20-milestone-9-paper-approval-execution-position-lifecycle-spec.md`

## Global Constraints

- Work from a `milestone9` branch or worktree based on merged Milestone 8 `main`.
- Use TDD for every behavior change: RED, GREEN, refactor, commit.
- Approval cards are generated only from persisted risk-approved or risk-warning candidate outputs.
- Do not add manual trade entry.
- Do not add Schwab OAuth, Schwab clients, broker credentials, broker account reads, broker previews, broker order IDs, live-mode arming, or live order submission.
- Only simulated references may be persisted; external `broker_reference` fields remain `None`.
- Only limit orders are accepted.
- Keep timestamps aware UTC in backend contracts and display explicit market-time labels in the UI.
- Run backend commands from `apps/api` using `.venv/bin/`.
- Run frontend commands from `apps/web`.

## File Structure

| Path | Responsibility |
| --- | --- |
| `apps/api/src/market_trader/paper/models.py` | Pure paper lifecycle DTO/domain contracts. |
| `apps/api/src/market_trader/paper/eligibility.py` | Approval-card eligibility from candidate/options/risk records. |
| `apps/api/src/market_trader/paper/broker.py` | Deterministic paper broker scenarios. |
| `apps/api/src/market_trader/paper/service.py` | Approval, preview, submit, cancel, replace, recovery orchestration. |
| `apps/api/src/market_trader/api/paper.py` | FastAPI paper lifecycle routes. |
| `apps/api/src/market_trader/repositories/orders.py` | Extend existing lifecycle repository with query/update helpers. |
| `apps/api/migrations/versions/*_paper_lifecycle.py` | Add indexes/status metadata only if existing tables are insufficient. |
| `apps/api/tests/paper/*` | Paper domain, broker, service, API, recovery, and safety tests. |
| `apps/web/src/paper/*` | Paper lifecycle API types and React views. |
| `apps/web/src/dashboard/navigation.ts` | Add paper lifecycle navigation if integrated as dashboard tabs. |
| `apps/web/src/api.ts` | Add typed paper lifecycle fetchers. |
| `apps/web/src/index.css` | Compact paper lifecycle UI styles. |
| `docs/milestone-9-paper-approval-execution-position-lifecycle.md` | Operator runbook. |
| `docs/development-roadmap.md` | Mark Milestone 9 complete after verification. |
| `scripts/verify-foundation.sh` | Add safe paper lifecycle smoke checks. |

---

### Task 1: Paper Lifecycle Contracts

**Files:**
- Create: `apps/api/src/market_trader/paper/__init__.py`
- Create: `apps/api/src/market_trader/paper/models.py`
- Create: `apps/api/tests/paper/__init__.py`
- Create: `apps/api/tests/paper/test_models.py`

**Steps:**

- [ ] Write failing tests for `ApprovalCard`, `PaperOrderIntent`, `PaperPreview`, `PaperBrokerOrder`, `PaperPosition`, and `LifecycleEvent`.
- [ ] Include tests that reject market orders, live-mode flags, Schwab/broker credential keys, non-UTC timestamps, non-finite prices, negative quantities, and unbounded raw payload fields.
- [ ] Run RED: `.venv/bin/pytest tests/paper/test_models.py -q`.
- [ ] Implement enums and Pydantic/dataclass contracts for paper lifecycle state:
  `ApprovalCardState`, `PaperOrderStatus`, `PaperPositionStatus`,
  `PaperOrderType`, `PaperAction`, `PaperBrokerScenario`.
- [ ] Implement bounded validation helpers for source keys, digests, timestamps, prices, quantities, and payload redaction.
- [ ] Run GREEN: `.venv/bin/ruff check src/market_trader/paper tests/paper/test_models.py && .venv/bin/mypy src/market_trader/paper tests/paper/test_models.py && .venv/bin/pytest tests/paper/test_models.py -q`.
- [ ] Commit: `git add apps/api/src/market_trader/paper apps/api/tests/paper && git commit -m "feat: add paper lifecycle contracts"`.

### Task 2: Approval Card Eligibility

**Files:**
- Create: `apps/api/src/market_trader/paper/eligibility.py`
- Create: `apps/api/tests/paper/test_eligibility.py`

**Steps:**

- [ ] Write failing tests for approval card generation from persisted candidates with risk decisions in `approved` and `warning` states.
- [ ] Add tests that blocked risk decisions, stale source digests, zero quantity, missing candidate lineage, missing options records for spread proposals, and active required locks produce no approval card.
- [ ] Run RED: `.venv/bin/pytest tests/paper/test_eligibility.py -q`.
- [ ] Implement read-only eligibility assembly over existing candidate, options-analysis, risk-decision, risk-lock, and symbol records.
- [ ] Ensure approval cards include candidate key, symbol, direction, proposal kind, quantity, max loss, risk decision key, input/result digests, source keys, expiration, and allowed actions.
- [ ] Run GREEN: `.venv/bin/ruff check src/market_trader/paper tests/paper/test_eligibility.py && .venv/bin/mypy src/market_trader/paper tests/paper/test_eligibility.py && .venv/bin/pytest tests/paper/test_eligibility.py -q`.
- [ ] Commit: `git add apps/api/src/market_trader/paper apps/api/tests/paper/test_eligibility.py && git commit -m "feat: assemble paper approval cards"`.

### Task 3: Trade Lifecycle Repository Extensions

**Files:**
- Modify: `apps/api/src/market_trader/repositories/orders.py`
- Create: `apps/api/tests/paper/test_lifecycle_repository.py`

**Steps:**

- [ ] Write failing repository tests for creating proposed trades from approval cards, updating approval status, creating paper orders, updating order status, recording fills, updating positions, listing open orders, listing open positions, and preserving audit events.
- [ ] Add tests proving external `broker_reference` remains `None` and only `simulated_broker_reference` is set.
- [ ] Run RED: `.venv/bin/pytest tests/paper/test_lifecycle_repository.py -q`.
- [ ] Add explicit query and update helpers to `TradeLifecycleRepository`; do not bypass existing audit conventions.
- [ ] Add typed conflict errors for invalid state transitions and digest mismatch.
- [ ] Run GREEN: `.venv/bin/ruff check src/market_trader/repositories/orders.py tests/paper/test_lifecycle_repository.py && .venv/bin/mypy src/market_trader/repositories/orders.py tests/paper/test_lifecycle_repository.py && .venv/bin/pytest tests/paper/test_lifecycle_repository.py -q`.
- [ ] Commit: `git add apps/api/src/market_trader/repositories/orders.py apps/api/tests/paper/test_lifecycle_repository.py && git commit -m "feat: extend paper lifecycle persistence"`.

### Task 4: Deterministic Paper Broker

**Files:**
- Create: `apps/api/src/market_trader/paper/broker.py`
- Create: `apps/api/tests/paper/test_broker.py`

**Steps:**

- [ ] Write failing tests for scenarios: `accepted_unfilled`, `full_fill`, `partial_fill`, `reject`, `cancel`, `cancel_replace`, `timeout`, and `assignment`.
- [ ] Add tests proving no randomness, no network imports, stable simulated references, deterministic fill prices, and bounded reason codes.
- [ ] Run RED: `.venv/bin/pytest tests/paper/test_broker.py -q`.
- [ ] Implement the broker as a pure deterministic state machine over `PaperOrderIntent`, `PaperPreview`, scenario, and clock input.
- [ ] Ensure all generated lifecycle events carry source order id, simulated reference, correlation id, and aware UTC timestamps.
- [ ] Run GREEN: `.venv/bin/ruff check src/market_trader/paper tests/paper/test_broker.py && .venv/bin/mypy src/market_trader/paper tests/paper/test_broker.py && .venv/bin/pytest tests/paper/test_broker.py -q`.
- [ ] Commit: `git add apps/api/src/market_trader/paper/broker.py apps/api/tests/paper/test_broker.py && git commit -m "feat: add deterministic paper broker"`.

### Task 5: Paper Lifecycle Service

**Files:**
- Create: `apps/api/src/market_trader/paper/service.py`
- Create: `apps/api/tests/paper/test_service.py`

**Steps:**

- [ ] Write failing service tests for approve, modify, reject, preview, submit, cancel, replace, and recovery workflows.
- [ ] Include blocking tests for expired approval, stale preview, changed risk digest, closed entry window, active required lock, non-limit order, and missing source records.
- [ ] Run RED: `.venv/bin/pytest tests/paper/test_service.py -q`.
- [ ] Implement `PaperLifecycleService` using eligibility, existing repositories, market-state service, deterministic quote fixtures, and paper broker.
- [ ] Ensure each write creates journal/audit events with correlation ids and no external broker references.
- [ ] Run GREEN: `.venv/bin/ruff check src/market_trader/paper src/market_trader/repositories/orders.py tests/paper/test_service.py && .venv/bin/mypy src/market_trader/paper src/market_trader/repositories/orders.py tests/paper/test_service.py && .venv/bin/pytest tests/paper/test_service.py -q`.
- [ ] Commit: `git add apps/api/src/market_trader/paper apps/api/tests/paper/test_service.py && git commit -m "feat: orchestrate paper lifecycle service"`.

### Task 6: Paper API Routes

**Files:**
- Create: `apps/api/src/market_trader/api/paper.py`
- Modify: `apps/api/src/market_trader/main.py`
- Create: `apps/api/tests/paper/test_api.py`

**Steps:**

- [ ] Write failing API tests for:
  `GET /api/paper/approval-cards`,
  `POST /api/paper/approval-cards/{card_key}/approve`,
  `POST /api/paper/approval-cards/{card_key}/modify`,
  `POST /api/paper/approval-cards/{card_key}/reject`,
  `POST /api/paper/approvals/{approval_id}/preview`,
  `POST /api/paper/approvals/{approval_id}/submit`,
  `POST /api/paper/orders/{order_id}/cancel`,
  `POST /api/paper/orders/{order_id}/replace`,
  `GET /api/paper/orders`,
  `GET /api/paper/positions`,
  and `POST /api/paper/recover`.
- [ ] Add tests for paper-mode response fields, validation errors, no-store headers, and forbidden live/broker payloads.
- [ ] Run RED: `.venv/bin/pytest tests/paper/test_api.py -q`.
- [ ] Implement FastAPI route DTOs and service wiring under `/api/paper`.
- [ ] Register the paper router in `main.py`.
- [ ] Run GREEN: `.venv/bin/ruff check src/market_trader/paper src/market_trader/api/paper.py src/market_trader/main.py tests/paper/test_api.py && .venv/bin/mypy src/market_trader/paper src/market_trader/api/paper.py src/market_trader/main.py tests/paper/test_api.py && .venv/bin/pytest tests/paper/test_api.py -q`.
- [ ] Commit: `git add apps/api/src/market_trader/paper apps/api/src/market_trader/api/paper.py apps/api/src/market_trader/main.py apps/api/tests/paper/test_api.py && git commit -m "feat: expose paper lifecycle api"`.

### Task 7: Paper API Safety And Recovery Tests

**Files:**
- Create: `apps/api/tests/paper/test_safety.py`
- Create: `apps/api/tests/paper/test_recovery.py`

**Steps:**

- [ ] Write failing safety tests proving no Schwab, broker credential, live-mode, market-order, or external broker reference appears in paper API OpenAPI contracts or persisted lifecycle records.
- [ ] Write failing recovery tests proving restart recovery lists and prioritizes open approvals, working orders, timed-out requests, and open positions.
- [ ] Run RED: `.venv/bin/pytest tests/paper/test_safety.py tests/paper/test_recovery.py -q`.
- [ ] Implement missing guards, recovery read models, and redaction needed to pass.
- [ ] Run GREEN: `.venv/bin/ruff check src/market_trader/paper src/market_trader/api/paper.py tests/paper && .venv/bin/mypy src/market_trader/paper src/market_trader/api/paper.py tests/paper && .venv/bin/pytest tests/paper -q`.
- [ ] Commit: `git add apps/api/src/market_trader/paper apps/api/src/market_trader/api/paper.py apps/api/tests/paper && git commit -m "test: verify paper lifecycle safety and recovery"`.

### Task 8: Frontend Paper API Client

**Files:**
- Modify: `apps/web/src/api.ts`
- Create: `apps/web/src/paper/types.ts`
- Create: `apps/web/src/paper/api.test.ts`

**Steps:**

- [ ] Write failing tests for typed fetchers for approval cards, approve, modify, reject, preview, submit, cancel, replace, orders, positions, and recovery.
- [ ] Add tests for no-store requests, API error handling, paper-mode fields, and payload encoding.
- [ ] Run RED: `npm test -- src/paper/api.test.ts`.
- [ ] Implement TypeScript paper lifecycle contracts and fetchers.
- [ ] Run GREEN: `npm run lint && npm test -- src/paper/api.test.ts && npm run build`.
- [ ] Commit: `git add apps/web/src/api.ts apps/web/src/paper && git commit -m "feat: add paper lifecycle web client"`.

### Task 9: Approval Queue And Card Detail UI

**Files:**
- Create: `apps/web/src/paper/ApprovalQueue.tsx`
- Create: `apps/web/src/paper/ApprovalCardDetail.tsx`
- Create: `apps/web/src/paper/ApprovalQueue.test.tsx`
- Create: `apps/web/src/paper/ApprovalCardDetail.test.tsx`
- Modify: `apps/web/src/dashboard/navigation.ts`
- Modify: `apps/web/src/dashboard/DashboardShell.tsx`
- Modify: `apps/web/src/index.css`

**Steps:**

- [ ] Write failing tests for approval-card list rendering, source trace display, expiration display, paper-only action labels, empty state, unavailable state, and no manual trade-entry controls.
- [ ] Run RED: `npm test -- src/paper/ApprovalQueue.test.tsx src/paper/ApprovalCardDetail.test.tsx`.
- [ ] Implement approval queue and card detail panels.
- [ ] Add navigation entry labeled `Paper Approvals` or equivalent.
- [ ] Add compact responsive CSS for approval cards without nested cards.
- [ ] Run GREEN: `npm run lint && npm test -- src/paper/ApprovalQueue.test.tsx src/paper/ApprovalCardDetail.test.tsx && npm run build`.
- [ ] Commit: `git add apps/web/src/paper apps/web/src/dashboard apps/web/src/index.css && git commit -m "feat: render paper approval queue"`.

### Task 10: Preview, Submit, Modify, And Reject UI

**Files:**
- Create: `apps/web/src/paper/PaperActionPanel.tsx`
- Create: `apps/web/src/paper/PaperPreviewPanel.tsx`
- Create: `apps/web/src/paper/PaperActionPanel.test.tsx`
- Create: `apps/web/src/paper/PaperPreviewPanel.test.tsx`
- Modify: `apps/web/src/index.css`

**Steps:**

- [ ] Write failing tests for approve, bounded modify, reject, preview, submit, expired approval, stale preview, validation errors, and paper-only labels.
- [ ] Run RED: `npm test -- src/paper/PaperActionPanel.test.tsx src/paper/PaperPreviewPanel.test.tsx`.
- [ ] Implement action and preview panels using paper API fetchers.
- [ ] Ensure submit controls are disabled until preview is current and clearly labeled `Submit paper order`.
- [ ] Run GREEN: `npm run lint && npm test -- src/paper/PaperActionPanel.test.tsx src/paper/PaperPreviewPanel.test.tsx && npm run build`.
- [ ] Commit: `git add apps/web/src/paper apps/web/src/index.css && git commit -m "feat: add paper approval actions"`.

### Task 11: Orders, Positions, And Recovery UI

**Files:**
- Create: `apps/web/src/paper/PaperOrdersPanel.tsx`
- Create: `apps/web/src/paper/PaperPositionsPanel.tsx`
- Create: `apps/web/src/paper/PaperRecoveryPanel.tsx`
- Create: `apps/web/src/paper/PaperOrdersPanel.test.tsx`
- Create: `apps/web/src/paper/PaperPositionsPanel.test.tsx`
- Create: `apps/web/src/paper/PaperRecoveryPanel.test.tsx`
- Modify: `apps/web/src/dashboard/navigation.ts`
- Modify: `apps/web/src/dashboard/DashboardShell.tsx`
- Modify: `apps/web/src/index.css`

**Steps:**

- [ ] Write failing tests for order status table, cancel/replace controls, partial fills, rejects, timeouts, position P/L facts, stops, targets, expiration warnings, assignment warnings, and recovery state.
- [ ] Run RED: `npm test -- src/paper/PaperOrdersPanel.test.tsx src/paper/PaperPositionsPanel.test.tsx src/paper/PaperRecoveryPanel.test.tsx`.
- [ ] Implement orders, positions, and recovery panels.
- [ ] Ensure all controls are paper-only and no Schwab/live/broker wording appears.
- [ ] Run GREEN: `npm run lint && npm test -- src/paper/PaperOrdersPanel.test.tsx src/paper/PaperPositionsPanel.test.tsx src/paper/PaperRecoveryPanel.test.tsx && npm run build`.
- [ ] Commit: `git add apps/web/src/paper apps/web/src/dashboard apps/web/src/index.css && git commit -m "feat: render paper orders and positions"`.

### Task 12: End-To-End Fixtures And Smoke Coverage

**Files:**
- Create: `apps/api/fixtures/paper_lifecycle/*`
- Create: `apps/api/scripts/generate_paper_lifecycle_fixtures.py`
- Create: `apps/api/tests/paper/test_fixture_conformance.py`
- Modify: `scripts/verify-foundation.sh`

**Steps:**

- [ ] Write failing fixture conformance tests for success, partial fill, reject, stale quote, expired approval, cancel race, restart recovery, and simulated assignment.
- [ ] Run RED: `.venv/bin/pytest tests/paper/test_fixture_conformance.py -q`.
- [ ] Add deterministic fixture generation and validation helpers.
- [ ] Add safe paper lifecycle smoke checks to `scripts/verify-foundation.sh` that do not create live/broker state.
- [ ] Run GREEN: `.venv/bin/ruff check src tests scripts && .venv/bin/mypy src tests scripts && .venv/bin/pytest tests/paper -q`.
- [ ] Run Docker smoke from repository root: `docker compose up --build -d`, `./scripts/verify-foundation.sh`, `docker compose down`.
- [ ] Commit: `git add apps/api/fixtures/paper_lifecycle apps/api/scripts/generate_paper_lifecycle_fixtures.py apps/api/tests/paper scripts/verify-foundation.sh && git commit -m "test: add paper lifecycle fixtures and smoke coverage"`.

### Task 13: Runbook, Roadmap, And Full Verification

**Files:**
- Create: `docs/milestone-9-paper-approval-execution-position-lifecycle.md`
- Modify: `docs/development-roadmap.md`

**Steps:**

- [ ] Write the runbook with local startup, source eligibility, approval workflow, preview/submit behavior, paper broker scenarios, position lifecycle, recovery, fixture expectations, and explicit non-capabilities.
- [ ] Update the roadmap Milestone 9 status to Complete and next planning action to Milestone 10.
- [ ] Run full backend gates from `apps/api`: `.venv/bin/ruff check src tests scripts`, `.venv/bin/mypy src tests scripts`, `.venv/bin/pytest -q`.
- [ ] Run frontend gates from `apps/web`: `npm run lint`, `npm test`, `npm run build`.
- [ ] Run Alembic SQLite head upgrade.
- [ ] Run Docker compose build/start and `./scripts/verify-foundation.sh`; stop compose after verification.
- [ ] Commit: `git add docs && git commit -m "docs: complete paper lifecycle milestone"`.

## Completion Criteria

Milestone 9 is complete only when every task has passed its verification command,
the runbook is written, the roadmap points to Milestone 10 as the next planning
action, and the system can complete deterministic paper approval, preview,
submission, fill, position, and recovery scenarios without any Schwab, broker,
credential, or live-mode capability.
