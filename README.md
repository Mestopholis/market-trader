# Market Trader

## Local foundation startup

1. Copy `.env.example` to `.env`.
2. Run `docker compose up --build -d`.
3. Open `http://127.0.0.1:8080`.
4. Run `./scripts/verify-foundation.sh`.
5. Stop with `docker compose down`.

The foundation is paper-only and contains no broker credentials or order submission.
