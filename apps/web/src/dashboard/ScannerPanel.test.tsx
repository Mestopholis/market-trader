import { cleanup, render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, expect, test, vi } from 'vitest'

import ScannerPanel from './ScannerPanel'
import type { CandidateListResponse } from './types'

const candidates: CandidateListResponse = {
  as_of: '2026-07-20T15:30:00Z',
  data_state: 'partial',
  candidates: [
    {
      candidate_key: 'candidate:aapl',
      symbol: 'AAPL',
      direction: 'bullish',
      strategy: 'bullish_breakout',
      score: '87.50',
      qualification_state: 'qualified',
      catalyst_state: 'confirmed',
      risk_state: 'warning',
      data_state: 'ready',
      observed_at: '2026-07-20T15:29:00Z',
      reason_codes: ['score.momentum'],
      source_keys: ['scanner:run:1'],
    },
    {
      candidate_key: 'candidate:msft',
      symbol: 'MSFT',
      direction: 'bearish',
      strategy: 'bearish_breakdown',
      score: '74.00',
      qualification_state: 'blocked',
      catalyst_state: 'unresolved',
      risk_state: 'blocked',
      data_state: 'stale',
      observed_at: '2026-07-20T15:00:00Z',
      reason_codes: ['risk.daily_loss'],
      source_keys: ['scanner:run:2'],
    },
  ],
  next_cursor: null,
  sources: [],
  warnings: [],
}

afterEach(() => {
  cleanup()
  vi.restoreAllMocks()
})

function response(body: unknown): Response {
  return new Response(JSON.stringify(body), { status: 200 })
}

test('renders scanner rows with states and score components', async () => {
  vi.spyOn(globalThis, 'fetch').mockResolvedValue(response(candidates))

  render(<ScannerPanel />)

  expect(await screen.findByRole('heading', { name: 'Scanner' })).toBeInTheDocument()
  expect(screen.getByText('AAPL')).toBeInTheDocument()
  expect(screen.getByText('87.50')).toBeInTheDocument()
  expect(screen.getByText('score.momentum')).toBeInTheDocument()
  expect(screen.getByText('stale')).toBeInTheDocument()
  expect(screen.queryByRole('button', { name: /approve|submit|buy|sell/i })).not.toBeInTheDocument()
})

test('filters candidate rows locally by symbol text', async () => {
  const user = userEvent.setup()
  vi.spyOn(globalThis, 'fetch').mockResolvedValue(response(candidates))

  render(<ScannerPanel />)
  await screen.findByText('AAPL')

  await user.type(screen.getByLabelText('Filter candidates'), 'msft')

  expect(screen.queryByText('AAPL')).not.toBeInTheDocument()
  expect(screen.getByText('MSFT')).toBeInTheDocument()
})

test('renders scanner unavailable state when request fails', async () => {
  vi.spyOn(globalThis, 'fetch').mockRejectedValue(new Error('offline'))

  render(<ScannerPanel />)

  expect(await screen.findByRole('alert')).toHaveTextContent('Scanner unavailable')
})
