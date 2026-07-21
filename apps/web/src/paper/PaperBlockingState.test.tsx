import { cleanup, render, screen } from '@testing-library/react'
import { afterEach, expect, test, vi } from 'vitest'

import type { ReadinessResponse } from '../api'
import SystemReadinessProvider from '../dashboard/SystemReadinessProvider'
import PaperActionPanel from './PaperActionPanel'
import PaperOrdersPanel from './PaperOrdersPanel'
import PaperPositionsPanel from './PaperPositionsPanel'
import PaperPreviewPanel from './PaperPreviewPanel'
import type { PaperApprovalCard } from './types'

afterEach(() => {
  cleanup()
  vi.restoreAllMocks()
})

const blockedReadiness: ReadinessResponse = {
  status: 'blocking',
  trading_mode: 'paper',
  blocking: true,
  components: [
    {
      name: 'restart_recovery',
      status: 'blocking',
      code: 'restart_recovery_gap',
      summary: 'Process restart recovery has pending reconciliation work.',
      blocking: true,
      details: {},
    },
  ],
}

const unsafeUnavailableReadiness: ReadinessResponse = {
  status: 'unavailable',
  trading_mode: 'paper',
  blocking: true,
  components: [
    {
      name: 'database',
      status: 'unavailable',
      code: 'database_unavailable',
      summary: 'System readiness is unavailable.',
      blocking: true,
      details: { raw_error: 'database_url=sqlite:///secret.db token=abc' },
    },
  ],
}

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

function response(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), { status })
}

test('disables approval preview and submit controls when readiness blocks paper actions', () => {
  render(
    <SystemReadinessProvider value={blockedReadiness}>
      <PaperActionPanel card={card} now={new Date('2026-07-20T15:31:00Z')} />
      <PaperPreviewPanel approvalId="approval:1" now={new Date('2026-07-20T15:31:00Z')} />
    </SystemReadinessProvider>,
  )

  expect(screen.getByRole('button', { name: 'Approve paper approval' })).toBeDisabled()
  expect(screen.getByRole('button', { name: 'Reject paper approval' })).toBeDisabled()
  expect(screen.getByRole('button', { name: 'Save paper modification' })).toBeDisabled()
  expect(screen.getByRole('button', { name: 'Preview paper order' })).toBeDisabled()
  expect(screen.getByRole('button', { name: 'Submit paper order' })).toBeDisabled()
  expect(screen.getAllByText('Paper actions blocked: restart_recovery_gap').length)
    .toBeGreaterThan(0)
})

test('disables cancel replace and position exit controls when readiness blocks paper actions', async () => {
  vi.spyOn(globalThis, 'fetch').mockImplementation(async (input) => {
    if (String(input).includes('/api/paper/orders')) {
      return response({
        paper_mode: true,
        orders: [{
          order_id: 'order:working',
          intent_key: 'intent:working',
          status: 'working',
          requested_quantity: 2,
          filled_quantity: 0,
          limit_price: '1.25',
          updated_at: '2026-07-20T15:35:00Z',
        }],
      })
    }
    return response({
      paper_mode: true,
      positions: [{
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
    })
  })

  render(
    <SystemReadinessProvider value={blockedReadiness}>
      <PaperOrdersPanel />
      <PaperPositionsPanel />
    </SystemReadinessProvider>,
  )

  expect(await screen.findByRole('button', { name: 'Cancel paper order order:working' }))
    .toBeDisabled()
  expect(screen.getByRole('button', { name: 'Replace paper order order:working' }))
    .toBeDisabled()
  expect(await screen.findByRole('button', { name: 'Exit paper position position:open' }))
    .toBeDisabled()
})

test('renders safe blocked unavailable copy without raw backend details', () => {
  render(
    <SystemReadinessProvider value={unsafeUnavailableReadiness}>
      <PaperActionPanel card={card} now={new Date('2026-07-20T15:31:00Z')} />
    </SystemReadinessProvider>,
  )

  expect(screen.getByText('Paper actions blocked: database_unavailable')).toBeInTheDocument()
  expect(document.body.textContent).not.toContain('secret.db')
  expect(document.body.textContent).not.toContain('token=abc')
})
