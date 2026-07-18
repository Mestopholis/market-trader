# Milestone 1: Domain Storage and Audit Specification

Date: July 18, 2026
Status: Approved
Roadmap milestone: [Milestone 1: Domain storage and audit foundation](../development-roadmap.md)

## Purpose

Establish persistent, versioned domain storage for the paper-only Market Trader
foundation. This milestone creates the repository, migration, and audit boundaries
that later market-data, scanner, risk, paper-execution, and broker integrations
will consume.

Milestone 1 must not add external market providers, Schwab authentication,
broker account access, scanner decisions, approval actions, or order submission.

## Context

The current foundation is a local FastAPI backend, React frontend, Docker Compose
deployment, health endpoint, and paper-mode configuration. The application already
defaults to paper mode and rejects live mode. The storage milestone extends the
backend only far enough to persist and reconstruct domain records through explicit
repository APIs.

Development has moved from a Windows machine to macOS. The specification is
platform-neutral, but local setup and verification commands should use POSIX shell
commands and Docker Desktop for Mac where container verification is required.

## Goals

- Add a database layer compatible with local SQLite and future PostgreSQL.
- Add migration tooling and repeatable database initialization.
- Define versioned domain records required by the roadmap.
- Persist append-only audit events with correlation identifiers.
- Preserve UTC timestamp conventions.
- Expose repository interfaces that hide database implementation details from
  future domain services.
- Add focused tests for migrations, repositories, audit append behavior, and
  backup/restore fixtures.

## Non-Goals

- Market data provider connections.
- Scanner, scoring, catalyst, options, or risk calculations.
- Schwab OAuth, account data, order preview, order submission, or credentials.
- Frontend dashboard expansion beyond health or storage diagnostics needed for
  local verification.
- PostgreSQL deployment. The code must be compatible with PostgreSQL, but
  Proxmox/PostgreSQL deployment remains Milestone 13.
- Live trading, live arming, or any executable trading control.

## Design Approach

Use SQLAlchemy 2.x ORM models behind repository classes and Alembic migrations.
SQLite remains the local default database. SQLAlchemy is the recommended boundary
because it supports SQLite now, PostgreSQL later, typed model definitions,
transaction management, and migration integration without exposing database
details to domain services.

Alternative approaches considered:

- Raw SQL plus migration scripts. This is simple initially but increases
  duplicated mapping code and makes later PostgreSQL compatibility easier to
  accidentally break.
- SQLModel. This reduces boilerplate for simple APIs, but the project already
  uses Pydantic separately and does not need ORM models to double as HTTP
  schemas at this milestone.

## Storage Boundary

The backend owns database configuration, session lifecycle, migration execution,
and repository implementations. Application code outside the persistence package
must not import ORM models directly.

Expected backend package shape:

```text
apps/api/src/market_trader/
├── db/
│   ├── base.py
│   ├── engine.py
│   ├── session.py
│   └── migrations/
├── domain/
│   ├── ids.py
│   ├── time.py
│   └── models.py
└── repositories/
    ├── audit.py
    ├── symbols.py
    ├── market_data.py
    ├── decisions.py
    ├── orders.py
    └── config_versions.py
```

Exact file names may change during implementation if the implementation plan
justifies the change, but the boundary must remain: ORM and migration details
stay inside the persistence layer; future services use repositories.

## Database Configuration

The existing `MARKET_TRADER_DATABASE_URL` setting remains the source of truth.
The default local value should remain SQLite. Docker Compose may continue to use
a named volume mounted at `/data`.

Required behavior:

- Missing database files are created through the initialization workflow.
- Migrations are idempotent for a clean database.
- A failed migration stops startup or verification with an explicit error.
- Timestamps are stored in UTC.
- SQLite foreign-key enforcement is enabled for local development and tests.
- Database URLs and filesystem paths are not exposed in frontend responses if
  they may reveal host-specific details.

## Domain Records

Milestone 1 introduces schema and repository support for the following record
families. These records do not need full later-milestone behavior yet; they need
stable identity, timestamps, version fields, JSON payload space for future inputs,
and relationships that make reconstruction possible.

