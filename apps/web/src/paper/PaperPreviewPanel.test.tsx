import { cleanup, render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, expect, test, vi } from 'vitest'

import PaperPreviewPanel from './PaperPreviewPanel'

afterEach(() => {
  cleanup()
  vi.restoreAllMocks()
})

function response(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), { status })
}

const currentPreview = {
  paper_mode: true,
  preview_key: 'preview:approval:1',
  approval_id: 'approval:1',
  intent_key: 'intent:1',
  quote_observed_at: '2026-07-20T15:30:00Z',
  quote_expires_at: '2026-07-20T15:40:00Z',
  bid: '1.20',
  ask: '1.30',
  limit_price: '1.25',
  estimated_maximum_loss: '250.00',
  reserved_risk: '250.00',
  warnings: ['Paper quote only'],
  preview_digest: 'preview-digest-1',
  source_keys: ['approval:1'],
  as_of: '2026-07-20T15:30:00Z',
}

test('previews and submits a paper order only after a current preview exists', async () => {
  const user = userEvent.setup()
  const fetchMock = vi.spyOn(globalThis, 'fetch')
    .mockResolvedValueOnce(response(currentPreview))
    .mockResolvedValueOnce(response({
      paper_mode: true,
      order: { order_id: 'order:1', intent_key: 'intent:1', status: 'filled' },
      persisted_order_id: 'persisted-order-1',
      position: null,
    }))

  render(<PaperPreviewPanel approvalId="approval:1" now={new Date('2026-07-20T15:31:00Z')} />)

  expect(screen.getByRole('button', { name: 'Submit paper order' })).toBeDisabled()
  await user.click(screen.getByRole('button', { name: 'Preview paper order' }))

  expect(await screen.findByText('preview-digest-1')).toBeInTheDocument()
  expect(screen.getByText('Paper quote only')).toBeInTheDocument()
  expect(screen.getByRole('button', { name: 'Submit paper order' })).toBeEnabled()

  await user.click(screen.getByRole('button', { name: 'Submit paper order' }))

  expect(await screen.findByText('Paper order submitted: order:1')).toBeInTheDocument()
  expect(fetchMock.mock.calls[1][0]).toBe('/api/paper/approvals/approval%3A1/submit')
  expect(fetchMock.mock.calls[1][1]).toMatchObject({
    method: 'POST',
    body: JSON.stringify({ preview_digest: 'preview-digest-1', scenario: 'full_fill' }),
  })
})

test('blocks stale preview submission and reports submit validation errors', async () => {
  const user = userEvent.setup()
  vi.spyOn(globalThis, 'fetch')
    .mockResolvedValueOnce(response({
      ...currentPreview,
      quote_expires_at: '2026-07-20T15:30:30Z',
    }))
    .mockResolvedValueOnce(response(currentPreview))
    .mockResolvedValueOnce(response({ detail: 'stale_preview' }, 409))

  render(<PaperPreviewPanel approvalId="approval:1" now={new Date('2026-07-20T15:31:00Z')} />)

  await user.click(screen.getByRole('button', { name: 'Preview paper order' }))

  expect(await screen.findByText('Preview is stale. Refresh preview before submitting.'))
    .toBeInTheDocument()
  expect(screen.getByRole('button', { name: 'Submit paper order' })).toBeDisabled()

  await user.click(screen.getByRole('button', { name: 'Preview paper order' }))
  await user.click(screen.getByRole('button', { name: 'Submit paper order' }))

  expect(await screen.findByRole('alert')).toHaveTextContent(
    'Paper approval submit request failed with 409',
  )
})
