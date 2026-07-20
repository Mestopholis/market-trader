import { cleanup, render, screen } from '@testing-library/react'
import { afterEach, expect, test, vi } from 'vitest'

import PaperPositionsPanel from './PaperPositionsPanel'

afterEach(() => {
  cleanup()
  vi.restoreAllMocks()
})

function response(body: unknown): Response {
  return new Response(JSON.stringify(body), { status: 200 })
}

test('renders paper position P/L facts, stops, targets, expiration, and assignment warnings', async () => {
  vi.spyOn(globalThis, 'fetch').mockResolvedValue(response({
    paper_mode: true,
    positions: [
      {
        position_key: 'position:msft',
        symbol: 'MSFT',
        status: 'open',
        quantity: 2,
        average_price: '1.25',
        realized_pl: '0.00',
        unrealized_pl: '42.50',
        source_order_ids: ['order:msft'],
        source_fill_ids: ['fill:msft'],
        risk_decision_key: 'risk:msft',
        opened_at: '2026-07-20T15:30:00Z',
        updated_at: '2026-07-20T15:35:00Z',
        closed_at: null,
        exit_rules: {
          stop_loss: '0.70',
          target: '2.20',
          expires_at: '2026-08-21',
        },
        broker_reference: null,
      },
      {
        position_key: 'position:assign',
        symbol: 'AAPL',
        status: 'assigned',
        quantity: 1,
        average_price: '0.90',
        realized_pl: '-12.00',
        unrealized_pl: '0.00',
        source_order_ids: ['order:assign'],
        source_fill_ids: ['fill:assign'],
        risk_decision_key: 'risk:assign',
        opened_at: '2026-07-20T15:30:00Z',
        updated_at: '2026-07-20T15:36:00Z',
        closed_at: null,
        exit_rules: {},
        broker_reference: null,
      },
    ],
  }))

  render(<PaperPositionsPanel />)

  expect(await screen.findByRole('heading', { name: 'Paper positions' })).toBeInTheDocument()
  expect(screen.getByText('MSFT')).toBeInTheDocument()
  expect(screen.getByText('$42.50')).toBeInTheDocument()
  expect(screen.getByText('Stop $0.70')).toBeInTheDocument()
  expect(screen.getByText('Target $2.20')).toBeInTheDocument()
  expect(screen.getByText('Expires 2026-08-21')).toBeInTheDocument()
  expect(screen.getByText('Assignment scenario warning')).toBeInTheDocument()
  expect(screen.queryByText(/schwab|live mode|external broker/i)).not.toBeInTheDocument()
})

test('renders empty paper position state', async () => {
  vi.spyOn(globalThis, 'fetch').mockResolvedValue(response({ paper_mode: true, positions: [] }))

  render(<PaperPositionsPanel />)

  expect(await screen.findByText('No paper positions are open.')).toBeInTheDocument()
})
