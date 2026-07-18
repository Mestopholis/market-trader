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

const marketState = {
  market_state: 'entry_open',
  entry_allowed: true,
  calendar: 'XNYS',
  policy_version: 'entry-window-v1',
  observed_at: '2026-07-20T15:30:00Z',
  valid_until: '2027-07-20T15:31:00Z',
  next_transition: '2026-07-20T19:30:00Z',
  session_date: '2026-07-20',
  market_open: '2026-07-20T13:30:00Z',
  market_close: '2026-07-20T20:00:00Z',
  entry_window_open: '2026-07-20T13:45:00Z',
  entry_window_close: '2026-07-20T19:30:00Z',
  is_early_close: false,
  next_session_date: '2026-07-21',
  next_session_open: '2026-07-21T13:30:00Z',
  calendar_timezone: 'America/New_York',
  display_timezone: 'America/Chicago',
}

test('shows an unmistakable paper mode banner', async () => {
  vi.spyOn(globalThis, 'fetch').mockImplementation(async (input) => {
    const url = String(input)
    const body = url.includes('/api/health') ? health : marketState
    return new Response(JSON.stringify(body), { status: 200 })
  })

  render(<App />)

  expect(await screen.findByRole('status')).toHaveTextContent('PAPER MODE')
  expect(screen.getByText(/No live orders can be submitted/i)).toBeInTheDocument()
  expect(screen.getByText('Database')).toBeInTheDocument()
  expect(screen.getByText('ok')).toBeInTheDocument()
  expect(await screen.findByText('Entry window open')).toBeInTheDocument()
  expect(screen.getByRole('heading', { name: 'Market status' })).toBeInTheDocument()
  expect(screen.getAllByText(/ET \/ .*CT/).length).toBeGreaterThan(0)
  expect(screen.queryByRole('button')).not.toBeInTheDocument()
})

test('shows a safe unavailable state when health fails', async () => {
  vi.spyOn(globalThis, 'fetch').mockRejectedValue(new Error('offline'))

  render(<App />)

  expect(await screen.findByRole('alert')).toHaveTextContent('Trading controls unavailable')
})

test('keeps paper and health state visible when the calendar is unavailable', async () => {
  vi.spyOn(globalThis, 'fetch').mockImplementation(async (input) => {
    if (String(input).includes('/api/health')) {
      return new Response(JSON.stringify(health), { status: 200 })
    }
    return new Response(
      JSON.stringify({
        market_state: 'unavailable',
        entry_allowed: false,
        error_code: 'market_calendar_unavailable',
      }),
      { status: 503 },
    )
  })

  render(<App />)

  expect(await screen.findByText('PAPER MODE')).toBeInTheDocument()
  expect(await screen.findByText('Market schedule unavailable')).toBeInTheDocument()
  expect(screen.getByText('Database')).toBeInTheDocument()
  expect(screen.queryByText('Trading controls unavailable')).not.toBeInTheDocument()
})
