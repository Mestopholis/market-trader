import { cleanup, render, screen } from '@testing-library/react'
import { afterEach, expect, test, vi } from 'vitest'

import JournalPanel from './JournalPanel'
import type { JournalEventListResponse } from './types'

const journal: JournalEventListResponse = {
  as_of: '2026-07-20T15:30:00Z',
  data_state: 'ready',
  events: [
    {
      event_key: 'journal:1',
      event_type: 'risk_decision.recorded',
      occurred_at: '2026-07-20T15:30:00Z',
      correlation_id: 'corr:1',
      actor: 'system',
      source_key: 'risk:decision:1',
      payload_summary: { status: 'blocked' },
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

test('renders journal events without secret payload fields', async () => {
  vi.spyOn(globalThis, 'fetch').mockResolvedValue(new Response(JSON.stringify(journal), { status: 200 }))

  render(<JournalPanel />)

  expect(await screen.findByRole('heading', { name: 'Journal' })).toBeInTheDocument()
  expect(screen.getByText('risk_decision.recorded')).toBeInTheDocument()
  expect(screen.getByText('corr:1')).toBeInTheDocument()
  expect(screen.getByText('risk:decision:1')).toBeInTheDocument()
  expect(screen.queryByText(/token|secret|password/i)).not.toBeInTheDocument()
})
