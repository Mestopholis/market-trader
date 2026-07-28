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

For local operator testing, start the HTTPS callback/helper page from the
repository root:

```bash
apps/api/.venv/bin/python scripts/start_schwab_helper.py
```

Then open:

```bash
open https://127.0.0.1:8182/
```

The helper generates a local self-signed certificate under ignored `data/`
storage, migrates the local SQLite database, and serves a small authenticated
connection page. Browser certificate warnings are expected for this local-only
self-signed certificate.

## Operations Status

The authenticated dashboard Operations view includes a Schwab Market Data panel
when the backend is available. It exposes only redacted read-only status:

- configuration state;
- OAuth connection state: unconfigured, disconnected, connected, expired, or
  revoked;
- market-data state: unknown, available, stale, rate-limited, unavailable, or
  quarantined;
- access-token expiry metadata;
- latest market-data refresh metadata; and
- refresh/revoke controls protected by local auth and CSRF.

The status endpoint is:

```text
GET /api/broker/schwab/status
```

It must never return client secrets, raw access tokens, raw refresh tokens,
account numbers, order controls, or live-mode controls.

Readiness also includes Schwab auth and market-data components when Schwab
Market Data is enabled. Disconnected, expired, revoked, stale, and rate-limited
states are surfaced as non-order-affecting local operator states; provider
unavailability can become blocking for broker-dependent future workflows.

## Local Smoke Check

After OAuth succeeds, a local operator may run a single read-only Market Data
smoke check, such as a quote request for `SPY`, using the stored token. Live
Schwab smoke checks are manual only and must not be added to CI or automated
test suites.

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

The Accounts and Trading Production app remains a later milestone. Do not add
account identity, balances, positions, transactions, reconciliation, or any
order-affecting behavior until that app is separately approved and a new plan is
reviewed.

Any appearance of those capabilities in source, OpenAPI, fixtures, frontend
build output, or operational docs should be treated as a milestone regression
unless it is an explicit exclusion or forbidden-capability test.
