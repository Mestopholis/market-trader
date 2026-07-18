import { act, cleanup, render, screen } from '@testing-library/react'
import { afterEach, expect, test, vi } from 'vitest'

import type { MarketStateResponse } from './api'
import MarketStatus from './MarketStatus'

function marketState(overrides: Partial<MarketStateResponse> = {}): MarketStateResponse {
  return {
    market_state: 'entry_open',
    entry_allowed: true,
    calendar: 'XNYS',
    policy_version: 'entry-window-v1',
    observed_at: '2026-07-20T15:30:00Z',
    valid_until: '2026-07-20T15:31:00Z',
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
    ...overrides,
  }
}

function response(body: MarketStateResponse): Response {
  return new Response(JSON.stringify(body), { status: 200 })
}

afterEach(() => {
  cleanup()
  vi.useRealTimers()
  vi.restoreAllMocks()
})

test('shows loading before the first market state response', () => {
  vi.spyOn(globalThis, 'fetch').mockReturnValue(new Promise(() => {}))

  render(<MarketStatus />)

  expect(screen.getByText('Checking market schedule...')).toBeInTheDocument()
})

test('shows market state with Eastern and Central values', async () => {
  vi.spyOn(globalThis, 'fetch').mockResolvedValue(response(marketState()))

  render(<MarketStatus />)

  expect(await screen.findByText('Entry window open')).toBeInTheDocument()
  expect(screen.getByRole('heading', { name: 'Market status' })).toBeInTheDocument()
  expect(screen.getAllByText(/ET \/ .*CT/).length).toBeGreaterThan(0)
})

test('calls out an early close and adjusted entry end', async () => {
  vi.spyOn(globalThis, 'fetch').mockResolvedValue(
    response(
      marketState({
        observed_at: '2026-11-27T16:00:00Z',
        valid_until: '2026-11-27T16:01:00Z',
        market_open: '2026-11-27T14:30:00Z',
        market_close: '2026-11-27T18:00:00Z',
        entry_window_open: '2026-11-27T14:45:00Z',
        entry_window_close: '2026-11-27T17:30:00Z',
        next_transition: '2026-11-27T17:30:00Z',
        is_early_close: true,
      }),
    ),
  )

  render(<MarketStatus />)

  expect(await screen.findByText('Early close')).toBeInTheDocument()
  expect(screen.getAllByText(/12:30 PM ET/).length).toBeGreaterThan(0)
})

test('shows a fail-closed unavailable state when the request fails', async () => {
  vi.spyOn(globalThis, 'fetch').mockRejectedValue(new Error('offline'))

  render(<MarketStatus />)

  expect(await screen.findByText('Market schedule unavailable')).toBeInTheDocument()
  expect(screen.queryByRole('button')).not.toBeInTheDocument()
})

test('expires a snapshot immediately after valid_until', async () => {
  vi.useFakeTimers()
  vi.setSystemTime(new Date('2026-07-20T15:30:00Z'))
  vi.spyOn(globalThis, 'fetch').mockResolvedValue(
    response(marketState({ valid_until: '2026-07-20T15:30:10Z' })),
  )

  render(<MarketStatus />)
  await act(async () => {})
  expect(screen.getByText('Entry window open')).toBeInTheDocument()

  await act(async () => {
    await vi.advanceTimersByTimeAsync(10_001)
  })

  expect(screen.getByText('Market schedule unavailable')).toBeInTheDocument()
})

test('refreshes market state every thirty seconds', async () => {
  vi.useFakeTimers()
  vi.setSystemTime(new Date('2026-07-20T15:30:00Z'))
  const fetchMock = vi.spyOn(globalThis, 'fetch').mockResolvedValue(response(marketState()))

  render(<MarketStatus />)
  await act(async () => {})

  await act(async () => {
    await vi.advanceTimersByTimeAsync(30_000)
  })

  expect(fetchMock).toHaveBeenCalledTimes(2)
})

test('aborts the active request when unmounted', () => {
  const fetchMock = vi.spyOn(globalThis, 'fetch').mockReturnValue(new Promise(() => {}))
  const { unmount } = render(<MarketStatus />)
  const request = fetchMock.mock.calls[0][1]

  unmount()

  expect(request?.signal?.aborted).toBe(true)
})
