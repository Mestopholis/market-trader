# Milestone 11 Schwab OAuth And Read-Only Integration Runbook

Scope: local, paper-mode Schwab Market Data Production integration. This
runbook covers setup guardrails for OAuth, local secrets, token encryption,
fixture fallback, and Market Data-only verification. Accounts and Trading
Production remains pending until separately approved. This runbook does not
authorize broker order preview, order submission, cancel, replace, live mode,
public deployment, or automatic trading.

## Current Product Scope

Milestone 11 starts with Schwab Market Data Production only:

- OAuth authorization for the local operator.
- Read-only market data such as quotes, price history, option chains, and
  provider freshness where supported by the approved product.
- Local readiness states for configured, connected, expired, revoked,
  rate-limited, stale, and unavailable provider states.

Accounts and Trading Production is a later slice after separate Schwab approval:

- account identity;
- balances;
- positions;
- transactions; and
- account reconciliation.

Do not implement, configure, or test account reads until that app is approved.

## Schwab Portal Checklist

From the Schwab developer portal, confirm non-secret facts only:

- The Market Data Production app is `Ready for use`.
- The registered callback URL is exactly `https://127.0.0.1:8182`.
- The approved product is Market Data Production.
- OAuth authorization and token URLs are recorded in local implementation notes
  without copying client secrets.
- Market Data base URLs, endpoint paths, rate-limit guidance, token lifetime,
  and refresh behavior are verified from the authenticated Schwab portal before
  coding network clients.

Do not copy Schwab client secrets, access tokens, refresh tokens, or account
numbers into tracked files, test fixtures, issue comments, pull requests, or
chat.

## Local Environment

Use `.env` at the repository root for Docker Compose runs. Use `apps/api/.env`
only when running the API directly from `apps/api`.

Required local values for Market Data OAuth:

```bash
MARKET_TRADER_SCHWAB_MARKET_DATA_ENABLED=true
MARKET_TRADER_SCHWAB_CALLBACK_URL=https://127.0.0.1:8182
MARKET_TRADER_SCHWAB_CLIENT_ID=<local_client_id>
MARKET_TRADER_SCHWAB_CLIENT_SECRET=<local_client_secret>
MARKET_TRADER_SCHWAB_TOKEN_ENCRYPTION_KEY=<random_token_encryption_key>
```

Generate the token-encryption key locally:

```bash
python3 -c 'import secrets; print(secrets.token_urlsafe(32))'
```

The `.env` file is ignored by Git. Verify before committing:

```bash
git status --short --ignored .env
```

Expected output includes `!! .env`, never `A .env` or `M .env`.

## OAuth Callback

The local default callback is:

```text
https://127.0.0.1:8182
```

Implementation may use a local callback listener or a backend callback route,
but the URL sent to Schwab must exactly match the portal registration. A
callback mismatch should fail closed and keep Schwab state disconnected.

## Fixture Fallback

All automated tests and CI must run without Schwab credentials. Use mocked HTTP
transports and redacted recorded-contract fixtures. Live Schwab calls are local
operator smoke checks only and must never run in CI.

## Explicit Non-Capabilities

Milestone 11 Market Data does not provide:

- Accounts and Trading Production access;
- account identity, balances, positions, transactions, or reconciliation;
- Schwab order preview;
- Schwab order submission;
- broker cancel or replace;
- live-mode arming;
- automatic trading; or
- public callback exposure.

Any appearance of those capabilities in source, OpenAPI, fixtures, frontend
build output, or operational docs should be treated as a milestone regression
unless it is an explicit exclusion or forbidden-capability test.
