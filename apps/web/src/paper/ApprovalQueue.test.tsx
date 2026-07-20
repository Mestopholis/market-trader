import { cleanup, render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, expect, test, vi } from 'vitest'

import ApprovalQueue from './ApprovalQueue'
import type { PaperApprovalCardListResponse } from './types'

const cards: PaperApprovalCardListResponse = {
  paper_mode: true,
  approval_cards: [
    {
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
    },
    {
      card_key: 'card:aapl',
      state: 'stale',
      candidate_key: 'candidate:aapl',
      symbol: 'AAPL',
      direction: 'short',
      proposal_kind: 'bear_put_spread',
      quantity: 1,
      limit_price: '0.95',
      maximum_loss: '95.00',
      risk_decision_key: 'risk:aapl',
      risk_status: 'warning',
      risk_input_digest: 'risk-input-aapl',
      risk_result_digest: 'risk-result-aapl',
      source_keys: ['candidate:aapl', 'risk_decision:risk:aapl'],
      allowed_actions: ['reject'],
      expires_at: '2026-07-20T15:32:00Z',
      as_of: '2026-07-20T15:30:00Z',
      warnings: ['Source data is stale'],
      paper_mode: true,
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

test('renders approval queue rows and opens selected detail', async () => {
  const user = userEvent.setup()
  vi.spyOn(globalThis, 'fetch').mockResolvedValue(response(cards))

  render(<ApprovalQueue />)

  expect(await screen.findByRole('heading', { name: 'Paper approvals' })).toBeInTheDocument()
  expect(screen.getByRole('button', { name: /MSFT long bull call spread/i })).toBeInTheDocument()
  expect(screen.getByRole('button', { name: /AAPL short bear put spread/i })).toBeInTheDocument()
  expect(screen.getAllByText('ready').length).toBeGreaterThan(0)
  expect(screen.getByText('stale')).toBeInTheDocument()
  expect(screen.getAllByText(/ET \/ .*CT/).length).toBeGreaterThan(0)

  await user.click(screen.getByRole('button', { name: /AAPL short bear put spread/i }))

  expect(screen.getByRole('heading', { name: 'AAPL paper approval detail' })).toBeInTheDocument()
  expect(screen.getByText('Source data is stale')).toBeInTheDocument()
})

test('renders empty approval queue without manual trade entry controls', async () => {
  vi.spyOn(globalThis, 'fetch').mockResolvedValue(
    response({ paper_mode: true, approval_cards: [] }),
  )

  render(<ApprovalQueue />)

  expect(await screen.findByText('No paper approval cards are available.')).toBeInTheDocument()
  expect(screen.queryByLabelText(/symbol|quantity|limit price/i)).not.toBeInTheDocument()
  expect(screen.queryByRole('button', { name: /approve|preview|submit|buy|sell|execute/i }))
    .not
    .toBeInTheDocument()
})

test('renders unavailable state when approval cards cannot load', async () => {
  vi.spyOn(globalThis, 'fetch').mockRejectedValue(new Error('offline'))

  render(<ApprovalQueue />)

  expect(await screen.findByRole('alert')).toHaveTextContent('Paper approvals unavailable')
})
