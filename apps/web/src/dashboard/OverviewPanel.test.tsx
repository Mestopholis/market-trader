import { cleanup, render, screen } from '@testing-library/react'
import { afterEach, expect, test, vi } from 'vitest'

import OverviewPanel from './OverviewPanel'
import type { DashboardOverview } from './types'

const overview: DashboardOverview = {
  as_of: '2026-07-20T15:30:00Z',
  data_state: 'partial',
  paper_mode: true,
  market_state: 'entry_open',
  entry_allowed: true,
  sources: [
    {
      name: 'scanner',
      state: 'stale',
      version: 'scanner-policy-v1',
      observed_at: '2026-07-20T15:10:00Z',
      stable_key: 'scanner:latest',
      digest: null,
    },
    {
      name: 'risk',
      state: 'ready',
      version: 'risk-policy-v1',
      observed_at: '2026-07-20T15:29:00Z',
      stable_key: 'risk:latest',
      digest: 'risk-digest',
    },
  ],
  warnings: [
    {
      code: 'scanner.stale',
      severity: 'warning',
      message: 'Scanner data is stale',
      source_keys: ['scanner:latest'],
    },
  ],
}

afterEach(() => {
  cleanup()
  vi.restoreAllMocks()
})

function response(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), { status })
}

test('renders overview source states and market timestamps', async () => {
  vi.spyOn(globalThis, 'fetch').mockResolvedValue(response(overview))

  render(<OverviewPanel />)

  expect(await screen.findByRole('heading', { name: 'Market overview' })).toBeInTheDocument()
  expect(screen.getByText('entry_open')).toBeInTheDocument()
  expect(screen.getByText('scanner-policy-v1')).toBeInTheDocument()
  expect(screen.getByText('stale')).toBeInTheDocument()
  expect(screen.getByText('Scanner data is stale')).toBeInTheDocument()
  expect(screen.getAllByText(/ET \/ .*CT/).length).toBeGreaterThan(0)
  expect(screen.queryByRole('button')).not.toBeInTheDocument()
})

test('renders overview unavailable state when the request fails', async () => {
  vi.spyOn(globalThis, 'fetch').mockRejectedValue(new Error('offline'))

  render(<OverviewPanel />)

  expect(await screen.findByRole('alert')).toHaveTextContent('Market overview unavailable')
})
