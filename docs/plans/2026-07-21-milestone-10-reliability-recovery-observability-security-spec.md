# Milestone 10 Reliability, Recovery, Observability, And Security Specification

Date: July 21, 2026
Status: Draft specification
Depends on: Milestone 9
Roadmap milestone: 10

## Purpose

Milestone 10 hardens the local paper-trading system before any brokerage
credentials or broker connectivity are introduced. It adds observable runtime
state, recovery drills, secret-safe logging and responses, local access
protection for sensitive screens, security checks in CI, and deterministic
fault-injection coverage for the failure modes most likely to damage audit
history or paper positions.

The milestone remains local and paper-only. It must not add Schwab OAuth,
Schwab clients, external broker credentials, externally reachable deployment,
or live-mode arming.

## Approved Design Decisions

- Treat reliability and security state as first-class application data that can
  block unsafe paper actions.
- Add structured application logs with correlation identifiers at the FastAPI
  boundary and paper lifecycle service boundary.
- Redact secret-shaped values before logging, persisting diagnostics, returning
  API responses, or rendering frontend state.
- Extend health responses with component status while preserving the existing
  simple `/api/health` contract for smoke checks.
- Store operational recovery records in the local database so backup, restore,
  restart, and fault-injection drills are auditable.
- Keep local authentication simple and reversible: password-protected local
  sessions, secure cookie settings, CSRF protection for mutating requests, and
  no OAuth or external identity provider.
- Run security scans as local and CI gates using the existing Python, Node, and
  Docker toolchains.
- Use deterministic fault injectors rather than sleeping, randomness, or
  destructive operating-system pressure in tests.

## Goals

- Emit structured logs with request ids, correlation ids, component names,
  event types, status, latency, and redacted diagnostic fields.
- Expose health and readiness states for the database, providers, scheduler
  jobs, data freshness, risk locks, paper reconciliation, backup status, and
  security configuration.
- Add blocking system states for unavailable providers, stale data, required
  risk locks, failed reconciliation, backup integrity failure, and restart
  recovery gaps.
- Provide backup, restore, database-integrity, restart-recovery, and
  disaster-recovery procedures that preserve audit records and paper positions.
- Add local authentication, session expiry, secure cookie settings, CSRF
  protection, and safe unauthenticated states for sensitive dashboard and paper
  endpoints.
- Add CI/security checks for Python dependencies, Node dependencies, container
  configuration, secret patterns, static security issues, and forbidden broker
  or live-mode capability.
- Add deterministic fault-injection tests for provider loss, database
  contention, clock drift, disk pressure, and process restart.
- Document operational drills and expected failure responses.

## Non-Goals

- Schwab OAuth, account reads, order previews, order placement, token storage,
  or broker reconciliation.
- Public deployment, TLS termination, VPN, firewall rules, or Proxmox
  deployment automation.
- Production alert routing, pager integration, external metrics backends, or
  hosted log aggregation.
- Multi-user role-based access control.
- Replacing SQLite with PostgreSQL.
- Automatic trading, live-mode arming, market orders, or broker credentials.

## Threat And Failure Model

Milestone 10 must explicitly defend against:

- Secrets or secret-shaped values entering logs, API responses, frontend state,
  audit diagnostics, or generated fixtures.
- A stale, partial, unavailable, or conflicting data source allowing a paper
  approval, paper order, or position-management action to proceed.
- A restart losing the ability to reconstruct open approvals, working paper
  orders, fills, positions, risk locks, and recovery actions.
- Backup or restore producing a database with broken migrations, missing audit
  records, or inconsistent paper lifecycle state.
- Local dashboard access by an unauthenticated browser session.
- Mutating endpoints being called without an authenticated local session and a
  valid CSRF token.
- CI passing while dependency, static-security, container, or secret-scan checks
  report high-risk findings.

## Observability Requirements

Structured logs must be JSON-serializable records with at least:

- `timestamp`, `level`, `event`, `component`, `correlation_id`, and
  `request_id`.
- Request method, path template, status code, latency, and client category for
  API requests.
- Paper lifecycle action, source identifiers, transition status, and failure
  code for paper actions.
- Provider, job, freshness window, and policy version for data-state events.
- Recovery drill id, step, result, and database integrity status for recovery
  events.

Logs must never include raw cookies, authorization headers, passwords, CSRF
tokens, database URLs containing credentials, Schwab-shaped tokens, broker
account numbers, or arbitrary raw payloads.

All user-facing errors must include a stable code, correlation id, safe summary,
and safe remediation hint. Internal exception messages may be logged only after
redaction.

## Health And Blocking State Requirements

The backend must provide a detailed health/readiness contract that reports:

- Database connectivity and migration head status.
- Backup freshness and last integrity-check result.
- Market-data provider state and data freshness.
- Scheduler job state and last successful run for configured jobs.
- Risk-lock state and whether any required lock blocks new paper actions.
- Paper reconciliation state for open approvals, working orders, and open
  positions.
