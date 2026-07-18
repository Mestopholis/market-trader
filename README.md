# Market Trader

[![CI](https://github.com/Mestopholis/market-trader/actions/workflows/ci.yml/badge.svg)](https://github.com/Mestopholis/market-trader/actions/workflows/ci.yml)

## Local foundation startup

1. Copy `.env.example` to `.env`.
2. Run `docker compose up --build -d`.
3. Open `http://127.0.0.1:8080`.
4. Run `./scripts/verify-foundation.sh`.
5. Stop with `docker compose down`.

The foundation is paper-only and contains no broker credentials or order submission.

## Foundation boundary

The foundation milestone proves local startup, paper-only configuration, health-state visibility and CI. Market data, scanning, brokerage authentication, account access and order submission require separate reviewed implementation plans.

See the [development roadmap](docs/development-roadmap.md) for the ordered remaining milestones and their safety gates.
