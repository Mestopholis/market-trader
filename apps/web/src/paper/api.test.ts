import { afterEach, expect, test, vi } from 'vitest'

import {
  approvePaperApprovalCard,
  cancelPaperOrder,
  fetchPaperApprovalCards,
  fetchPaperOrders,
  fetchPaperPositions,
  modifyPaperApprovalCard,
  previewPaperApproval,
  recoverPaperLifecycle,
  rejectPaperApprovalCard,
  replacePaperOrder,
  submitPaperApproval,
} from '../api'
import type { PaperApprovalCardListResponse } from './types'

const approvalCards: PaperApprovalCardListResponse = {
  paper_mode: true,
  approval_cards: [
    {
      card_key: 'card:a',
      state: 'ready',
      candidate_key: 'candidate:a',
      symbol: 'MSFT',
      direction: 'long',
      proposal_kind: 'single',
      quantity: 2,
      limit_price: '1.25',
      maximum_loss: '250.00',
      risk_decision_key: 'risk:a',
      risk_status: 'approved',
      risk_input_digest: 'risk-input-a',
      risk_result_digest: 'risk-result-a',
      source_keys: ['candidate:candidate:a', 'risk_decision:risk:a'],
      allowed_actions: ['approve', 'modify', 'reject'],
      expires_at: '2026-07-20T15:35:00Z',
      as_of: '2026-07-20T15:30:00Z',
      warnings: [],
      paper_mode: true,
    },
  ],
}

afterEach(() => {
  vi.restoreAllMocks()
  document.cookie = 'market_trader_csrf=; Max-Age=0; path=/'
})

function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), { status })
}

test('fetches approval cards, orders, positions, and recovery with no-store headers', async () => {
  const fetchMock = vi.spyOn(globalThis, 'fetch').mockImplementation(async (input) => {
    if (String(input).endsWith('/approval-cards')) return jsonResponse(approvalCards)
    if (String(input).endsWith('/orders')) return jsonResponse({ paper_mode: true, orders: [] })
    if (String(input).endsWith('/positions')) return jsonResponse({ paper_mode: true, positions: [] })
    return jsonResponse({
      paper_mode: true,
      open_approvals: [],
      working_orders: [],
      timed_out_orders: [],
      open_orders: [],
      open_positions: [],
    })
  })

  await expect(fetchPaperApprovalCards()).resolves.toEqual(approvalCards)
  await expect(fetchPaperOrders()).resolves.toEqual({ paper_mode: true, orders: [] })
  await expect(fetchPaperPositions()).resolves.toEqual({ paper_mode: true, positions: [] })
  await expect(recoverPaperLifecycle()).resolves.toEqual({
    paper_mode: true,
    open_approvals: [],
    working_orders: [],
    timed_out_orders: [],
    open_orders: [],
    open_positions: [],
  })

  expect(fetchMock.mock.calls.map((call) => call[1])).toEqual([
    {
      headers: { Accept: 'application/json' },
      cache: 'no-store',
      credentials: 'same-origin',
      signal: undefined,
    },
    {
      headers: { Accept: 'application/json' },
      cache: 'no-store',
      credentials: 'same-origin',
      signal: undefined,
    },
    {
      headers: { Accept: 'application/json' },
      cache: 'no-store',
      credentials: 'same-origin',
      signal: undefined,
    },
    {
      method: 'POST',
      headers: { Accept: 'application/json', 'X-CSRF-Token': '' },
      body: undefined,
      cache: 'no-store',
      credentials: 'same-origin',
      signal: undefined,
    },
  ])
})

test('posts paper approval actions with encoded keys and JSON payloads', async () => {
  const fetchMock = vi
    .spyOn(globalThis, 'fetch')
    .mockImplementation(async () => jsonResponse({ paper_mode: true, id: 'approval-a' }))

  await approvePaperApprovalCard('card:a')
  await modifyPaperApprovalCard('card:a', { quantity: 1, limit_price: '1.15' })
  await rejectPaperApprovalCard('card:a')

  expect(fetchMock.mock.calls).toEqual([
    [
      '/api/paper/approval-cards/card%3Aa/approve',
      {
        method: 'POST',
        headers: { Accept: 'application/json', 'X-CSRF-Token': '' },
        body: undefined,
        cache: 'no-store',
        credentials: 'same-origin',
        signal: undefined,
      },
    ],
    [
      '/api/paper/approval-cards/card%3Aa/modify',
      {
        method: 'POST',
        headers: {
          Accept: 'application/json',
          'X-CSRF-Token': '',
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({ quantity: 1, limit_price: '1.15' }),
        cache: 'no-store',
        credentials: 'same-origin',
        signal: undefined,
      },
    ],
    [
      '/api/paper/approval-cards/card%3Aa/reject',
      {
        method: 'POST',
        headers: { Accept: 'application/json', 'X-CSRF-Token': '' },
        body: undefined,
        cache: 'no-store',
        credentials: 'same-origin',
        signal: undefined,
      },
    ],
  ])
})

test('posts preview, submit, cancel, and replace actions', async () => {
  const fetchMock = vi
    .spyOn(globalThis, 'fetch')
    .mockImplementation(async () => jsonResponse({ paper_mode: true, ok: true }))

  await previewPaperApproval('approval:a')
  await submitPaperApproval('approval:a', {
    preview_digest: 'preview-digest-a',
    scenario: 'full_fill',
  })
  await cancelPaperOrder('order:a')
  await replacePaperOrder('order:a', { limit_price: '1.10' })

  expect(fetchMock.mock.calls.map((call) => call[0])).toEqual([
    '/api/paper/approvals/approval%3Aa/preview',
    '/api/paper/approvals/approval%3Aa/submit',
    '/api/paper/orders/order%3Aa/cancel',
    '/api/paper/orders/order%3Aa/replace',
  ])
  expect(fetchMock.mock.calls[1][1]).toMatchObject({
    method: 'POST',
    body: JSON.stringify({ preview_digest: 'preview-digest-a', scenario: 'full_fill' }),
  })
  expect(fetchMock.mock.calls[3][1]).toMatchObject({
    method: 'POST',
    body: JSON.stringify({ limit_price: '1.10' }),
  })
})

test('throws clear paper API errors', async () => {
  vi.spyOn(globalThis, 'fetch').mockResolvedValue(jsonResponse({ detail: 'stale_preview' }, 409))

  await expect(fetchPaperApprovalCards()).rejects.toThrow(
    'Paper approval cards request failed with 409',
  )
})
