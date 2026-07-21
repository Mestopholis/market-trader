# Milestone 10 Reliability, Recovery, Observability, And Security Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:executing-plans` to implement this plan task-by-task. Use `superpowers:test-driven-development` for every behavior change.

**Goal:** Harden the local paper system with structured observability, recovery drills, local authentication, CI security checks, and deterministic fault-injection tests before any Schwab, broker credential, public deployment, or live-mode capability is introduced.

**Architecture:** Add small infrastructure modules around the existing FastAPI, SQLAlchemy, React, Docker, and verification script foundations. Keep observability, health state, authentication, recovery, and security-scan contracts explicit and testable. Paper lifecycle services consult blocking system state before mutating actions.

**Tech Stack:** Python 3.12/3.13, FastAPI, Pydantic, SQLAlchemy 2, Alembic, pytest, Ruff, strict mypy, pip-audit or equivalent Python dependency audit, Bandit or equivalent static-security check, React 19, TypeScript, Vite, Vitest, Testing Library, npm audit, Docker Compose.

**Specification:** `docs/plans/2026-07-21-milestone-10-reliability-recovery-observability-security-spec.md`

## Global Constraints

- Work from a `milestone10` branch or worktree based on complete Milestone 9.
- Use TDD for every behavior change: RED, GREEN, refactor, commit.
- Keep the system local and paper-only.
- Do not add Schwab OAuth, Schwab clients, broker credentials, external broker references, live-mode arming, live order submission, public deployment, or network-exposed access.
- Keep `/api/health` safe for local smoke checks; detailed diagnostics must be redacted and session-protected when sensitive.
- Keep timestamps aware UTC in backend contracts.
- Run backend commands from `apps/api` using `.venv/bin/`.
- Run frontend commands from `apps/web`.

## File Structure

| Path | Responsibility |
| --- | --- |
| `apps/api/src/market_trader/observability/*` | Structured logging, correlation ids, redaction, error contracts. |
| `apps/api/src/market_trader/system_state/*` | Health/readiness models, component state aggregation, blocking state policy. |
| `apps/api/src/market_trader/security/*` | Local sessions, password verification, CSRF, secret scanning helpers. |
| `apps/api/src/market_trader/recovery/*` | Backup metadata, integrity checks, restore validation, restart recovery drills. |
| `apps/api/src/market_trader/faults/*` | Deterministic fault injectors used by tests only. |
| `apps/api/src/market_trader/api/auth.py` | Login, logout, session, and CSRF endpoints. |
| `apps/api/src/market_trader/api/health.py` | Safe health and detailed readiness contracts. |
| `apps/api/src/market_trader/api/paper.py` | Enforce authenticated, CSRF-protected, health-gated paper mutations. |
| `apps/api/migrations/versions/*_reliability_state.py` | Operational status, backup metadata, and recovery drill records if needed. |
| `apps/api/tests/reliability/*` | Backend observability, health, recovery, security, and fault-injection tests. |
| `apps/web/src/auth/*` | Login/session API and UI. |
| `apps/web/src/operations/*` | Health, recovery, and blocking-state UI. |
| `apps/web/src/paper/*` | Disable paper actions when system state blocks mutations. |
| `.github/workflows/*` | CI gates if workflows are present or added in this milestone. |
| `scripts/verify-foundation.sh` | Add local security, health, recovery, and no-secret smoke checks. |
| `docs/milestone-10-reliability-recovery-observability-security.md` | Operator runbook. |
| `docs/development-roadmap.md` | Link Milestone 10 plan and mark complete after verification. |

---

### Task 1: Redaction And Correlation Contracts

**Files:**
- Create: `apps/api/src/market_trader/observability/__init__.py`
- Create: `apps/api/src/market_trader/observability/redaction.py`
- Create: `apps/api/src/market_trader/observability/correlation.py`
- Create: `apps/api/tests/reliability/test_redaction.py`
- Create: `apps/api/tests/reliability/test_correlation.py`

**Steps:**

- [x] Write failing tests for redacting passwords, cookies, authorization headers, CSRF tokens, database URLs with credentials, Schwab-shaped tokens, broker account numbers, and nested secret-shaped payload keys.
- [x] Write failing tests for stable request id and correlation id generation, propagation, validation, and response header behavior.
- [x] Run RED: `.venv/bin/pytest tests/reliability/test_redaction.py tests/reliability/test_correlation.py -q`.
- [x] Implement bounded redaction and correlation helpers without logging raw payloads.
- [x] Run GREEN: `.venv/bin/ruff check src/market_trader/observability tests/reliability/test_redaction.py tests/reliability/test_correlation.py && .venv/bin/mypy src/market_trader/observability tests/reliability/test_redaction.py tests/reliability/test_correlation.py && .venv/bin/pytest tests/reliability/test_redaction.py tests/reliability/test_correlation.py -q`.
- [x] Commit: `git add apps/api/src/market_trader/observability apps/api/tests/reliability && git commit -m "feat: add redaction and correlation contracts"`.

