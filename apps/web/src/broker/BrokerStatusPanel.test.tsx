import { cleanup, render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, expect, test, vi } from 'vitest'

import BrokerStatusPanel from './BrokerStatusPanel'
import type { SchwabBrokerStatus } from './types'

afterEach(() => {
  cleanup()
  vi.restoreAllMocks()
})

const connectedStatus: SchwabBrokerStatus = {
  configured: true,
  callback_url: 'https://127.0.0.1:8182',
  connection_state: 'connected',
  market_data_state: 'available',
  accounts_trading_configured: true,
  accounts_trading_state: 'disconnected',
  token: {
    token_id: 'schwab-market-data',
    product: 'market_data',
    status: 'active',
    token_type: 'Bearer',
    scope: 'api',
    access_token_expires_at: '2026-07-28T14:06:30Z',
    refresh_token_expires_at: null,
    encryption_key_id: '31605fe4e416f566',
    issued_at: '2026-07-28T13:36:30Z',
    refreshed_at: null,
    revoked_at: null,
    last_error_code: null,
    last_error_at: null,
    is_expired: false,
  },
  accounts_trading_token: null,
  last_market_data_refresh: {
    sync_key: 'manual-quote',
    data_kind: 'quote',
    status: 'completed',
    provider_state: 'available',
    observed_at: '2026-07-28T13:58:00Z',
    completed_at: '2026-07-28T13:58:01Z',
    correlation_id: 'corr-quote',
    is_stale: false,
  },
  actions: {
    oauth_start: true,
    refresh: true,
    revoke: true,
    accounts_oauth_start: true,
    accounts_refresh: false,
    accounts_revoke: false,
  },
}

test('renders connected read-only market data status and safe actions', async () => {
  const user = userEvent.setup()
  const onRefresh = vi.fn()
  const onRevoke = vi.fn()
  const onAccountsRefresh = vi.fn()
  const onAccountsRevoke = vi.fn()
  const onQuoteRefresh = vi.fn()

  render(
    <BrokerStatusPanel
      status={connectedStatus}
      onRefresh={onRefresh}
      onRevoke={onRevoke}
      onQuoteRefresh={onQuoteRefresh}
      onAccountsRefresh={onAccountsRefresh}
      onAccountsRevoke={onAccountsRevoke}
    />,
  )

  expect(screen.getByRole('heading', { name: 'Schwab Market Data' })).toBeInTheDocument()
  expect(screen.getByRole('heading', { name: 'Schwab Accounts and Trading' })).toBeInTheDocument()
  expect(screen.getByText('connected')).toBeInTheDocument()
  expect(screen.getByText('available')).toBeInTheDocument()
  expect(screen.getByText('disconnected')).toBeInTheDocument()
  expect(screen.getByText('2026-07-28 09:06 CT')).toBeInTheDocument()
  expect(screen.getByText('quote')).toBeInTheDocument()
  expect(document.body.textContent).not.toMatch(/access_token|client_secret|account number|position/i)
  expect(document.body.textContent).not.toMatch(/live mode|submit order/i)

  await user.click(screen.getByRole('button', { name: 'Refresh Schwab token' }))
  await user.click(screen.getByRole('button', { name: 'Revoke Schwab token' }))
  await user.click(screen.getByRole('button', { name: 'Refresh SPY quote' }))

  expect(onRefresh).toHaveBeenCalledOnce()
  expect(onRevoke).toHaveBeenCalledOnce()
  expect(onQuoteRefresh).toHaveBeenCalledOnce()
  expect(screen.getByRole('button', { name: 'Refresh Accounts token' })).toBeDisabled()
  expect(screen.getByRole('button', { name: 'Revoke Accounts token' })).toBeDisabled()
})

test('renders reconnect guidance when disconnected and disables unsafe actions', () => {
  render(
    <BrokerStatusPanel
      status={{
        ...connectedStatus,
        connection_state: 'disconnected',
        market_data_state: 'unknown',
        token: null,
        last_market_data_refresh: null,
        actions: {
          oauth_start: true,
          refresh: false,
          revoke: false,
          accounts_oauth_start: false,
          accounts_refresh: false,
          accounts_revoke: false,
        },
      }}
      onRefresh={vi.fn()}
      onRevoke={vi.fn()}
      onQuoteRefresh={vi.fn()}
      onAccountsRefresh={vi.fn()}
      onAccountsRevoke={vi.fn()}
    />,
  )

  expect(screen.getAllByText('disconnected')).toHaveLength(2)
  expect(screen.getByText('Use the local OAuth helper on https://127.0.0.1:8182.')).toBeInTheDocument()
  expect(screen.getByRole('button', { name: 'Refresh Schwab token' })).toBeDisabled()
  expect(screen.getByRole('button', { name: 'Revoke Schwab token' })).toBeDisabled()
  expect(screen.getByRole('button', { name: 'Refresh SPY quote' })).toBeDisabled()
})
