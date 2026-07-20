import { cleanup, render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, expect, test, vi } from 'vitest'

import PaperRecoveryPanel from './PaperRecoveryPanel'

afterEach(() => {
  cleanup()
  vi.restoreAllMocks()
})

function response(body: unknown): Response {
  return new Response(JSON.stringify(body), { status: 200 })
}

const recovery = {
  paper_mode: true,
  open_approvals: [{ paper_mode: true, id: 'approval:open', status: 'approved' }],
  working_orders: [{ order_id: 'order:working', intent_key: 'intent:working', status: 'working' }],
  timed_out_orders: [{ order_id: 'order:timeout', intent_key: 'intent:timeout', status: 'timed_out' }],
  open_orders: [
    { order_id: 'order:working', intent_key: 'intent:working', status: 'working' },
    { order_id: 'order:timeout', intent_key: 'intent:timeout', status: 'timed_out' },
  ],
  open_positions: [{
    position_key: 'position:open',
    symbol: 'MSFT',
    status: 'open',
    quantity: 2,
    average_price: '1.25',
    realized_pl: '0.00',
    unrealized_pl: '10.00',
    source_order_ids: ['order:working'],
    source_fill_ids: ['fill:working'],
    risk_decision_key: 'risk:open',
    opened_at: '2026-07-20T15:30:00Z',
    updated_at: '2026-07-20T15:35:00Z',
    closed_at: null,
    exit_rules: {},
    broker_reference: null,
  }],
}

test('renders recovery state and refreshes recovery on demand', async () => {
  const user = userEvent.setup()
  const fetchMock = vi.spyOn(globalThis, 'fetch')
    .mockResolvedValueOnce(response(recovery))
    .mockResolvedValueOnce(response({
      ...recovery,
      timed_out_orders: [],
      open_orders: recovery.open_orders.slice(0, 1),
    }))

  render(<PaperRecoveryPanel />)

  expect(await screen.findByRole('heading', { name: 'Paper recovery' })).toBeInTheDocument()
  expect(screen.getByText('1 open approval')).toBeInTheDocument()
  expect(screen.getByText('1 working order')).toBeInTheDocument()
  expect(screen.getByText('1 timed-out order')).toBeInTheDocument()
  expect(screen.getByText('1 open position')).toBeInTheDocument()
  expect(screen.getByText(/order:timeout/)).toBeInTheDocument()

  await user.click(screen.getByRole('button', { name: 'Refresh paper recovery' }))

  expect(await screen.findByText('0 timed-out orders')).toBeInTheDocument()
  expect(fetchMock.mock.calls.map((call) => call[0])).toEqual([
    '/api/paper/recover',
    '/api/paper/recover',
  ])
})

test('renders unavailable recovery state', async () => {
  vi.spyOn(globalThis, 'fetch').mockRejectedValue(new Error('offline'))

  render(<PaperRecoveryPanel />)

  expect(await screen.findByRole('alert')).toHaveTextContent('Paper recovery unavailable')
})
