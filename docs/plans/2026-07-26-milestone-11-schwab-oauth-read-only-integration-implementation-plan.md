# Milestone 11 Schwab OAuth And Read-Only Integration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:executing-plans` to implement this plan task-by-task. Use `superpowers:test-driven-development` for every behavior change.

**Goal:** Add Schwab OAuth and read-only market-data integration first, then add read-only account integration after separate Accounts and Trading Production approval, while keeping every order path disabled and preserving paper mode.

**Architecture:** Add Schwab as a backend-only provider behind explicit OAuth, token-storage, market-data, and broker-read interfaces. Sequence implementation around Schwab's product approvals: Market Data Production first, Accounts and Trading Production second. Persist encrypted token metadata and bounded normalized observations, expose safe authenticated status/read models to the operations UI, and keep deterministic fixtures available for tests and local verification.

**Tech Stack:** Python 3.12/3.13, FastAPI, Pydantic, SQLAlchemy 2, Alembic, httpx, pytest, Ruff, strict mypy, React 19, TypeScript, Vite, Vitest, Testing Library, Docker Compose.

**Specification:** `docs/plans/2026-07-26-milestone-11-schwab-oauth-read-only-integration-spec.md`

## Global Constraints

- Work from a `milestone11` branch or worktree based on complete Milestone 10.
- Use TDD for every behavior change: RED, GREEN, refactor, commit.
- Verify current Schwab portal OAuth, endpoint, scope, token, and rate-limit
  details before implementing HTTP clients.
- Implement Market Data Production first because that app is available before
  Accounts and Trading Production. Do not implement account, balance, position,
  transaction, or reconciliation behavior until the account app is approved.
- Do not commit Schwab credentials, tokens, account numbers, portal exports, or
  raw response payloads containing account identifiers.
- Do not add order preview, order placement, cancel, replace, saved-order,
  live-mode, or automatic trading capability.
- Keep `MARKET_TRADER_TRADING_MODE=paper`; startup and recovery must continue
  to reject live mode.
- Keep all Schwab mutating local control routes protected by local auth and
  CSRF. The OAuth callback validates signed state and never trusts query
  parameters alone.
- Run backend commands from `apps/api` using `.venv/bin/`.
- Run frontend commands from `apps/web`.

## File Structure

| Path | Responsibility |
| --- | --- |
| `apps/api/src/market_trader/broker/schwab/*` | Schwab OAuth, token storage, client, normalizers, and read-only adapters. |
| `apps/api/src/market_trader/broker/read_models.py` | Provider-neutral account, balance, position, transaction, and reconciliation models. |
| `apps/api/src/market_trader/api/broker.py` | Authenticated Schwab status, OAuth, revoke, refresh, and read-only broker data routes. |
| `apps/api/src/market_trader/db/models.py` | Encrypted token, OAuth state, broker account, broker position, and reconciliation ORM rows. |
| `apps/api/migrations/versions/*_schwab_read_only.py` | Milestone 11 storage migration. |
| `apps/api/tests/broker/*` | OAuth, token, client, normalizer, read-model, and safety tests. |
| `apps/api/tests/market_data/*` | Schwab provider conformance tests using mocked HTTP and recorded fixtures. |
| `apps/api/fixtures/schwab_read_only/*` | Redacted recorded-contract fixtures. |
| `apps/web/src/broker/*` | Broker status API, types, and read-only operations UI. |
| `apps/web/src/operations/*` | Link broker connection and reconciliation state into operations views. |
| `scripts/security-check.sh` | Extend forbidden-capability and secret scans for Schwab credentials and order endpoints. |
| `.env.example` | Add placeholder Schwab config without secrets. |
| `docs/milestone-11-schwab-oauth-read-only-integration.md` | Operator runbook. |
| `docs/development-roadmap.md` | Link Milestone 11 plan and mark complete only after verification. |

---

### Task 1: Portal Verification And Scope Lock

