# Market Trader

[![CI](https://github.com/Mestopholis/market-trader/actions/workflows/ci.yml/badge.svg)](https://github.com/Mestopholis/market-trader/actions/workflows/ci.yml)

## Local foundation startup

1. Copy `.env.example` to `.env`.
2. Run `docker compose up --build -d`.
3. Open `http://127.0.0.1:8080`.
4. Run `./scripts/verify-foundation.sh`.
5. Stop with `docker compose down`.

The foundation is paper-only and contains no broker credentials or order submission.

## Milestone 1 storage

Milestone 1 adds versioned SQLite storage, Alembic migrations, audited repository
boundaries, and a local backup/restore fixture. API containers migrate the database
before startup. See the [Milestone 1 storage guide](docs/milestone-1-storage.md) for
macOS/Linux setup, verification, reset, and safety details.

## Milestone 2 market calendar

Milestone 2 adds deterministic XNYS regular-session state, versioned entry-window
decisions, schedule planning, and a read-only ET/CT status panel. It does not run
planned jobs or add providers, broker access, or order controls. See the
[Milestone 2 calendar guide](docs/milestone-2-calendar.md) for macOS startup,
test commands, calendar rules, and safety boundaries.

## Foundation boundary

The foundation milestone proves local startup, paper-only configuration, health-state visibility and CI. Market data, scanning, brokerage authentication, account access and order submission require separate reviewed implementation plans.

See the [development roadmap](docs/development-roadmap.md) for the ordered remaining milestones and their safety gates.
