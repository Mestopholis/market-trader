# Milestone 10 Reliability, Recovery, Observability, And Security Runbook

Scope: local, paper-only hardening for the market-trader application. This runbook covers authentication, observability, readiness blocking, recovery drills, security gates, and fault injection. It does not authorize Schwab, broker credentials, live mode, external deployment, or automatic trading.

## Local Auth Setup

The API reads configuration from `MARKET_TRADER_` environment variables or `apps/api/.env` when running from `apps/api`.

Required local auth variables:

```bash
MARKET_TRADER_AUTH_USERNAME=operator
MARKET_TRADER_AUTH_PASSWORD_HASH=<pbkdf2_sha256_hash>
MARKET_TRADER_SESSION_SECRET=<random_session_secret>
MARKET_TRADER_SESSION_TTL_SECONDS=3600
```

Generate a password hash from `apps/api`:

```bash
./.venv/bin/python -c 'from market_trader.security.passwords import hash_password; import getpass; print(hash_password(getpass.getpass()))'
```

Generate a session secret:

```bash
python3 -c 'import secrets; print(secrets.token_urlsafe(32))'
```

Password rotation is deliberately manual and local:

1. Stop the API or compose stack.
2. Generate a new PBKDF2-SHA256 password hash.
3. Replace `MARKET_TRADER_AUTH_PASSWORD_HASH` in the local environment or `.env` file.
4. Generate and replace `MARKET_TRADER_SESSION_SECRET` if existing sessions should be invalidated immediately.
5. Restart the API and log in again.

Sensitive API and dashboard routes require an authenticated session. Mutating paper routes also require the session-bound CSRF token returned by login. `/api/health` remains unauthenticated and safe for local smoke checks.

## Structured Logs And Correlation IDs

API request logs and safe errors use structured fields:

- `timestamp`, `level`, `event`, `component`
- `request_id`, `correlation_id`
- request method, path template, status code, latency, and client category
- paper lifecycle action, source identifiers, transition status, and failure code when applicable
- recovery drill id, step, result, and database integrity status when applicable

Every user-facing backend error should include a stable code, a safe summary, and a correlation id. Use the correlation id from an API response header or response body to search logs for the matching structured record. Logs and frontend state must not include raw cookies, authorization headers, CSRF tokens, passwords, database URLs with credentials, broker account numbers, or raw backend exception text.

## Health And Readiness

Use `/api/health` for unauthenticated local smoke checks. It intentionally returns a small safe payload.

Use `/api/readiness` after login for detailed operator state. It reports component status for database connectivity, migration state, backup freshness, provider/data freshness, scheduler jobs, risk locks, paper reconciliation, auth configuration, and security metadata.

Readiness components have a stable shape:

- `name`: component family, such as `database`, `backup`, or `restart_recovery`
- `status`: `ready`, `stale`, `partial`, `blocking`, or `unavailable`
- `code`: stable machine-readable reason
- `summary`: safe operator-facing text
- `blocking`: whether paper mutations must stop
- `details`: redacted bounded diagnostics

When any readiness component is blocking, paper approval, preview, submit, cancel, replace, and position-exit controls are disabled in the frontend. Read-only dashboard views should continue rendering safe unavailable states.

## Backup, Restore, And Integrity Drills

Backup metadata is collected by `market_trader.recovery.backup.collect_backup_metadata`. It records source path, destination path, created timestamp, Alembic schema revision, row counts for audit and paper lifecycle tables, SHA-256 checksum, correlation id, and integrity status.

SQLite integrity is validated by `market_trader.recovery.integrity.validate_sqlite_integrity`. It runs SQLite `PRAGMA integrity_check` and repository-level paper audit consistency checks. A failed integrity check is a blocking operational state.

Recommended local drill pattern:

```bash
cd apps/api
mkdir -p data
MARKET_TRADER_DATABASE_URL=sqlite:///./data/market_trader.db ./.venv/bin/alembic upgrade head
./.venv/bin/python -m scripts.run_recovery_drill ./data/market_trader.db --correlation-id corr-local-drill
```