**Files:**
- Create: `docs/milestone-11-schwab-oauth-read-only-integration.md`
- Modify: `.env.example`
- Modify: `docs/plans/2026-07-26-milestone-11-schwab-oauth-read-only-integration-spec.md`

**Steps:**

- [ ] Log in to the Schwab developer portal and record non-secret facts only:
  Market Data app status, callback URL, OAuth URLs, base URLs, token lifetime,
  refresh behavior, rate-limit guidance, and read-only market-data endpoint
  list.
- [ ] Record that Accounts and Trading Production is pending/not yet in scope
  until separately approved.
- [ ] Update the spec if any portal detail conflicts with the draft.
- [ ] Add `.env.example` placeholders for Schwab market-data enablement,
  callback URL, client id, client secret, and token-encryption key. Add expected
  account hash placeholders only when the account slice begins.
- [ ] Write the initial runbook with Market Data app setup, callback
  registration, local secret generation, and explicit non-capabilities.
- [ ] Run: `rg -n "SCHWAB|Schwab|schwab" .env.example docs/milestone-11-schwab-oauth-read-only-integration.md docs/plans/2026-07-26-milestone-11-schwab-oauth-read-only-integration-spec.md`.
  Expected: only placeholders, setup instructions, and explicit exclusions.
- [ ] Commit: `git add .env.example docs/milestone-11-schwab-oauth-read-only-integration.md docs/plans/2026-07-26-milestone-11-schwab-oauth-read-only-integration-spec.md && git commit -m "docs: add schwab read-only setup guardrails"`.

### Task 2: Configuration And Forbidden Capability Gates

**Files:**
- Modify: `apps/api/src/market_trader/config.py`
- Modify: `scripts/security-check.sh`
- Create: `apps/api/tests/broker/test_schwab_configuration.py`
- Create: `apps/api/tests/broker/test_forbidden_schwab_capabilities.py`
- Modify: `apps/api/tests/reliability/test_forbidden_capabilities.py`

**Steps:**

- [ ] Write failing tests for disabled-by-default Schwab settings, required
  settings when enabled, invalid callback URL rejection, missing encryption key
  rejection, and live-mode rejection.
- [ ] Write failing forbidden-capability tests proving source, OpenAPI,
  fixtures, and frontend build artifacts do not contain Schwab order preview,
  order submit, cancel, replace, saved-order, or live-mode capability.
- [ ] Run RED: `.venv/bin/pytest tests/broker/test_schwab_configuration.py tests/broker/test_forbidden_schwab_capabilities.py tests/reliability/test_forbidden_capabilities.py -q`.
- [ ] Add Schwab settings to `Settings` with validation. Keep values optional
  unless Schwab is explicitly enabled.
- [ ] Extend `scripts/security-check.sh` scans for raw Schwab secret names,
  access tokens, refresh tokens, account numbers, and order-capability terms.
- [ ] Run GREEN: `.venv/bin/ruff check src/market_trader/config.py tests/broker tests/reliability/test_forbidden_capabilities.py && .venv/bin/mypy src/market_trader/config.py tests/broker tests/reliability/test_forbidden_capabilities.py && .venv/bin/pytest tests/broker/test_schwab_configuration.py tests/broker/test_forbidden_schwab_capabilities.py tests/reliability/test_forbidden_capabilities.py -q`.
- [ ] Commit: `git add apps/api/src/market_trader/config.py apps/api/tests/broker scripts/security-check.sh apps/api/tests/reliability/test_forbidden_capabilities.py && git commit -m "feat: add schwab read-only configuration guards"`.

### Task 3: Token Storage Migration

**Files:**
- Modify: `apps/api/src/market_trader/db/models.py`
- Create: `apps/api/migrations/versions/20260726_0011_schwab_read_only.py`
- Create: `apps/api/src/market_trader/broker/__init__.py`
- Create: `apps/api/src/market_trader/broker/schwab/__init__.py`
- Create: `apps/api/src/market_trader/broker/schwab/tokens.py`
- Create: `apps/api/tests/broker/test_schwab_token_storage.py`
- Modify: `apps/api/tests/test_migrations.py`

