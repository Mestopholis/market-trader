import { cleanup, render, screen } from '@testing-library/react'
import { afterEach, expect, test } from 'vitest'

import ApprovalCardDetail from './ApprovalCardDetail'
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
  risk_status: 'warning',
  risk_input_digest: 'risk-input-msft',
  risk_result_digest: 'risk-result-msft',
  source_keys: ['candidate:msft', 'risk_decision:risk:msft'],
  allowed_actions: ['approve', 'modify', 'reject'],
  expires_at: '2026-07-20T15:35:00Z',
  as_of: '2026-07-20T15:30:00Z',
  warnings: ['Risk warning remains active'],
  paper_mode: true,
}

afterEach(() => {
  cleanup()
})

test('renders approval card detail with source trace and expiration', () => {
  render(<ApprovalCardDetail card={card} />)

  expect(screen.getByRole('heading', { name: 'MSFT paper approval detail' })).toBeInTheDocument()
  expect(screen.getByText(/bull call spread/)).toBeInTheDocument()
  expect(screen.getByText('Maximum loss')).toBeInTheDocument()
  expect(screen.getByText('$250.00')).toBeInTheDocument()
  expect(screen.getByText('Risk warning remains active')).toBeInTheDocument()
  expect(screen.getByText('candidate:msft')).toBeInTheDocument()
  expect(screen.getByText('risk_decision:risk:msft')).toBeInTheDocument()
  expect(screen.getByText(/Jul 20, 11:35 AM ET \/ .*10:35 AM CT/)).toBeInTheDocument()
})

test('shows paper-only action labels without executable controls', () => {
  render(<ApprovalCardDetail card={card} />)

  expect(screen.getByText('Paper-only actions')).toBeInTheDocument()
  expect(screen.getByText('approve')).toBeInTheDocument()
  expect(screen.getByText('modify')).toBeInTheDocument()
  expect(screen.getByText('reject')).toBeInTheDocument()
  expect(screen.queryByRole('button', { name: /approve|modify|reject|submit|buy|sell/i }))
    .not
    .toBeInTheDocument()
})