### Symbols and Instruments

Symbols represent tradable identifiers observed by the system. Instruments
represent the security or contract associated with a symbol at a point in time.

Required fields include:

- Stable internal identifier.
- Display symbol.
- Instrument type.
- Exchange or venue when known.
- Active/inactive status.
- First observed UTC timestamp.
- Last observed UTC timestamp.
- Versioned metadata payload.

### Market-Data Snapshots

Snapshots persist normalized observations from future providers and replay
fixtures. Milestone 1 stores the shape, not provider integrations.

Required fields include:

- Source identifier.
- Symbol or instrument reference.
- Observed UTC timestamp.
- Ingested UTC timestamp.
- Session date when known.
- Quality state.
- Configuration version reference when available.
- Immutable payload.

### Signals and Candidates

Signals and candidates persist future scanner outputs. Milestone 1 defines the
records so later deterministic decisions can be audited.

Required fields include:

- Strategy or rule version identifier.
- Symbol or instrument reference.
- Direction where applicable.
- Score or status fields that can remain null until later milestones.
- Input snapshot references.
- Explanation payload.
- Created UTC timestamp.

### Proposed Trades, Approvals, Orders, Fills, and Positions

Execution lifecycle records are required for later paper trading and broker
validation. Milestone 1 defines storage only and must not expose executable
actions.

Required fields include:

- Stable internal identifier.
- Status enum.
- Related candidate or proposal reference where applicable.
- Order intent payload.
- Broker or simulated-broker reference fields that remain null in Milestone 1.
- Created, updated, and terminal UTC timestamps where applicable.
- Audit correlation identifier.

### Risk Locks

Risk locks represent system states that can block future actions. Milestone 1
stores lock records without calculating risk.

Required fields include:

- Lock type.
- Status.
- Reason.
- Source event reference.
- Activated UTC timestamp.
- Cleared UTC timestamp when applicable.
- Clearing audit event reference.

### Journal Events

Journal events are append-only records used to reconstruct inputs, decisions,
user actions, and system state transitions.

Required fields include:

- Event identifier.
- Correlation identifier.
- Event type.
- Actor type, such as system, user, scheduler, replay, or provider adapter.
- Occurred UTC timestamp.
- Recorded UTC timestamp.
- Subject type and subject identifier.
- Causation event identifier when applicable.
- Immutable payload.
- Schema version.

### Configuration Versions

Configuration versions track deterministic rules and settings that affect later
decisions.

Required fields include:

- Configuration key.
- Semantic or monotonic version.
- Effective UTC timestamp.
- Retired UTC timestamp when applicable.
- Content hash.
- Immutable configuration payload.
- Creation audit event reference.

## Audit Requirements

The audit journal is append-only through normal application APIs.

Required behavior:

- Repository APIs may insert journal events but must not update or delete them.
- Database constraints should prevent accidental mutation where feasible.
- Tests must prove normal repository APIs cannot alter existing journal events.
- Every persisted decision-shaped record must carry either a correlation
  identifier or a direct audit event reference.
- Correlation identifiers must connect inputs, derived records, and user/system
  actions across tables.
- Payloads should be JSON objects with explicit schema versions.

SQLite cannot enforce every append-only property by itself. Implementation may
use a combination of restricted repository APIs, database triggers, and tests.
The implementation plan must choose the exact enforcement mechanism.

## Repository Contracts

Repositories should provide explicit methods for domain operations rather than
generic CRUD access. This keeps later milestones from bypassing audit and
versioning rules.

Minimum repository capabilities:

- Create and fetch symbols and instruments.
- Store and fetch market-data snapshots by symbol, source, and observed time.
- Create signals, candidates, proposed trades, risk locks, and configuration
  versions.
- Append and fetch journal events by identifier, correlation identifier, subject,
  and time range.
- Create order, fill, and position records for future paper workflows without
  contacting any broker.

Repository methods must run inside explicit transactions. If a repository method
creates a domain record that requires an audit event, both writes must commit or
roll back together.

## Migration Requirements

Alembic or equivalent migration tooling must support:

