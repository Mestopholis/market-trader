# Milestone 11 Schwab OAuth And Read-Only Integration Specification

Date: July 26, 2026
Status: Draft specification
Depends on: Milestone 10
Roadmap milestone: 11

## Purpose

Milestone 11 connects approved Schwab developer applications to the local paper
system for read-only market and account information. Schwab approval may arrive
one product at a time, so the milestone is sequenced in two slices: Market Data
Production first, then Accounts and Trading Production after separate approval.
It adds OAuth authorization, encrypted token storage, read-only Schwab adapters,
broker-data freshness state, and, after the account app is approved, account
identity verification and reconciliation views.

The milestone must keep all order paths disabled. Schwab order preview, order
submission, cancel, replace, live-mode arming, public deployment, and automatic
trading remain unavailable.

## Operator Inputs Required Before Implementation

- Confirm the Market Data Production app is `Ready for use` in the developer
  portal before implementing the first slice.
- Confirm the Accounts and Trading Production app separately before
  implementing account, balance, position, transaction, or reconciliation
  behavior.
- Confirm the exact callback URL registered in Schwab. The default local design
  is `https://127.0.0.1:8182`.
- Export local-only client configuration through environment variables. Do not
  commit credentials or paste them into chats, docs, logs, fixtures, or tests.
- Export a local token-encryption key generated for this app instance.
- Confirm whether the approved Schwab product exposes trading/order endpoints.
  Even if it does, this milestone must not request, store, call, render, or test
  order submission capability.
- Capture current Schwab OAuth token lifetime, refresh behavior, product scopes,
  base URLs, and rate-limit guidance from the authenticated Schwab developer
  portal before coding endpoint clients.

## Approved Design Decisions

- Treat Schwab as a read-only provider implementation behind existing market
  data and broker-read interfaces.
- Store Schwab credentials only in backend configuration and encrypted database
  rows; never expose raw tokens to frontend, logs, fixtures, OpenAPI examples,
  or language-model-accessible text.
- Use OAuth authorization-code flow with an operator-initiated local callback.
- Keep OAuth recovery fail-closed: expired, revoked, mismatched, or missing
  tokens create authentication locks and broker-dependent unavailable states.
- Verify account identity before using any account, balance, position, or
  transaction data.
- Persist bounded broker observations and reconciliation summaries, not raw
  Schwab payload dumps.
- Continue supporting deterministic fixture and replay providers as first-class
  alternatives to Schwab.
- Use recorded contract fixtures for Schwab responses when Schwab does not
  provide a stable sandbox.
- Preserve paper mode through startup, restart, token refresh, revocation,
  account mismatch, and recovery flows.

## Goals

- Add configuration for Schwab client id, client secret, callback URL, product
  mode, expected account identity, and token-encryption key.
- Add OAuth start, callback, refresh, revoke, and status behavior protected by
  local authentication.
- Persist encrypted Schwab access and refresh tokens with issued-at,
  expires-at, rotation, revocation, and audit metadata.
- First slice: add read-only Schwab market-data adapters for quotes, candles,
  option chains, provider status, and market-data freshness using existing
  normalized contracts.
- Second slice, after Accounts and Trading Production approval: add read-only
  account adapters for account identity, balances, positions, and transactions
  needed for reconciliation and risk visibility.
- Add authentication, rate-limit, provider-stale, and provider-unavailable locks
  to readiness in the first slice. Add account-mismatch locks in the second
  slice.
- Add backend and frontend views showing market-data connection status and
  freshness first. Add account identity confirmation, balances, positions, and
  reconciliation summaries only after the account app is approved.
- Add security and forbidden-capability tests proving no order submission,
  preview, cancel, replace, or live-mode paths are introduced.
- Document local setup, portal verification, callback registration, token
  rotation, revocation recovery, and safe fallback to fixtures.

## Non-Goals

- Schwab order preview, order placement, cancel, replace, or saved orders.
- Live-mode arming or any live-account order submission path.
- Automatic trading, automatic reauthentication, or unattended credential
  recovery.
- Public deployment, externally reachable callbacks, TLS termination, VPN,
  firewall, or Proxmox changes.
- OAuth for users other than the single local operator.
- Replacing deterministic fixtures or paper broker behavior.
- Redistributing market data or building commercial/multi-user access.

## Security Requirements

Schwab configuration must be backend-only:

- `MARKET_TRADER_SCHWAB_MARKET_DATA_ENABLED`
- `MARKET_TRADER_SCHWAB_CLIENT_ID`
- `MARKET_TRADER_SCHWAB_CLIENT_SECRET`
- `MARKET_TRADER_SCHWAB_CALLBACK_URL`
- `MARKET_TRADER_SCHWAB_TOKEN_ENCRYPTION_KEY`

The account slice will add account-specific configuration, such as an expected
account hash, after Accounts and Trading Production is separately approved.

Credential values must never be committed, logged, returned by APIs, embedded
in OpenAPI examples, rendered in React, or written into fixtures. Logs may
include redacted connection state, token age buckets, safe reason codes, and
correlation ids only.