- Authentication/session configuration state.
- Security-scan metadata from the last local or CI verification run when
  available.

Critical states must block dependent paper actions with explicit failure codes.
Read-only dashboard views should continue to render safe unavailable states.

## Backup, Restore, And Recovery Requirements

Milestone 10 extends the existing SQLite backup helpers with:

- Backup metadata including source path, destination path, created timestamp,
  schema revision, row counts for audit and paper lifecycle tables, checksum,
  and correlation id.
- Database integrity checks using SQLite integrity checks and repository-level
  consistency checks.
- Restore validation that verifies migrations, audit history, paper approvals,
  orders, fills, positions, risk locks, and recovery events.
- A restart-recovery command or service entry point that prioritizes open paper
  positions, working orders, timed-out paper broker requests, and expiring
  approvals.
- Recovery drill fixtures that prove restored state can reconstruct the same
  paper lifecycle read models as the source database.

Backup and restore commands must refuse live-mode configuration and must not
delete an existing database unless the caller supplies an explicit destination
path or force flag in a test-only context.

## Local Authentication Requirements

Sensitive dashboard and paper endpoints must require a local authenticated
session. Required behavior:

- Login accepts a configured local password or password hash.
- Session cookies are HTTP-only, same-site, scoped to the application, and
  expire after a bounded idle and absolute lifetime.
- Mutating requests require a CSRF token tied to the session.
- Logout invalidates the session.
- Unauthenticated users receive safe 401 responses from sensitive APIs and a
  login view in the frontend.
- `/api/health` remains available for local smoke checks but must not leak
  sensitive diagnostics.

The implementation must not add OAuth, social login, external identity
providers, user registration, or persistent user profiles.

## CI And Security Requirements

The repository verification path must include:

- Python lint, type-check, tests, dependency audit, and static-security checks.
- Node lint, tests, build, and dependency audit.
- Secret scanning for tracked source, docs, fixtures, and generated OpenAPI
  contracts.
- Container configuration checks for non-root runtime, explicit health checks,
  no baked secrets, and paper-only defaults.
- Guard tests proving Schwab, broker credential, live order, and externally
  reachable deployment capability remain unavailable.

Security scan failures with high-risk findings must fail CI. Lower-risk or
environment-dependent findings may be documented with exact suppression files
and rationale.

## Fault-Injection Requirements

Fault-injection tests must cover:

- Provider loss and stale provider data.
- Database lock/contention during paper submission and recovery.
- Clock drift affecting approvals, previews, freshness windows, and sessions.
- Disk pressure or backup destination write failure.
- Process restart with open approvals, working orders, timed-out paper broker
  requests, and open positions.

Tests must be deterministic and bounded. They must not depend on random sleeps,
network access, destructive disk-filling, or external services.

## Frontend Requirements

The React app must add:

- Login, logout, session-expired, and unauthenticated states.
- Health and recovery status panels with component-level states and correlation
  ids.
- Backup/recovery drill status surfaces for local operator use.
- Clear blocking states on paper approval, paper order, and position screens
  when health or security state prevents actions.
- Safe error rendering that never displays secrets, raw headers, cookies, or
  unbounded backend exception text.

Frontend tests must prove sensitive screens are inaccessible when
unauthenticated and that blocking states disable mutating paper actions.

## Documentation Requirements

Create an operator runbook that documents:

- Local authentication setup and password rotation.
- Structured log fields and correlation-id lookup.
- Health/readiness states and actionability.
- Backup, restore, integrity check, and disaster-recovery drills.
- Restart-recovery procedure for open paper lifecycle state.
- Security scan commands and expected CI gates.
- Fault-injection scenarios and expected system behavior.
- Explicit non-capabilities: Schwab, broker credentials, live mode, public
  deployment, and automatic trading.

## Acceptance Criteria

Milestone 10 is complete when:

- Structured logs and API errors carry correlation ids and redacted fields.
- Secrets cannot enter logs, frontend responses, OpenAPI contracts, fixtures, or
  persisted diagnostics under tested secret-shaped inputs.
- Detailed health/readiness states block unsafe paper actions and keep read-only
  views safe.
- Backup, restore, database-integrity, restart-recovery, and disaster-recovery
  drills preserve audit history and paper positions.
- Local authentication and CSRF protection guard sensitive screens and mutating
  endpoints.
- CI/security checks cover dependencies, containers, secrets, static-security,
  and forbidden live/broker capability.
- Fault-injection tests cover provider loss, database contention, clock drift,
  disk pressure, and process restart.

## Explicitly Excluded Later Work

- Schwab credentials and OAuth remain Milestone 11.
- Schwab order contracts remain Milestone 12.
- Proxmox, PostgreSQL, TLS, VPN, firewall, and private deployment automation
  remain Milestone 13.
- Live-mode arming remains Milestone 14 and requires a separately approved
  specification.