### Task 2: Structured Logging And Safe Errors

**Files:**
- Create: `apps/api/src/market_trader/observability/logging.py`
- Create: `apps/api/src/market_trader/observability/errors.py`
- Modify: `apps/api/src/market_trader/main.py`
- Create: `apps/api/tests/reliability/test_structured_logging.py`
- Create: `apps/api/tests/reliability/test_safe_errors.py`

**Steps:**

- [x] Write failing tests proving API requests emit structured records with timestamp, level, event, component, request id, correlation id, path template, status, and latency.
- [x] Add tests proving exceptions return safe error codes, correlation ids, and redacted summaries without raw exception text or secret values.
- [x] Run RED: `.venv/bin/pytest tests/reliability/test_structured_logging.py tests/reliability/test_safe_errors.py -q`.
- [x] Add FastAPI middleware and exception handling for structured logs and safe error responses.
- [x] Run GREEN: `.venv/bin/ruff check src/market_trader/observability src/market_trader/main.py tests/reliability/test_structured_logging.py tests/reliability/test_safe_errors.py && .venv/bin/mypy src/market_trader/observability src/market_trader/main.py tests/reliability/test_structured_logging.py tests/reliability/test_safe_errors.py && .venv/bin/pytest tests/reliability/test_structured_logging.py tests/reliability/test_safe_errors.py -q`.
- [x] Commit: `git add apps/api/src/market_trader/observability apps/api/src/market_trader/main.py apps/api/tests/reliability && git commit -m "feat: emit structured safe api diagnostics"`.

### Task 3: System State And Readiness

**Files:**
- Create: `apps/api/src/market_trader/system_state/__init__.py`
- Create: `apps/api/src/market_trader/system_state/models.py`
- Create: `apps/api/src/market_trader/system_state/service.py`
- Modify: `apps/api/src/market_trader/api/health.py`
- Create: `apps/api/tests/reliability/test_system_state.py`
- Create: `apps/api/tests/reliability/test_readiness_api.py`

**Steps:**

- [x] Write failing tests for database, migration head, backup freshness, market data freshness, scheduler jobs, risk locks, paper reconciliation, authentication configuration, and security-scan component states.
- [x] Add tests proving `/api/health` stays safe and detailed readiness redacts sensitive diagnostics.
- [x] Run RED: `.venv/bin/pytest tests/reliability/test_system_state.py tests/reliability/test_readiness_api.py -q`.
- [x] Implement health/readiness models, state aggregation, and detailed readiness endpoint.
- [x] Run GREEN: `.venv/bin/ruff check src/market_trader/system_state src/market_trader/api/health.py tests/reliability/test_system_state.py tests/reliability/test_readiness_api.py && .venv/bin/mypy src/market_trader/system_state src/market_trader/api/health.py tests/reliability/test_system_state.py tests/reliability/test_readiness_api.py && .venv/bin/pytest tests/reliability/test_system_state.py tests/reliability/test_readiness_api.py -q`.
- [x] Commit: `git add apps/api/src/market_trader/system_state apps/api/src/market_trader/api/health.py apps/api/tests/reliability && git commit -m "feat: expose detailed system readiness state"`.

### Task 4: Blocking State Enforcement

**Files:**
- Create: `apps/api/src/market_trader/system_state/blocking.py`
- Modify: `apps/api/src/market_trader/paper/service.py`
- Modify: `apps/api/src/market_trader/api/paper.py`
- Create: `apps/api/tests/reliability/test_blocking_state.py`

**Steps:**

- [x] Write failing tests proving stale data, provider loss, required risk locks, failed reconciliation, backup integrity failure, and restart recovery gaps block dependent paper mutations with stable failure codes.
- [x] Add tests proving read-only paper and dashboard views can still render safe unavailable states.
- [x] Run RED: `.venv/bin/pytest tests/reliability/test_blocking_state.py -q`.
- [x] Implement blocking policy checks in paper mutation paths and safe response contracts.
- [x] Run GREEN: `.venv/bin/ruff check src/market_trader/system_state src/market_trader/paper src/market_trader/api/paper.py tests/reliability/test_blocking_state.py && .venv/bin/mypy src/market_trader/system_state src/market_trader/paper src/market_trader/api/paper.py tests/reliability/test_blocking_state.py && .venv/bin/pytest tests/reliability/test_blocking_state.py -q`.
- [x] Commit: `git add apps/api/src/market_trader/system_state apps/api/src/market_trader/paper apps/api/src/market_trader/api/paper.py apps/api/tests/reliability/test_blocking_state.py && git commit -m "feat: block unsafe paper actions from system state"`.