**Steps:**

- [ ] Write failing tests for encrypted token create, read metadata, refresh
  rotation, revoke, expired state, missing key failure, wrong key failure, and
  redacted `repr`/serialization.
- [ ] Add migration tests proving token and OAuth state tables migrate from an
  empty database and match ORM metadata.
- [ ] Run RED: `.venv/bin/pytest tests/broker/test_schwab_token_storage.py tests/test_migrations.py -q`.
- [ ] Add ORM tables for OAuth state, encrypted token material, token metadata,
  broker account fingerprint, and broker sync metadata.
- [ ] Implement token encryption using an authenticated encryption primitive.
  If adding `cryptography`, update `apps/api/pyproject.toml` in the same task;
  otherwise use a reviewed existing standard-library-compatible envelope design
  and document its limits.
- [ ] Run GREEN: `.venv/bin/ruff check src/market_trader/db src/market_trader/broker tests/broker/test_schwab_token_storage.py tests/test_migrations.py && .venv/bin/mypy src/market_trader/db src/market_trader/broker tests/broker/test_schwab_token_storage.py tests/test_migrations.py && .venv/bin/pytest tests/broker/test_schwab_token_storage.py tests/test_migrations.py -q`.
- [ ] Commit: `git add apps/api/src/market_trader/db apps/api/migrations/versions apps/api/src/market_trader/broker apps/api/tests/broker/test_schwab_token_storage.py apps/api/tests/test_migrations.py apps/api/pyproject.toml && git commit -m "feat: store schwab tokens encrypted"`.

### Task 4: OAuth Flow API

**Files:**
- Create: `apps/api/src/market_trader/broker/schwab/oauth.py`
- Create: `apps/api/src/market_trader/api/broker.py`
- Modify: `apps/api/src/market_trader/main.py`
- Create: `apps/api/tests/broker/test_schwab_oauth.py`

**Steps:**

- [ ] Write failing tests for OAuth start URL creation, signed state storage,
  state expiry, callback success, callback replay rejection, callback wrong
  state rejection, error callback handling, refresh, revoke, local auth
  protection, and CSRF enforcement.
- [ ] Run RED: `.venv/bin/pytest tests/broker/test_schwab_oauth.py -q`.
- [ ] Implement OAuth service and FastAPI routes. Use `httpx.MockTransport` in
  tests; no test may call Schwab over the network.
- [ ] Add audit journal events for start, callback success/failure, refresh,
  revoke, and authentication lock changes.
- [ ] Run GREEN: `.venv/bin/ruff check src/market_trader/broker src/market_trader/api/broker.py src/market_trader/main.py tests/broker/test_schwab_oauth.py && .venv/bin/mypy src/market_trader/broker src/market_trader/api/broker.py src/market_trader/main.py tests/broker/test_schwab_oauth.py && .venv/bin/pytest tests/broker/test_schwab_oauth.py -q`.
- [ ] Commit: `git add apps/api/src/market_trader/broker apps/api/src/market_trader/api/broker.py apps/api/src/market_trader/main.py apps/api/tests/broker/test_schwab_oauth.py && git commit -m "feat: add schwab oauth flow"`.

### Task 5: Schwab HTTP Client And Read-Only Normalizers

**Files:**
- Create: `apps/api/src/market_trader/broker/schwab/client.py`
- Create: `apps/api/src/market_trader/broker/schwab/normalizers.py`
- Create: `apps/api/fixtures/schwab_read_only/quotes.json`
- Create: `apps/api/fixtures/schwab_read_only/option-chain.json`
- Create: `apps/api/fixtures/schwab_read_only/accounts.json`
- Create: `apps/api/fixtures/schwab_read_only/positions.json`
- Create: `apps/api/fixtures/schwab_read_only/transactions.json`
- Create: `apps/api/tests/broker/test_schwab_client.py`
- Create: `apps/api/tests/broker/test_schwab_normalizers.py`

