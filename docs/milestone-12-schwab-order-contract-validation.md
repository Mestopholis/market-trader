# Milestone 12: Schwab Order-Contract Validation

Milestone 12 adds Schwab Accounts and Trading OAuth readiness plus validation-only
Schwab order-contract translation for the existing paper workflow.

This milestone does not submit orders to Schwab, does not expose account numbers,
does not read live positions, and does not arm live mode.

## Configuration

Keep the Schwab callback URL set to the local helper:

```bash
MARKET_TRADER_SCHWAB_CALLBACK_URL=https://127.0.0.1:8182
```

Market Data and Accounts and Trading use separate Schwab apps and separate stored
tokens:

```bash
MARKET_TRADER_SCHWAB_MARKET_DATA_ENABLED=true
MARKET_TRADER_SCHWAB_CLIENT_ID=<schwab_market_data_client_id>
MARKET_TRADER_SCHWAB_CLIENT_SECRET=<schwab_market_data_client_secret>

MARKET_TRADER_SCHWAB_ACCOUNTS_TRADING_ENABLED=true
MARKET_TRADER_SCHWAB_ACCOUNTS_TRADING_CLIENT_ID=<schwab_accounts_trading_client_id>
MARKET_TRADER_SCHWAB_ACCOUNTS_TRADING_CLIENT_SECRET=<schwab_accounts_trading_client_secret>

MARKET_TRADER_SCHWAB_TOKEN_ENCRYPTION_KEY=<random_token_encryption_key>
```

## Connecting Accounts and Trading

Start the local stack and the helper:

```bash
docker compose up --build
apps/api/.venv/bin/python scripts/start_schwab_helper.py
```

Open `https://127.0.0.1:8182`, choose `Accounts and Trading`, and connect with
the Schwab brokerage-login credentials for the account authorized in the
Accounts and Trading Production app.

The dashboard will show a separate `Schwab Accounts and Trading` panel. A
connected state means the OAuth dependency exists for validation checks; it does
not mean live trading is enabled.

## Validation Scope

The Schwab contract builder translates only these paper intents:

- long shares
- bull call debit spreads
- bear put debit spreads

The builder rejects unsupported strategies, live-submission flags, non-limit
orders, and non-day duration. Generated contracts are marked
`validation_only=true` and `submit_capable=false`.

## Safety Checks

- Market Data and Accounts and Trading tokens are stored independently.
- OAuth state includes the requested Schwab product to prevent callback
  cross-use between apps.
- Readiness includes a blocking `schwab_accounts_trading` component when the
  Accounts and Trading app is enabled but disconnected.
- The frontend exposes token refresh and revoke controls only. It does not show
  account identity, balances, positions, order placement, or live-mode controls.
