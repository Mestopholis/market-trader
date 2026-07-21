import { cleanup, render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, expect, test, vi } from 'vitest'

import OperationsPanel from './OperationsPanel'

afterEach(() => {
  cleanup()
  vi.restoreAllMocks()
})

const readiness = {
  status: 'blocking',
  trading_mode: 'paper',
  blocking: true,
  components: [
    {
      name: 'database',
      status: 'ok',
      code: 'database_ok',
      summary: 'Database connection is available.',
      blocking: false,
      details: {},
    },
    {
      name: 'restart_recovery',
      status: 'blocking',
      code: 'restart_recovery_gap',
      summary: 'Process restart recovery has pending reconciliation work.',
      blocking: true,
      details: { pending_events: 2 },
    },
  ],
}

const recovery = {
  paper_mode: true,
  open_approvals: [],
  working_orders: [{ order_id: 'order:working', intent_key: 'intent:working', status: 'working' }],
  timed_out_orders: [{ order_id: 'order:timeout', intent_key: 'intent:timeout', status: 'timed_out' }],
  open_orders: [],
  open_positions: [],
}

function response(body: unknown, headers: Record<string, string> = {}): Response {
  return new Response(JSON.stringify(body), { status: 200, headers })
}

test('renders health states and the response correlation id', async () => {
  vi.spyOn(globalThis, 'fetch').mockImplementation(async (input) => {
    if (String(input).includes('/api/readiness')) {
      return response(readiness, { 'X-Correlation-ID': 'corr-ops-1' })
    }
    return response(recovery, { 'X-Correlation-ID': 'corr-recovery-1' })
  })

  render(<OperationsPanel />)

  expect(await screen.findByRole('heading', { name: 'System health' })).toBeInTheDocument()
  expect(screen.getByText('restart_recovery_gap')).toBeInTheDocument()
  expect(screen.getByText('Process restart recovery has pending reconciliation work.')).toBeInTheDocument()
  expect(screen.getByText('corr-ops-1')).toBeInTheDocument()
  expect(screen.getByRole('heading', { name: 'Recovery drill' })).toBeInTheDocument()
  expect(screen.getByText('1 timed-out order')).toBeInTheDocument()
  expect(screen.getByText('corr-recovery-1')).toBeInTheDocument()
})

test('refreshes recovery state and renders safe errors only', async () => {
  const user = userEvent.setup()
  const fetchMock = vi.spyOn(globalThis, 'fetch')
    .mockResolvedValueOnce(response(readiness))
    .mockResolvedValueOnce(response(recovery))
    .mockRejectedValueOnce(new Error('database_url=sqlite:///secret.db token=abc'))

  render(<OperationsPanel />)

  await screen.findByRole('heading', { name: 'Recovery drill' })
  await user.click(screen.getByRole('button', { name: 'Refresh recovery drill' }))

  expect(await screen.findByRole('alert')).toHaveTextContent('Recovery drill unavailable')
  expect(document.body.textContent).not.toContain('secret.db')
  expect(document.body.textContent).not.toContain('token=abc')
  expect(fetchMock.mock.calls.map((call) => String(call[0]))).toEqual([
    '/api/readiness',
    '/api/paper/recover',
    '/api/paper/recover',
  ])
})