**Steps:**

- [ ] Write failing client tests for bearer-token injection, token refresh
  before request, 401 auth lock, 429 rate-limit state, 5xx provider-unavailable
  state, malformed JSON quarantine, timeout handling, and redacted diagnostics.
- [ ] Write failing normalizer tests for redacted recorded fixtures covering
  quotes, option chains, accounts, balances, positions, and transactions.
- [ ] Run RED: `.venv/bin/pytest tests/broker/test_schwab_client.py tests/broker/test_schwab_normalizers.py -q`.
- [ ] Implement a small `httpx` client wrapper and pure normalizers. Do not
  include order endpoints in code, fixtures, type names, or tests.
- [ ] Run GREEN: `.venv/bin/ruff check src/market_trader/broker apps/api/tests/broker && .venv/bin/mypy src/market_trader/broker tests/broker && .venv/bin/pytest tests/broker/test_schwab_client.py tests/broker/test_schwab_normalizers.py -q`.
- [ ] Commit: `git add apps/api/src/market_trader/broker apps/api/fixtures/schwab_read_only apps/api/tests/broker && git commit -m "feat: add schwab read-only client normalizers"`.

### Task 6: Market Data Provider Adapter

**Files:**
- Create: `apps/api/src/market_trader/broker/schwab/market_data.py`
- Create: `apps/api/tests/market_data/test_schwab_provider_contracts.py`
- Modify: `apps/api/src/market_trader/market_data/providers.py` if capability metadata needs extension.

**Steps:**

- [ ] Write failing provider-conformance tests for quotes, candles, option
  chains, unsupported corporate actions if not available, provider health,
  stale timestamps, rate limits, and unavailable state.
- [ ] Run RED: `.venv/bin/pytest tests/market_data/test_schwab_provider_contracts.py -q`.
- [ ] Implement adapter methods returning existing normalized `ProviderEvent`
  records or `UnsupportedCapability`.
- [ ] Run GREEN: `.venv/bin/ruff check src/market_trader/broker src/market_trader/market_data/providers.py tests/market_data/test_schwab_provider_contracts.py && .venv/bin/mypy src/market_trader/broker src/market_trader/market_data/providers.py tests/market_data/test_schwab_provider_contracts.py && .venv/bin/pytest tests/market_data/test_schwab_provider_contracts.py -q`.
- [ ] Commit: `git add apps/api/src/market_trader/broker/schwab apps/api/src/market_trader/market_data/providers.py apps/api/tests/market_data/test_schwab_provider_contracts.py && git commit -m "feat: add schwab market data provider"`.

### Task 7: Account Read Models And Reconciliation

**Files:**
- Create: `apps/api/src/market_trader/broker/read_models.py`
- Create: `apps/api/src/market_trader/broker/reconciliation.py`
- Modify: `apps/api/src/market_trader/api/broker.py`
- Modify: `apps/api/src/market_trader/system_state/service.py`
- Create: `apps/api/tests/broker/test_broker_read_models.py`
- Create: `apps/api/tests/broker/test_broker_reconciliation.py`

**Steps:**

- [ ] Write failing tests for account fingerprint verification, balances,
  positions, transactions, reconciliation summaries, account mismatch blocking,
  unavailable states, stale states, and no paper-position mutation.
- [ ] Run RED: `.venv/bin/pytest tests/broker/test_broker_read_models.py tests/broker/test_broker_reconciliation.py -q`.
- [ ] Implement read models and reconciliation service using normalized Schwab
  account observations and local paper state.
- [ ] Add readiness components for Schwab auth, account identity, market data,
  account data, rate limits, and reconciliation.
