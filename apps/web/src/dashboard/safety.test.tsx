import { cleanup, render, screen } from '@testing-library/react'
import { afterEach, expect, test, vi } from 'vitest'

import DashboardShell from './DashboardShell'

afterEach(() => {
  cleanup()
  vi.restoreAllMocks()
})

function response(body: unknown): Response {
  return new Response(JSON.stringify(body), { status: 200 })
}

test('dashboard shell exposes no executable trading controls or copy', async () => {
  vi.spyOn(globalThis, 'fetch').mockResolvedValue(
    response({
      as_of: '2026-07-20T15:30:00Z',
      data_state: 'unavailable',
      paper_mode: true,
      market_state: 'unavailable',
      entry_allowed: false,
      sources: [],
      warnings: [],
      candidates: [],
      events: [],
      checks: [],
      active_locks: [],
      tax_disclaimer: 'Informational estimate only; not tax advice.',
      candidate_counts: {},
      strategy_mix: {},
      block_reasons: {},
      stale_counts: {},
      risk_status_distribution: {},
    }),
  )

  render(<DashboardShell />)

  expect(await screen.findByText('PAPER MODE')).toBeInTheDocument()
  const forbidden = /approve|preview|submit|buy|sell|execute|connect broker|arm live|clear lock/i
  expect(screen.queryByRole('button', { name: forbidden })).not.toBeInTheDocument()
  expect(screen.queryByRole('link', { name: forbidden })).not.toBeInTheDocument()
  expect(document.body.textContent).not.toMatch(/connect broker|arm live|clear lock/i)
})