Token storage must encrypt token material at rest. Token rows must include
created, refreshed, expires, revoked, and last-error metadata so operators can
diagnose state without inspecting secrets.

OAuth routes must require local session authentication except the callback
handler, which must validate signed state and nonce values created by the
authenticated start route. CSRF protection remains required for local mutating
control routes.

## OAuth Requirements

The backend must expose:

- `POST /api/broker/schwab/oauth/start`
- `GET /api/broker/schwab/oauth/callback`
- `POST /api/broker/schwab/oauth/refresh`
- `POST /api/broker/schwab/oauth/revoke`
- `GET /api/broker/schwab/status`

The start route creates a short-lived signed OAuth state record and returns the
Schwab authorization URL to the authenticated operator. The callback validates
state, exchanges the authorization code, stores encrypted tokens, audits the
event, verifies account identity, and redirects to a safe local broker-status
view.

Token refresh must happen only in backend service code. If refresh fails because
credentials are expired, revoked, mismatched, malformed, or rate-limited, the
system must set a broker-authentication lock and keep paper mode active.

Revocation clears active token use, records an audit event, and makes
broker-dependent views unavailable until the operator reauthenticates.

## Read-Only Broker Data Requirements

Schwab market data may satisfy existing provider contracts:

- quotes
- candles or price history
- option chains
- provider health

After Accounts and Trading Production is separately approved, Schwab account
data may satisfy new broker-read contracts:

- account identity
- cash and buying-power style balances
- positions
- transactions and activity needed for reconciliation

Account identifiers must be hashed or otherwise reduced before persistence and
display. Raw account numbers must not appear in logs, frontend state, tests, or
fixtures.

All Schwab data must carry source, observed time, ingestion time, freshness
state, provider state, and stable source keys. Stale or unavailable broker data
must not be silently reused for risk or reconciliation decisions.

## Deferred Reconciliation Requirements

Milestone 11 does not place orders. Reconciliation is deferred until Accounts
and Trading Production is separately approved. That later slice must compare
read-only Schwab account state with local paper positions and working paper
orders:

- show unmatched broker positions as informational reconciliation warnings;
- show local paper positions missing from Schwab as expected while still in
  paper-only operation;
- block broker-dependent future actions when account identity changes;
- record reconciliation summaries in the audit journal; and
- never mutate paper orders or positions based solely on Schwab reads.

## Frontend Requirements

The operations area must show:

- Schwab connection state;
- whether OAuth is configured, connected, expired, revoked, or blocked;
- account identity verification state using a redacted fingerprint only;
- last successful market-data and account-data refresh times;
- provider freshness and rate-limit states;
- read-only balances, positions, and reconciliation summaries only after
  Accounts and Trading Production is separately approved;
- reauthenticate and revoke controls protected by local auth and CSRF.

The UI must not render buttons, labels, routes, request builders, or hidden
controls for live mode, order preview, order submit, cancel, replace, or broker
order editing.

## Testing Requirements

Milestone 11 must add tests for:

- OAuth state signing, expiry, replay rejection, and callback validation.
- Token encryption, refresh, revocation, metadata, and redaction.
- Schwab HTTP client request construction with mocked HTTP transport.
- First slice normalization of quote, candle, and option-chain responses from
  recorded fixtures.
- Later account-slice normalization of account, balance, position, and
  transaction responses from recorded fixtures after Accounts and Trading
  Production is approved.
- Provider stale, unavailable, rate-limited, unauthorized, and malformed
  responses.
- Account identity mismatch creating a blocking state after the account slice is
  approved.
- OpenAPI, source, frontend, fixtures, and docs scans proving no Schwab order
  submission, order preview, cancel, replace, live mode, or raw credential
  capability is exposed.
- Frontend broker-status rendering and absence of trading controls.
- Full local verification with deterministic fixtures when Schwab credentials
  are absent.

## Exit Criteria

- An authenticated local operator can connect and disconnect Schwab OAuth.
- Tokens are encrypted at rest, refreshable when valid, revocable, and never
  leaked through logs, APIs, OpenAPI, fixtures, or frontend state.
- Read-only Schwab market data can be normalized into existing read models with
  explicit timestamps and freshness.
- Missing credentials, expired tokens, revoked tokens, stale data, rate limits,
  and provider outages fail closed.
- After the account slice is approved, read-only Schwab account data can be
  normalized into new read models and account identity mismatch fails closed.
- Paper mode remains active after OAuth connect, refresh, revocation, restart,
  account mismatch, and recovery.
- Every order-affecting Schwab capability remains absent and covered by
  forbidden-capability tests.
- Operator documentation explains portal setup, callback registration, local
  secret handling, reauthentication, revocation, and fixture fallback.

## References To Verify During Implementation

- Schwab Developer Portal: `https://developer.schwab.com/`
- Schwab Trader API product page: `https://developer.schwab.com/products/trader-api--individual`
- Schwab Market Data API product page: `https://developer.schwab.com/products/market-data-api`
- Schwab developer login portal: `https://devportal.schwab.com/`

The authenticated developer portal is the source of truth for exact OAuth,
endpoint, rate-limit, and product-scope details. If portal details differ from
this draft, update this specification before implementation.
