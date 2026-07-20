import { cleanup, render, screen } from '@testing-library/react'
import { afterEach, expect, test, vi } from 'vitest'

import RiskPanel from './RiskPanel'
import type { RiskSummary } from './types'

const risk: RiskSummary = {
  as_of: '2026-07-20T15:30:00Z',
  data_state: 'partial',
  latest_decision_key: 'risk:decision:1',
  status: 'blocked',
  checks: [{ code: 'daily_loss', severity: 'block', message: 'Daily loss lock', source_keys: ['lock:1'] }],
  active_locks: ['daily_loss', 'manual_operator_hold'],
  tax_disclaimer: 'Informational estimate only; not tax advice.',
  sources: [],
  warnings: [],
}

afterEach(() => {
  cleanup()
  vi.restoreAllMocks()
})

test('renders risk checks, locks, decision key, and tax disclaimer', async () => {
  vi.spyOn(globalThis, 'fetch').mockResolvedValue(new Response(JSON.stringify(risk), { status: 200 }))

  render(<RiskPanel />)

  expect(await screen.findByRole('heading', { name: 'Risk' })).toBeInTheDocument()
  expect(screen.getByText('risk:decision:1')).toBeInTheDocument()
  expect(screen.getByText('blocked')).toBeInTheDocument()
  expect(screen.getByText('daily_loss')).toBeInTheDocument()
  expect(screen.getByText('manual_operator_hold')).toBeInTheDocument()
  expect(screen.getByText(/not tax advice/i)).toBeInTheDocument()
})
