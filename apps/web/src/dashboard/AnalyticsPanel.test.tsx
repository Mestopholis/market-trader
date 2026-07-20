import { cleanup, render, screen } from '@testing-library/react'
import { afterEach, expect, test, vi } from 'vitest'

import AnalyticsPanel from './AnalyticsPanel'
import type { AnalyticsSummary } from './types'

const analytics: AnalyticsSummary = {
  as_of: '2026-07-20T15:30:00Z',
  data_state: 'ready',
  candidate_counts: { qualified: 3, blocked: 2 },
  strategy_mix: { bullish_breakout: 2 },
  block_reasons: { daily_loss: 1 },
  stale_counts: { scanner: 1 },
  risk_status_distribution: { blocked: 2, warning: 1 },
  sources: [],
  warnings: [],
}

afterEach(() => {
  cleanup()
  vi.restoreAllMocks()
})

test('renders analytics summaries for local deterministic data', async () => {
  vi.spyOn(globalThis, 'fetch').mockResolvedValue(new Response(JSON.stringify(analytics), { status: 200 }))

  render(<AnalyticsPanel />)

  expect(await screen.findByRole('heading', { name: 'Analytics' })).toBeInTheDocument()
  expect(screen.getByText('qualified')).toBeInTheDocument()
  expect(screen.getByText('bullish_breakout')).toBeInTheDocument()
  expect(screen.getByText('daily_loss')).toBeInTheDocument()
  expect(screen.getByText('scanner')).toBeInTheDocument()
  expect(screen.getByText('warning')).toBeInTheDocument()
})
