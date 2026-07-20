import { useEffect, useState } from 'react'

import { fetchPaperPositions } from '../api'
import { formatDashboardTime, labelize } from '../dashboard/formatting'
import type { PaperPosition, PaperPositionsResponse } from './types'

type LoadState =
  | { kind: 'loading' }
  | { kind: 'ready'; positions: PaperPositionsResponse }
  | { kind: 'error' }

export default function PaperPositionsPanel() {
  const [state, setState] = useState<LoadState>({ kind: 'loading' })

  useEffect(() => {
    const controller = new AbortController()
    fetchPaperPositions(controller.signal)
      .then((positions) => setState({ kind: 'ready', positions }))
      .catch(() => {
        if (!controller.signal.aborted) setState({ kind: 'error' })
      })
    return () => controller.abort()
  }, [])

  if (state.kind === 'loading') {
    return <section className="dashboard-panel"><p>Loading paper positions...</p></section>
  }

  if (state.kind === 'error') {
    return (
      <section role="alert" className="dashboard-panel dashboard-panel-unavailable">
        <h2>Paper positions unavailable</h2>
        <p>Paper position state could not be loaded.</p>
      </section>
    )
  }

  return (
    <section className="dashboard-panel" aria-labelledby="paper-positions-title">
      <div className="dashboard-panel-heading">
        <h2 id="paper-positions-title">Paper positions</h2>
        <span className="state-chip">{state.positions.positions.length} open</span>
      </div>

      {state.positions.positions.length === 0 ? (
        <p className="muted">No paper positions are open.</p>
      ) : (
        <div className="paper-position-grid">
          {state.positions.positions.map((position) => (
            <article key={position.position_key} className="paper-position-row">
              <div className="dashboard-panel-heading">
                <h3>{position.symbol}</h3>
                <span className={`state-chip state-${position.status}`}>
                  {labelize(position.status)}
                </span>
              </div>
              <dl className="dashboard-facts">
                <dt>Quantity</dt><dd>{position.quantity}</dd>
                <dt>Average price</dt><dd>{formatCurrency(position.average_price)}</dd>
                <dt>Realized P/L</dt><dd>{formatCurrency(position.realized_pl)}</dd>
                <dt>Unrealized P/L</dt><dd>{formatCurrency(position.unrealized_pl)}</dd>
                <dt>Updated</dt><dd>{formatDashboardTime(position.updated_at)}</dd>
                <dt>Risk decision</dt><dd>{position.risk_decision_key}</dd>
              </dl>
              <PaperExitRules position={position} />
              {position.status === 'assigned' && <p className="muted">Assignment scenario warning</p>}
            </article>
          ))}
        </div>
      )}
    </section>
  )
}

function PaperExitRules({ position }: { position: PaperPosition }) {
  const stopLoss = textValue(position.exit_rules.stop_loss)
  const target = textValue(position.exit_rules.target)
  const expiresAt = textValue(position.exit_rules.expires_at)
  if (!stopLoss && !target && !expiresAt) return null
  return (
    <ul className="paper-token-list">
      {stopLoss && <li><span className="state-chip">Stop {formatCurrency(stopLoss)}</span></li>}
      {target && <li><span className="state-chip">Target {formatCurrency(target)}</span></li>}
      {expiresAt && <li><span className="state-chip">Expires {expiresAt}</span></li>}
    </ul>
  )
}

function textValue(value: unknown): string | null {
  return typeof value === 'string' && value.trim() ? value : null
}

function formatCurrency(value: string | null | undefined): string {
  if (!value) return 'Unavailable'
  const numeric = Number(value)
  if (Number.isNaN(numeric)) return value
  return new Intl.NumberFormat('en-US', {
    style: 'currency',
    currency: 'USD',
  }).format(numeric)
}
