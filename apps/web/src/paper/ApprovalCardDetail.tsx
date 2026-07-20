import { formatDashboardTime, labelize } from '../dashboard/formatting'
import type { PaperApprovalCard } from './types'

type ApprovalCardDetailProps = {
  card: PaperApprovalCard
}

export default function ApprovalCardDetail({ card }: ApprovalCardDetailProps) {
  return (
    <section className="paper-detail" aria-labelledby="paper-detail-title">
      <div className="dashboard-panel-heading">
        <div>
          <h2 id="paper-detail-title">{card.symbol} paper approval detail</h2>
          <p className="muted">{labelize(card.proposal_kind)} · {card.direction}</p>
        </div>
        <span className={`state-chip state-${card.state}`}>{card.state}</span>
      </div>

      <dl className="dashboard-facts">
        <dt>Quantity</dt><dd>{card.quantity}</dd>
        <dt>Limit price</dt><dd>{formatCurrency(card.limit_price)}</dd>
        <dt>Maximum loss</dt><dd>{formatCurrency(card.maximum_loss)}</dd>
        <dt>Risk status</dt><dd>{card.risk_status}</dd>
        <dt>Risk decision</dt><dd>{card.risk_decision_key}</dd>
        <dt>Expires</dt><dd>{formatDashboardTime(card.expires_at)}</dd>
        <dt>As of</dt><dd>{formatDashboardTime(card.as_of)}</dd>
      </dl>

      <section className="dashboard-subsection" aria-labelledby="paper-actions-title">
        <h3 id="paper-actions-title">Paper-only actions</h3>
        <ul className="paper-token-list">
          {card.allowed_actions.map((action) => (
            <li key={action}><span className="state-chip">{action}</span></li>
          ))}
        </ul>
      </section>

      {card.warnings.length > 0 && (
        <section className="dashboard-subsection" aria-labelledby="paper-warnings-title">
          <h3 id="paper-warnings-title">Warnings</h3>
          <ul className="dashboard-warnings">
            {card.warnings.map((warning) => <li key={warning}>{warning}</li>)}
          </ul>
        </section>
      )}

      <section className="dashboard-subsection" aria-labelledby="paper-sources-title">
        <h3 id="paper-sources-title">Source trace</h3>
        <ul className="dashboard-list">
          {card.source_keys.map((sourceKey) => <li key={sourceKey}>{sourceKey}</li>)}
        </ul>
      </section>
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