### Task 5: Backup Metadata And Integrity Validation

**Files:**
- Create: `apps/api/src/market_trader/recovery/__init__.py`
- Create: `apps/api/src/market_trader/recovery/backup.py`
- Create: `apps/api/src/market_trader/recovery/integrity.py`
- Modify: `apps/api/src/market_trader/db/backup.py`
- Create: `apps/api/tests/reliability/test_backup_integrity.py`

**Steps:**

- [x] Write failing tests for backup metadata, schema revision, row counts, checksums, SQLite integrity checks, audit-table consistency, paper lifecycle consistency, and safe destination handling.
- [x] Run RED: `.venv/bin/pytest tests/reliability/test_backup_integrity.py -q`.
- [x] Implement metadata generation and integrity validation around the existing SQLite backup helpers.
- [x] Run GREEN: `.venv/bin/ruff check src/market_trader/recovery src/market_trader/db/backup.py tests/reliability/test_backup_integrity.py && .venv/bin/mypy src/market_trader/recovery src/market_trader/db/backup.py tests/reliability/test_backup_integrity.py && .venv/bin/pytest tests/reliability/test_backup_integrity.py -q`.
- [x] Commit: `git add apps/api/src/market_trader/recovery apps/api/src/market_trader/db/backup.py apps/api/tests/reliability/test_backup_integrity.py && git commit -m "feat: validate backup integrity metadata"`.

### Task 6: Restore And Restart Recovery Drills

**Files:**
- Create: `apps/api/src/market_trader/recovery/restore.py`
- Create: `apps/api/src/market_trader/recovery/restart.py`
- Create: `apps/api/scripts/run_recovery_drill.py`
- Create: `apps/api/tests/reliability/test_restore_recovery.py`
- Create: `apps/api/tests/reliability/test_restart_recovery.py`

**Steps:**

- [x] Write failing tests proving restore validation preserves audit records, approvals, orders, fills, positions, risk locks, and recovery events.
- [x] Write failing tests proving restart recovery prioritizes open paper positions, working orders, timed-out broker requests, and expiring approvals.
- [x] Run RED: `.venv/bin/pytest tests/reliability/test_restore_recovery.py tests/reliability/test_restart_recovery.py -q`.
- [x] Implement restore validation and restart-recovery drill services using existing repositories and paper lifecycle read models.
- [x] Run GREEN: `.venv/bin/ruff check src/market_trader/recovery scripts/run_recovery_drill.py tests/reliability/test_restore_recovery.py tests/reliability/test_restart_recovery.py && .venv/bin/mypy src/market_trader/recovery scripts/run_recovery_drill.py tests/reliability/test_restore_recovery.py tests/reliability/test_restart_recovery.py && .venv/bin/pytest tests/reliability/test_restore_recovery.py tests/reliability/test_restart_recovery.py -q`.
- [x] Commit: `git add apps/api/src/market_trader/recovery apps/api/scripts/run_recovery_drill.py apps/api/tests/reliability && git commit -m "feat: add restore and restart recovery drills"`.

### Task 7: Local Authentication And CSRF

**Files:**
- Create: `apps/api/src/market_trader/security/__init__.py`
- Create: `apps/api/src/market_trader/security/session.py`
- Create: `apps/api/src/market_trader/security/passwords.py`
- Create: `apps/api/src/market_trader/security/csrf.py`
- Create: `apps/api/src/market_trader/api/auth.py`
- Modify: `apps/api/src/market_trader/config.py`
- Modify: `apps/api/src/market_trader/main.py`
- Create: `apps/api/tests/reliability/test_auth.py`
- Create: `apps/api/tests/reliability/test_csrf.py`

**Steps:**

