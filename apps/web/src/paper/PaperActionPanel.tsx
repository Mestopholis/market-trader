import { useState } from 'react'

import {
  approvePaperApprovalCard,
  modifyPaperApprovalCard,
  rejectPaperApprovalCard,
} from '../api'
import { usePaperActionBlock } from '../dashboard/SystemReadinessHooks'
import type { PaperApproval, PaperApprovalCard } from './types'
import PaperPreviewPanel from './PaperPreviewPanel'

type PaperActionPanelProps = {
  card: PaperApprovalCard
  now?: Date
}

export default function PaperActionPanel({
  card,
  now = new Date(),
}: PaperActionPanelProps) {
  const [quantity, setQuantity] = useState(String(card.quantity))
  const [limitPrice, setLimitPrice] = useState(card.limit_price)
  const [approval, setApproval] = useState<PaperApproval | null>(null)
  const [message, setMessage] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [busyAction, setBusyAction] = useState<string | null>(null)
  const actionBlock = usePaperActionBlock()

  const isExpired = new Date(card.expires_at).getTime() <= now.getTime()
  const isActionable = card.state === 'ready' && !isExpired && actionBlock === null

  async function runAction(
    action: string,
    request: () => Promise<PaperApproval>,
    success: (approval: PaperApproval) => string,
  ) {
    setBusyAction(action)
    setError(null)
    setMessage(null)
    try {
      const nextApproval = await request()
      setApproval(nextApproval)
      setMessage(success(nextApproval))
    } catch (caught) {
      setError(messageFrom(caught))
    } finally {
      setBusyAction(null)
    }
  }

  async function handleModify() {
    const parsedQuantity = Number(quantity)
    const parsedLimit = Number(limitPrice)
    if (!Number.isInteger(parsedQuantity) || parsedQuantity < 1) {
      setError('Quantity must be at least 1')
      return
    }
    if (!Number.isFinite(parsedLimit) || parsedLimit <= 0) {
      setError('Limit price must be greater than 0')
      return
    }

    await runAction(
      'modify',
      () => modifyPaperApprovalCard(card.card_key, {
        quantity: parsedQuantity,
        limit_price: limitPrice,
      }),
      (nextApproval) => `Paper approval modified: ${nextApproval.id}`,
    )
  }

  return (
    <section className="paper-action-block" aria-labelledby="paper-action-title">
      <div className="dashboard-panel-heading">
        <h3 id="paper-action-title">Paper-only approval actions</h3>
        <span className="state-chip">no live broker</span>
      </div>

      {isExpired && <p className="muted">Approval expired. Refresh the approval queue.</p>}
      {actionBlock && <p className="paper-action-error">Paper actions blocked: {actionBlock.code}</p>}

      <div className="paper-action-row">
        <button
          type="button"
          className="paper-action-button"
          disabled={!isActionable || busyAction !== null}
          onClick={() => runAction(
            'approve',
            () => approvePaperApprovalCard(card.card_key),
            (nextApproval) => `Paper approval approved: ${nextApproval.id}`,
          )}
        >
          Approve paper approval
        </button>
        <button
          type="button"
          className="paper-action-button"
          disabled={!isActionable || busyAction !== null}
          onClick={() => runAction(
            'reject',
            () => rejectPaperApprovalCard(card.card_key),
            (nextApproval) => `Paper approval rejected: ${nextApproval.id}`,
          )}
        >
          Reject paper approval
        </button>
      </div>

      <div className="paper-modify-grid">
        <label className="filter-label">
          Paper quantity
          <input
            aria-label="Paper quantity"
            inputMode="numeric"
            value={quantity}
            onChange={(event) => setQuantity(event.target.value)}
          />
        </label>
        <label className="filter-label">
          Paper limit price
          <input
            aria-label="Paper limit price"
            inputMode="decimal"
            value={limitPrice}
            onChange={(event) => setLimitPrice(event.target.value)}
          />
        </label>
        <button
          type="button"
          className="paper-action-button"
          disabled={!isActionable || busyAction !== null}
          onClick={handleModify}
        >
          Save paper modification
        </button>
      </div>

      {message && <p>{message}</p>}
      {error && <p role="alert" className="paper-action-error">{error}</p>}
      {approval?.id && <PaperPreviewPanel approvalId={approval.id} now={now} />}
    </section>
  )
}

function messageFrom(caught: unknown): string {
  return caught instanceof Error ? caught.message : 'Paper request failed'
}