- [ ] Run GREEN: `.venv/bin/ruff check src/market_trader/broker src/market_trader/api/broker.py src/market_trader/system_state tests/broker/test_broker_read_models.py tests/broker/test_broker_reconciliation.py && .venv/bin/mypy src/market_trader/broker src/market_trader/api/broker.py src/market_trader/system_state tests/broker/test_broker_read_models.py tests/broker/test_broker_reconciliation.py && .venv/bin/pytest tests/broker/test_broker_read_models.py tests/broker/test_broker_reconciliation.py -q`.
- [ ] Commit: `git add apps/api/src/market_trader/broker apps/api/src/market_trader/api/broker.py apps/api/src/market_trader/system_state apps/api/tests/broker && git commit -m "feat: expose schwab account read models"`.

### Task 8: Operations UI

**Files:**
- Create: `apps/web/src/broker/types.ts`
- Create: `apps/web/src/broker/api.ts`
- Create: `apps/web/src/broker/BrokerStatusPanel.tsx`
- Create: `apps/web/src/broker/BrokerStatusPanel.test.tsx`
- Modify: `apps/web/src/operations/OperationsPanel.tsx`
- Modify: `apps/web/src/operations/OperationsPanel.test.tsx`
- Modify: `apps/web/src/dashboard/navigation.ts` if navigation needs a broker/status entry.

**Steps:**

- [ ] Write failing tests for broker status rendering, configured/unconfigured
  states, connected/expired/revoked states, account fingerprint display,
  freshness timestamps, reconciliation warnings, reauthenticate action, revoke
  action, and absence of order/live controls.
- [ ] Run RED: `npm test -- BrokerStatusPanel OperationsPanel`.
- [ ] Implement API helpers and UI using existing operations styling. Keep the
  panel dense and operational, not a marketing flow.
- [ ] Run GREEN: `npm run lint && npm test -- BrokerStatusPanel OperationsPanel`.
- [ ] Commit: `git add apps/web/src/broker apps/web/src/operations apps/web/src/dashboard/navigation.ts && git commit -m "feat: show schwab read-only operations state"`.

### Task 9: Verification, Docs, And Roadmap Completion

**Files:**
- Modify: `docs/milestone-11-schwab-oauth-read-only-integration.md`
- Modify: `docs/development-roadmap.md`
- Modify: `README.md` if local setup changes need a short pointer.
- Modify: `scripts/verify-foundation.sh`

**Steps:**

- [ ] Add offline verification to `verify-foundation.sh` proving the app starts
  without Schwab credentials and deterministic fixtures still validate.
- [ ] Document local OAuth setup, reauth, revoke, account mismatch recovery,
  rate-limit handling, fixture fallback, and explicit non-capabilities.
- [ ] Run backend verification:
  `.venv/bin/ruff check src tests scripts && .venv/bin/mypy src tests scripts && .venv/bin/pytest -q && .venv/bin/alembic upgrade head`.
- [ ] Run frontend verification:
  `npm run lint && npm test && npm run build`.
- [ ] Run repository security gate: `./scripts/security-check.sh`.
- [ ] Run forbidden capability scan:
  `rg -n "place order|submit order|order preview|cancel order|replace order|saved order|live mode" apps docs scripts README.md`.
  Expected: only explicit exclusions, forbidden-capability tests, or roadmap
  future-milestone text.
- [ ] Update roadmap Milestone 11 status to Complete only after every gate
  passes and the runbook is accurate.
- [ ] Commit: `git add docs README.md scripts/verify-foundation.sh && git commit -m "docs: complete schwab read-only milestone"`.

## Execution Notes

- Prefer mocked `httpx` transports and redacted recorded fixtures over network
  tests. Live Schwab calls are local operator smoke checks only and must never
  run in CI.
- When a test needs Schwab-shaped token values, use synthetic values that cannot
  authenticate and assert redaction.
- If Schwab portal details contradict any endpoint names or lifetime
  assumptions in this plan, update the spec and plan before coding that task.
- Do not merge Milestone 11 until PR #12's dashboard read-model cleanup is
  either merged or consciously superseded, because account/reconciliation UI
  depends on trustworthy persisted read models.