- [x] Write failing tests for login, logout, session expiry, secure cookie attributes, password hash verification, safe unauthenticated responses, and CSRF protection for mutating requests.
- [x] Add tests proving `/api/health` remains unauthenticated and sensitive diagnostics remain protected.
- [x] Run RED: `.venv/bin/pytest tests/reliability/test_auth.py tests/reliability/test_csrf.py -q`.
- [x] Implement local password/session/CSRF modules and auth routes without external identity providers.
- [x] Run GREEN: `.venv/bin/ruff check src/market_trader/security src/market_trader/api/auth.py src/market_trader/config.py src/market_trader/main.py tests/reliability/test_auth.py tests/reliability/test_csrf.py && .venv/bin/mypy src/market_trader/security src/market_trader/api/auth.py src/market_trader/config.py src/market_trader/main.py tests/reliability/test_auth.py tests/reliability/test_csrf.py && .venv/bin/pytest tests/reliability/test_auth.py tests/reliability/test_csrf.py -q`.
- [x] Commit: `git add apps/api/src/market_trader/security apps/api/src/market_trader/api/auth.py apps/api/src/market_trader/config.py apps/api/src/market_trader/main.py apps/api/tests/reliability && git commit -m "feat: add local session authentication"`.

### Task 8: Protect Sensitive APIs

**Files:**
- Modify: `apps/api/src/market_trader/api/dashboard.py`
- Modify: `apps/api/src/market_trader/api/paper.py`
- Modify: `apps/api/src/market_trader/api/market_state.py`
- Create: `apps/api/tests/reliability/test_sensitive_api_protection.py`

**Steps:**

- [x] Write failing API tests proving dashboard, paper, detailed readiness, and mutating market/paper endpoints reject unauthenticated requests where sensitive or actionable data is exposed.
- [x] Add tests proving mutating requests require CSRF and safe no-store headers.
- [x] Run RED: `.venv/bin/pytest tests/reliability/test_sensitive_api_protection.py -q`.
- [x] Apply auth dependencies and CSRF guards to sensitive routes while keeping safe health checks available.
- [x] Run GREEN: `.venv/bin/ruff check src/market_trader/api src/market_trader/security tests/reliability/test_sensitive_api_protection.py && .venv/bin/mypy src/market_trader/api src/market_trader/security tests/reliability/test_sensitive_api_protection.py && .venv/bin/pytest tests/reliability/test_sensitive_api_protection.py -q`.
- [x] Commit: `git add apps/api/src/market_trader/api apps/api/src/market_trader/security apps/api/tests/reliability/test_sensitive_api_protection.py && git commit -m "feat: require local auth for sensitive apis"`.

### Task 9: Security And CI Gates

**Files:**
- Create or modify: `.github/workflows/ci.yml`
- Create: `scripts/security-check.sh`
- Modify: `scripts/verify-foundation.sh`
- Modify: `apps/api/pyproject.toml`
- Modify: `apps/web/package.json`
- Create: `apps/api/tests/reliability/test_forbidden_capabilities.py`

**Steps:**

- [ ] Write failing tests proving OpenAPI contracts, source, fixtures, and frontend build artifacts do not expose Schwab, broker credential, live order, or externally reachable deployment capability.
- [ ] Run RED: `.venv/bin/pytest tests/reliability/test_forbidden_capabilities.py -q`.
- [ ] Add security-check script for Python dependency audit, static-security scan, Node audit, secret scan, container configuration checks, and forbidden capability scan.
- [ ] Wire security checks into CI or documented local gates.
- [ ] Run GREEN: `.venv/bin/ruff check src tests scripts && .venv/bin/mypy src tests scripts && .venv/bin/pytest tests/reliability/test_forbidden_capabilities.py -q`.
- [ ] Run frontend gates: `npm run lint && npm test && npm run build`.
- [ ] Run security gate: `./scripts/security-check.sh`.
- [ ] Commit: `git add .github scripts apps/api/pyproject.toml apps/web/package.json apps/api/tests/reliability/test_forbidden_capabilities.py && git commit -m "ci: add milestone security gates"`.

### Task 10: Deterministic Fault Injection

**Files:**
- Create: `apps/api/src/market_trader/faults/__init__.py`
- Create: `apps/api/src/market_trader/faults/models.py`
- Create: `apps/api/src/market_trader/faults/injectors.py`
- Create: `apps/api/tests/reliability/test_fault_injection.py`

**Steps:**

