import { useMemo, useState } from 'react'

import { previewPaperApproval, submitPaperApproval } from '../api'
import { formatDashboardTime } from '../dashboard/formatting'
import type { PaperBrokerScenario, PaperPreview, SubmittedPaperOrder } from './types'

type PaperPreviewPanelProps = {
  approvalId: string
  now?: Date
}

const DEFAULT_SCENARIO: PaperBrokerScenario = 'full_fill'

export default function PaperPreviewPanel({
  approvalId,
  now = new Date(),
}: PaperPreviewPanelProps) {
  const [preview, setPreview] = useState<PaperPreview | null>(null)
  const [submitted, setSubmitted] = useState<SubmittedPaperOrder | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [busyAction, setBusyAction] = useState<'preview' | 'submit' | null>(null)

  const previewIsCurrent = useMemo(() => {
    if (!preview) return false
    return new Date(preview.quote_expires_at).getTime() > now.getTime()
  }, [now, preview])

  async function handlePreview() {
    setBusyAction('preview')
    setError(null)
    setSubmitted(null)
    try {
      setPreview(await previewPaperApproval(approvalId))
    } catch (caught) {
      setError(messageFrom(caught))
    } finally {
      setBusyAction(null)
    }
  }

  async function handleSubmit() {
    if (!preview || !previewIsCurrent) return
    setBusyAction('submit')
    setError(null)
    try {
      setSubmitted(await submitPaperApproval(approvalId, {
        preview_digest: preview.preview_digest,
        scenario: DEFAULT_SCENARIO,
      }))
    } catch (caught) {
      setError(messageFrom(caught))
    } finally {
      setBusyAction(null)
    }
  }

  return (
    <section className="paper-action-block" aria-labelledby="paper-preview-title">
      <div className="dashboard-panel-heading">
        <h3 id="paper-preview-title">Paper preview</h3>
        <span className="state-chip">paper-only</span>
      </div>

      <div className="paper-action-row">
        <button
          type="button"
          className="paper-action-button"
          onClick={handlePreview}
          disabled={busyAction !== null}
        >
          Preview paper order
        </button>
        <button
          type="button"
          className="paper-action-button"
          onClick={handleSubmit}
          disabled={!previewIsCurrent || busyAction !== null}
        >
          Submit paper order
        </button>
      </div>

      {preview && (
        <dl className="dashboard-facts paper-preview-facts">
          <dt>Preview digest</dt><dd>{preview.preview_digest}</dd>
          <dt>Quote expires</dt><dd>{formatDashboardTime(preview.quote_expires_at)}</dd>
          <dt>Bid / ask</dt><dd>{formatCurrency(preview.bid)} / {formatCurrency(preview.ask)}</dd>
          <dt>Reserved risk</dt><dd>{formatCurrency(preview.reserved_risk)}</dd>
        </dl>
      )}

      {preview && !previewIsCurrent && (
        <p className="muted">Preview is stale. Refresh preview before submitting.</p>
      )}

      {preview && preview.warnings.length > 0 && (
        <ul className="dashboard-warnings">
          {preview.warnings.map((warning) => <li key={warning}>{warning}</li>)}
        </ul>
      )}

      {submitted && <p>Paper order submitted: {submitted.order.order_id}</p>}
      {error && <p role="alert" className="paper-action-error">{error}</p>}
    </section>
  )
}

function formatCurrency(value: string): string {
  const numeric = Number(value)
  if (Number.isNaN(numeric)) return value
  return new Intl.NumberFormat('en-US', {
    style: 'currency',
    currency: 'USD',
  }).format(numeric)
}

function messageFrom(caught: unknown): string {
  return caught instanceof Error ? caught.message : 'Paper request failed'
}
