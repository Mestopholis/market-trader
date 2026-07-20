import { cleanup, render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, expect, test, vi } from 'vitest'

import PaperOrdersPanel from './PaperOrdersPanel'

afterEach(() => {
  cleanup()
  vi.restoreAllMocks()
})

function response(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), { status })
}

const orders = {
  paper_mode: true,
  orders: [
    {
      order_id: 'order:working',
      intent_key: 'intent:working',
      status: 'working',
      scenario: 'accepted_unfilled',
      requested_quantity: 4,
      filled_quantity: 0,
      remaining_quantity: 4,
      limit_price: '1.25',
      average_fill_price: null,
      simulated_broker_reference: 'sim-order-working',
      source_keys: ['approval:working'],
      updated_at: '2026-07-20T15:30:00Z',
      broker_reference: null,
    },
    {
      order_id: 'order:partial',
      intent_key: 'intent:partial',
      status: 'partially_filled',
      scenario: 'partial_fill',
      requested_quantity: 4,
      filled_quantity: 2,
      remaining_quantity: 2,
      limit_price: '1.40',
      average_fill_price: '1.35',
      simulated_broker_reference: 'sim-order-partial',
      source_keys: ['approval:partial'],
      updated_at: '2026-07-20T15:31:00Z',
      broker_reference: null,
    },
    {
      order_id: 'order:reject',
      intent_key: 'intent:reject',
      status: 'rejected',
      scenario: 'reject',
      requested_quantity: 1,
      filled_quantity: 0,
      remaining_quantity: 1,
      limit_price: '0.85',
      average_fill_price: null,
      simulated_broker_reference: 'sim-order-reject',
      source_keys: ['approval:reject'],
      updated_at: '2026-07-20T15:32:00Z',
      broker_reference: null,
    },
  ],
}

test('renders paper order statuses and paper-only cancel replace controls', async () => {
  const user = userEvent.setup()
  const fetchMock = vi.spyOn(globalThis, 'fetch')
    .mockResolvedValueOnce(response(orders))
    .mockResolvedValueOnce(response({ paper_mode: true, order_id: 'order:working', status: 'canceled' }))
    .mockResolvedValueOnce(response({ paper_mode: true, order_id: 'order:working', status: 'replaced' }))

  render(<PaperOrdersPanel />)

  expect(await screen.findByRole('heading', { name: 'Paper orders' })).toBeInTheDocument()
  expect(screen.getByText('working')).toBeInTheDocument()
  expect(screen.getByText('partially filled')).toBeInTheDocument()
  expect(screen.getByText('rejected')).toBeInTheDocument()
  expect(screen.getByText('2 / 4 filled')).toBeInTheDocument()
  expect(screen.queryByText('timeout')).not.toBeInTheDocument()
  expect(screen.queryByText(/schwab|live mode|external broker/i)).not.toBeInTheDocument()

  await user.click(screen.getByRole('button', { name: 'Cancel paper order order:working' }))
  expect(await screen.findByText('Paper order canceled: order:working')).toBeInTheDocument()

  await user.clear(screen.getByLabelText('Replacement limit for order:working'))
  await user.type(screen.getByLabelText('Replacement limit for order:working'), '1.10')
  await user.click(screen.getByRole('button', { name: 'Replace paper order order:working' }))

  expect(await screen.findByText('Paper order replaced: order:working')).toBeInTheDocument()
  expect(fetchMock.mock.calls[2][0]).toBe('/api/paper/orders/order%3Aworking/replace')
  expect(fetchMock.mock.calls[2][1]).toMatchObject({
    method: 'POST',
    body: JSON.stringify({ limit_price: '1.10' }),
  })
})

test('renders unavailable paper order state', async () => {
  vi.spyOn(globalThis, 'fetch').mockRejectedValue(new Error('offline'))

  render(<PaperOrdersPanel />)

  expect(await screen.findByRole('alert')).toHaveTextContent('Paper orders unavailable')
})