- [ ] Write failing tests for provider loss, database contention, clock drift, disk pressure/write failure, and process restart recovery scenarios.
- [ ] Ensure tests are deterministic, bounded, and do not require network access or destructive disk filling.
- [ ] Run RED: `.venv/bin/pytest tests/reliability/test_fault_injection.py -q`.
- [ ] Implement test-only fault injectors and production guards that translate injected failures into blocking system states and safe diagnostics.
- [ ] Run GREEN: `.venv/bin/ruff check src/market_trader/faults src/market_trader/system_state tests/reliability/test_fault_injection.py && .venv/bin/mypy src/market_trader/faults src/market_trader/system_state tests/reliability/test_fault_injection.py && .venv/bin/pytest tests/reliability/test_fault_injection.py -q`.
- [ ] Commit: `git add apps/api/src/market_trader/faults apps/api/src/market_trader/system_state apps/api/tests/reliability/test_fault_injection.py && git commit -m "test: add deterministic reliability fault injection"`.

### Task 11: Frontend Auth And Operations UI

**Files:**
- Create: `apps/web/src/auth/types.ts`
- Create: `apps/web/src/auth/api.ts`
- Create: `apps/web/src/auth/LoginView.tsx`
- Create: `apps/web/src/auth/AuthProvider.tsx`
- Create: `apps/web/src/auth/*.test.tsx`
- Create: `apps/web/src/operations/SystemHealthPanel.tsx`
- Create: `apps/web/src/operations/RecoveryPanel.tsx`
- Create: `apps/web/src/operations/*.test.tsx`
- Modify: `apps/web/src/App.tsx`
- Modify: `apps/web/src/api.ts`
- Modify: `apps/web/src/index.css`

**Steps:**

- [ ] Write failing tests for login, logout, session-expired state, unauthenticated routing, safe error rendering, health panel states, recovery drill state, and correlation-id display.
- [ ] Run RED: `npm test -- src/auth src/operations`.
- [ ] Implement auth provider, login view, operations panels, and typed API clients.
- [ ] Run GREEN: `npm run lint && npm test -- src/auth src/operations && npm run build`.
- [ ] Commit: `git add apps/web/src/auth apps/web/src/operations apps/web/src/App.tsx apps/web/src/api.ts apps/web/src/index.css && git commit -m "feat: add local auth and operations ui"`.

### Task 12: Frontend Blocking States For Paper Actions

**Files:**
- Modify: `apps/web/src/paper/*`
- Modify: `apps/web/src/dashboard/*`
- Create: `apps/web/src/paper/PaperBlockingState.test.tsx`
- Modify: `apps/web/src/index.css`

**Steps:**

- [ ] Write failing tests proving paper approval, preview, submit, cancel, replace, and position-exit controls are disabled when system state blocks actions.
- [ ] Add tests proving safe unavailable/stale states do not render raw backend exception text or secrets.
- [ ] Run RED: `npm test -- src/paper/PaperBlockingState.test.tsx`.
- [ ] Wire readiness/blocking-state API data into paper and dashboard views.
- [ ] Run GREEN: `npm run lint && npm test -- src/paper/PaperBlockingState.test.tsx && npm run build`.
- [ ] Commit: `git add apps/web/src/paper apps/web/src/dashboard apps/web/src/index.css && git commit -m "feat: show reliability blocks in paper ui"`.

### Task 13: Runbook And Full Verification

**Files:**
- Create: `docs/milestone-10-reliability-recovery-observability-security.md`
- Modify: `docs/development-roadmap.md`
- Modify: `scripts/verify-foundation.sh`

**Steps:**

- [ ] Write the runbook with local auth setup, password rotation, structured log fields, correlation-id lookup, health states, backup/restore/integrity drills, restart recovery, security scans, fault injection, and explicit non-capabilities.
- [ ] Update the roadmap Milestone 10 status to Complete only after all verification gates pass, and set the next planning action to Milestone 11 read-only Schwab integration specification.
- [ ] Run full backend gates from `apps/api`: `.venv/bin/ruff check src tests scripts`, `.venv/bin/mypy src tests scripts`, `.venv/bin/pytest -q`.
- [ ] Run frontend gates from `apps/web`: `npm run lint`, `npm test`, `npm run build`.
- [ ] Run security gate: `./scripts/security-check.sh`.
- [ ] Run Alembic SQLite head upgrade.
- [ ] Run Docker compose build/start and `./scripts/verify-foundation.sh`; stop compose after verification.
- [ ] Commit: `git add docs scripts/verify-foundation.sh && git commit -m "docs: complete reliability hardening milestone"`.

## Completion Criteria

Milestone 10 is complete only when every task has passed its verification command, the runbook is written, structured logs and safe errors carry correlation ids, secrets cannot enter logs or frontend responses under tested inputs, recovery drills preserve audit and paper positions, local authentication protects sensitive screens and mutating APIs, security gates pass, and deterministic fault-injection coverage proves critical failures produce blocking system states with actionable diagnostics.