- Creating a clean local SQLite database from scratch.
- Applying all migrations in order.
- Verifying the database is at the expected head revision.
- Running migrations in CI.
- Preparing for PostgreSQL-compatible column types and constraints.

The first migration should create only Milestone 1 tables, indexes, constraints,
and any append-only enforcement needed by the audit journal.

## Backup and Restore Fixture

Milestone 1 must include a deterministic backup/restore fixture or script for the
local SQLite database.

Required behavior:

- Seed representative domain records.
- Create a backup artifact in a temporary test location.
- Restore into a clean database.
- Prove records, relationships, timestamps, and audit events reconstruct
  correctly after restore.

Production backup operations are not required until Milestone 10, but the local
fixture must establish the storage contract early.

## API Surface

Milestone 1 does not require new user-facing APIs. If implementation needs a
local diagnostic endpoint, it must be read-only, must not expose sensitive paths
or payloads, and must clearly report paper mode.

The existing `/api/health` contract may include a coarse database health state if
that is useful for verification. It must not expose raw database URLs.

## Testing Requirements

Automated tests must cover:

- Migration from an empty database.
- Database initialization against a temporary SQLite file.
- Repository create/fetch behavior for representative records.
- UTC timestamp persistence and retrieval.
- JSON payload persistence and schema-version fields.
- Transaction rollback when an audited write fails.
- Append-only journal behavior through normal repository APIs.
- Correlation identifier lookup across related records.
- Backup/restore fixture integrity.
- Existing health and paper-mode tests.

Static checks must continue to pass:

- Ruff.
- mypy.
- pytest.
- Frontend checks if any public contract changes.
- Docker Compose foundation verification.

## Documentation Requirements

Implementation must update or add documentation for:

- Local database initialization.
- Running migrations on macOS and in containers.
- Resetting a local development database.
- Running repository and migration tests.
- Backup/restore fixture usage.
- The fact that Milestone 1 remains paper-only and broker-free.

Documentation must avoid Schwab credential setup instructions.

## Security and Safety Requirements

- No broker credentials or credential placeholders may be added.
- No external provider API keys may be added.
- Audit payloads must be treated as application data, not executable
  instructions.
- Logs must not print full database URLs if they may include credentials in
  future PostgreSQL deployments.
- Live mode must remain rejected by configuration.
- Repository tests must not rely on network access.

## macOS Local Development Notes

Use the existing POSIX shell scripts and Docker Compose workflow on macOS:

```bash
cp .env.example .env
docker compose up --build -d
./scripts/verify-foundation.sh
```

For Python-only local development, use Python 3.12 or newer within the supported
project range and install backend dev dependencies from `apps/api`.

The implementation plan should prefer commands that work on macOS and Linux CI.
Avoid Windows-only shell syntax in scripts or documentation.

## Acceptance Criteria

Milestone 1 is complete when:

- A clean SQLite database can be migrated to the latest schema.
- Representative domain records can be stored and reconstructed through
  repositories.
- Journal events are append-only through normal application APIs.
- Correlation identifiers connect stored inputs, decisions, and actions.
- Backup/restore fixtures prove the representative dataset survives restore.
- Existing paper-only configuration remains enforced.
- Tests and static checks pass locally and in CI.
- Documentation explains local database setup and confirms that providers,
  Schwab access, scanner behavior, approvals, and orders remain unavailable.

## Explicitly Deferred

- Market calendar and scheduling behavior: Milestone 2.
- Provider-neutral market data and replay behavior: Milestone 3.
- Scanner and scoring logic: Milestone 4.
- Catalysts, news, and filings: Milestone 5.
- Options analysis: Milestone 6.
- Risk calculations and sizing: Milestone 7.
- Dashboard expansion: Milestone 8.
- Paper approvals and execution: Milestone 9.
- Reliability hardening and operational backup procedures: Milestone 10.
- Schwab OAuth and read-only integration: Milestone 11.
- Schwab order-contract validation: Milestone 12.
- Proxmox/PostgreSQL deployment: Milestone 13.
- Live-mode arming: Milestone 14.
