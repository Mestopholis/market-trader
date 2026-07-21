import { cleanup, render, screen } from '@testing-library/react'
import { afterEach, expect, test, vi } from 'vitest'

import App from './App'

afterEach(() => {
  cleanup()
  vi.restoreAllMocks()
})

const health = {
  status: 'ok',
  environment: 'local',
  trading_mode: 'paper',
  version: '0.1.0',
  database: 'ok',
}

const overview = {
  as_of: '2026-07-20T15:30:00Z',
  data_state: 'ready',
  paper_mode: true,
  market_state: 'entry_open',
  entry_allowed: true,
  sources: [
    {
      name: 'scanner',
      state: 'ready',
      version: 'scanner-policy-v1',
      observed_at: '2026-07-20T15:20:00Z',
      stable_key: 'scanner:latest',
      digest: 'scanner-digest',
    },
  ],
  warnings: [],
}

test('shows the dashboard overview on first load', async () => {
  vi.spyOn(globalThis, 'fetch').mockImplementation(async (input) => {
    const url = String(input)
    if (url.includes('/api/health')) {
      return new Response(JSON.stringify(health), { status: 200 })
    }
    if (url.includes('/api/auth/session')) {
      return new Response(JSON.stringify({ authenticated: true, username: 'operator' }), { status: 200 })
    }
    return new Response(JSON.stringify(overview), { status: 200 })
  })

  render(<App />)

  expect(await screen.findByRole('status')).toHaveTextContent('PAPER MODE')
  expect(screen.getByText(/No live orders can be submitted/i)).toBeInTheDocument()
  expect(await screen.findByRole('heading', { name: 'Market overview' })).toBeInTheDocument()
  expect(screen.getByText('scanner-policy-v1')).toBeInTheDocument()
  expect(screen.getAllByText(/ET \/ .*CT/).length).toBeGreaterThan(0)
  expect(screen.queryByRole('button', { name: /approve|preview|submit|buy|sell|execute/i }))
    .not
    .toBeInTheDocument()
})

test('shows a safe unavailable state when health fails', async () => {
  vi.spyOn(globalThis, 'fetch').mockRejectedValue(new Error('offline'))

  render(<App />)

  expect(await screen.findByRole('alert')).toHaveTextContent('Trading controls unavailable')
})

test('keeps paper state visible when the dashboard overview is unavailable', async () => {
  vi.spyOn(globalThis, 'fetch').mockImplementation(async (input) => {
    const url = String(input)
    if (url.includes('/api/health')) {
      return new Response(JSON.stringify(health), { status: 200 })
    }
    if (url.includes('/api/auth/session')) {
      return new Response(JSON.stringify({ authenticated: true, username: 'operator' }), { status: 200 })
    }
    return new Response(
      JSON.stringify({ message: 'dashboard unavailable' }),
      { status: 503 },
    )
  })

  render(<App />)

  expect(await screen.findByText('PAPER MODE')).toBeInTheDocument()
  expect(await screen.findByText('Market overview unavailable')).toBeInTheDocument()
  expect(screen.queryByText('Trading controls unavailable')).not.toBeInTheDocument()
})
