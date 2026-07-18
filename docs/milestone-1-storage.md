# Milestone 1 Storage

Milestone 1 provides persistent domain records and an append-only audit journal.
The application remains paper-only and broker-free. It does not connect to market
data providers or Schwab, run scanners, approve trades, submit orders, or expose
live-mode controls.

## Prerequisites

- Docker Desktop for Mac for the container workflow.
- Python 3.12 or 3.13 for local backend development.
- Node.js 20.19 or newer, or Node.js 22.12 or newer, for frontend verification.

## Local SQLite Setup

SQLite is the local default. From the repository root on macOS or Linux:

```bash
cd apps/api
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -e '.[dev]'
mkdir -p data
alembic upgrade head
```

The database URL continues to come from `MARKET_TRADER_DATABASE_URL`. Do not print
or return the full URL because future PostgreSQL URLs may contain credentials.

To verify the current migration revision:

```bash
cd apps/api
source .venv/bin/activate
alembic current
```

## Container Startup

The API container applies `alembic upgrade head` before starting FastAPI. Start and
verify the complete local stack from the repository root:

```bash
cp .env.example .env
docker compose up --build -d
./scripts/verify-foundation.sh
```

The health response reports only `database: ok` or `database: unavailable`; it
never returns the database URL.

## Tests

Run migration and audit coverage:

```bash
cd apps/api
source .venv/bin/activate
pytest tests/test_migrations.py tests/test_audit_repository.py -q
```

Run all backend checks:

```bash
cd apps/api
source .venv/bin/activate
pytest -q
ruff check src tests migrations
mypy src
```

Repository tests are deterministic, use temporary SQLite files, and require no
network access.

## Backup And Restore Fixture

`market_trader.db.backup` uses SQLite's backup API to create a consistent local
backup and restore it into a clean database. The automated fixture seeds a symbol
and its audit event, restores the database, and verifies identity, relationships,
payloads, and UTC timestamps:

```bash
cd apps/api
source .venv/bin/activate
pytest tests/test_backup_restore.py -q
```

This is a development fixture, not the production backup workflow planned for
Milestone 10.

## Reset Local Development Data

This removes the named Docker volume and all local development records stored in
it:

```bash
docker compose down
docker volume rm market-trader_market-trader-data
docker compose up --build -d
```

For Python-only development, remove `apps/api/data/market_trader.db` while the API
is stopped, then run `alembic upgrade head` again.

## Safety Boundary

Milestone 1 stores future-facing record shapes only. Provider keys, Schwab OAuth,
account access, scanner behavior, approval actions, broker order submission, and
live trading remain unavailable. `MARKET_TRADER_TRADING_MODE=live` continues to be
rejected at configuration startup.
