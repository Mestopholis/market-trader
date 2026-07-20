import { cleanup, render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, expect, test, vi } from 'vitest'

import PaperActionPanel from './PaperActionPanel'
import type { PaperApprovalCard } from './types'

const card: PaperApprovalCard = {
  card_key: 'card:msft',
  state: 'ready',
  candidate_key: 'candidate:msft',
  symbol: 'MSFT',
  direction: 'long',
  proposal_kind: 'bull_call_spread',
  quantity: 2,
  limit_price: '1.25',
  maximum_loss: '250.00',
  risk_decision_key: 'risk:msft',
  risk_status: 'approved',
  risk_input_digest: 'risk-input-msft',
  risk_result_digest: 'risk-result-msft',
  source_keys: ['candidate:msft', 'risk_decision:risk:msft'],
  allowed_actions: ['approve', 'modify', 'reject'],
  expires_at: '2026-07-20T15:35:00Z',
  as_of: '2026-07-20T15:30:00Z',
  warnings: [],
  paper_mode: true,
}

afterEach(() => {
  cleanup()
  vi.restoreAllMocks()
})

function response(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), { status })
}

test('approves and rejects paper approval cards with paper-only labels', async () => {
  const user = userEvent.setup()
  const fetchMock = vi.spyOn(globalThis, 'fetch')
    .mockResolvedValueOnce(response({ paper_mode: true, id: 'approval:1', status: 'approved' }))
    .mockResolvedValueOnce(response({ paper_mode: true, id: 'approval:1', status: 'rejected' }))

  render(<PaperActionPanel card={card} now={new Date('2026-07-20T15:31:00Z')} />)

  expect(screen.getByText('Paper-only approval actions')).toBeInTheDocument()
  await user.click(screen.getByRole('button', { name: 'Approve paper approval' }))
  expect(await screen.findByText('Paper approval approved: approval:1')).toBeInTheDocument()

  await user.click(screen.getByRole('button', { name: 'Reject paper approval' }))
  expect(await screen.findByText('Paper approval rejected: approval:1')).toBeInTheDocument()
  expect(fetchMock.mock.calls.map((call) => call[0])).toEqual([
    '/api/paper/approval-cards/card%3Amsft/approve',
    '/api/paper/approval-cards/card%3Amsft/reject',
  ])
})

test('modifies quantity and limit price with bounded validation', async () => {
  const user = userEvent.setup()
  const fetchMock = vi.spyOn(globalThis, 'fetch')
    .mockResolvedValue(response({ paper_mode: true, id: 'approval:1', status: 'modified' }))

  render(<PaperActionPanel card={card} now={new Date('2026-07-20T15:31:00Z')} />)

  await user.clear(screen.getByLabelText('Paper quantity'))
  await user.type(screen.getByLabelText('Paper quantity'), '0')
  await user.click(screen.getByRole('button', { name: 'Save paper modification' }))

  expect(screen.getByRole('alert')).toHaveTextContent('Quantity must be at least 1')
  expect(fetchMock).not.toHaveBeenCalled()

  await user.clear(screen.getByLabelText('Paper quantity'))
  await user.type(screen.getByLabelText('Paper quantity'), '3')
  await user.clear(screen.getByLabelText('Paper limit price'))
  await user.type(screen.getByLabelText('Paper limit price'), '1.10')
  await user.click(screen.getByRole('button', { name: 'Save paper modification' }))

  expect(await screen.findByText('Paper approval modified: approval:1')).toBeInTheDocument()
  expect(fetchMock.mock.calls[0][0]).toBe('/api/paper/approval-cards/card%3Amsft/modify')
  expect(fetchMock.mock.calls[0][1]).toMatchObject({
    method: 'POST',
    body: JSON.stringify({ quantity: 3, limit_price: '1.10' }),
  })
})

test('disables paper approval actions for expired cards and reports API validation errors', async () => {
  const expiredCard = { ...card, expires_at: '2026-07-20T15:30:00Z' }
  const { rerender } = render(
    <PaperActionPanel card={expiredCard} now={new Date('2026-07-20T15:31:00Z')} />,
  )

  expect(screen.getByText('Approval expired. Refresh the approval queue.')).toBeInTheDocument()
  expect(screen.getByRole('button', { name: 'Approve paper approval' })).toBeDisabled()

  vi.spyOn(globalThis, 'fetch').mockResolvedValue(response({ detail: 'approval_expired' }, 409))
  rerender(<PaperActionPanel card={card} now={new Date('2026-07-20T15:31:00Z')} />)

  await userEvent.click(screen.getByRole('button', { name: 'Approve paper approval' }))

  expect(await screen.findByRole('alert')).toHaveTextContent(
    'Paper approval approve request failed with 409',
  )
})