For restore validation, restore into an explicit destination path and validate that audit records, approvals, orders, fills, positions, risk locks, and recovery events match the source expectations before using the restored database. Do not overwrite an existing local database unless the operation is an intentional test-only force scenario.

## Restart Recovery

Run restart recovery after an API restart, host reboot, restore, or any suspected interrupted paper lifecycle action:

```bash
cd apps/api
./.venv/bin/python -m scripts.run_recovery_drill ./data/market_trader.db --correlation-id corr-restart-check
```

The drill prioritizes open paper positions, working orders, timed-out paper broker requests, and expiring approvals. Any unresolved restart recovery gap should appear as a blocking readiness component and should keep mutating paper controls disabled until reconciled.

## Security Gates

Run the local security gate from the repository root:

```bash
./scripts/security-check.sh
```

The gate performs:

- Python dependency consistency check with `pip check`
- Python static checks with Ruff
- Node production dependency audit with `npm audit --audit-level high --omit dev`
- secret-pattern and forbidden-capability scans over source, fixtures, scripts, web source, and web build output
- OpenAPI forbidden-capability scan
- container checks for non-root API runtime, pinned base images, loopback web binding, no privileged services, and no published API port
- `docker compose config` validation when Docker Compose is available

In a local offline environment, npm audit may continue only when the audit endpoint is unreachable and `MARKET_TRADER_ALLOW_OFFLINE_AUDIT` is not disabled. CI must fail on high-risk findings.

## Fault Injection

Fault injection is deterministic and test-only. The scenarios live under `market_trader.faults` and are covered by `apps/api/tests/reliability/test_fault_injection.py`.

Expected blocking scenarios:

- provider loss or stale provider data blocks provider-dependent paper actions
- database contention blocks paper submission or recovery actions safely
- clock drift blocks stale approvals, previews, freshness windows, or sessions
- backup destination write failure blocks backup-dependent actionability
- process restart recovery gaps block paper lifecycle mutations until reconciled

Run the fault-injection tests from `apps/api`:

```bash
./.venv/bin/pytest tests/reliability/test_fault_injection.py -q
```

## Full Milestone Verification

Backend gates from `apps/api`:

```bash
./.venv/bin/ruff check src tests scripts
./.venv/bin/mypy src tests scripts
./.venv/bin/pytest -q
mkdir -p data
./.venv/bin/alembic upgrade head
```

Frontend gates from `apps/web`:

```bash
npm run lint
npm test
npm run build
```

Security gate from the repository root:

```bash
./scripts/security-check.sh
```

Compose smoke from the repository root:

```bash
export MARKET_TRADER_AUTH_USERNAME=operator
export MARKET_TRADER_AUTH_PASSWORD_HASH=<pbkdf2_sha256_hash>
export MARKET_TRADER_AUTH_PASSWORD=<plaintext_for_verify_script_only>
export MARKET_TRADER_SESSION_SECRET=<random_session_secret>
docker compose build
docker compose up -d
./scripts/verify-foundation.sh
docker compose down
```

`MARKET_TRADER_AUTH_PASSWORD` is consumed by `verify-foundation.sh` only to perform the local login request. Do not persist plaintext passwords in tracked files.

When Docker is unavailable, `verify-foundation.sh` still validates fixtures through the local `apps/api/.venv` fallback. Serve the built frontend from `apps/web/dist` with `/api` proxied to the local API, set `MARKET_TRADER_URL` to that local web URL, and run the same script.

## Explicit Non-Capabilities

Milestone 10 remains local and paper-only. The system must not provide or imply:

- Schwab OAuth or token storage
- broker credentials or broker account linking
- live-mode arming
- live order placement, preview, cancel, replace, or reconciliation
- externally reachable deployment
- automatic trading

Any appearance of those capabilities in source, OpenAPI, fixtures, frontend build output, docs meant as operating instructions, or CI output should be treated as a milestone regression unless it is an explicit exclusion or forbidden-capability test.
