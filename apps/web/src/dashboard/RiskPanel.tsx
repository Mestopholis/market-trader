import { useEffect, useState } from 'react'

import { fetchDashboardRisk } from '../api'
import { formatDashboardTime } from './formatting'
import type { RiskSummary } from './types'

type LoadState = { kind: 'loading' } | { kind: 'ready'; risk: RiskSummary } | { kind: 'error' }

export default function RiskPanel() {
  const [state, setState] = useState<LoadState>({ kind: 'loading' })

  useEffect(() => {
    const controller = new AbortController()
    fetchDashboardRisk(controller.signal)
      .then((risk) => setState({ kind: 'ready', risk }))
      .catch(() => {
        if (!controller.signal.aborted) setState({ kind: 'error' })
      })
    return () => controller.abort()
  }, [])

  if (state.kind === 'loading') return <section className="dashboard-panel"><p>Loading risk...</p></section>
  if (state.kind === 'error') {
    return (
      <section role="alert" className="dashboard-panel dashboard-panel-unavailable">
        <h2>Risk unavailable</h2>
        <p>Risk summary data could not be loaded.</p>
      </section>
    )
  }

  const risk = state.risk
  return (
    <section className="dashboard-panel" aria-labelledby="risk-panel-title">
      <h2 id="risk-panel-title">Risk</h2>
      <dl className="dashboard-facts">
        <dt>Status</dt><dd>{risk.status}</dd>
        <dt>Latest decision</dt><dd>{risk.latest_decision_key ?? 'Unavailable'}</dd>
        <dt>As of</dt><dd>{formatDashboardTime(risk.as_of)}</dd>
      </dl>
      <h3>Checks</h3>
      <ul className="dashboard-list">{risk.checks.map((check) => <li key={check.code}>{check.code}: {check.message}</li>)}</ul>
      <h3>Active locks</h3>
      <ul className="dashboard-list">{risk.active_locks.map((lock) => <li key={lock}>{lock}</li>)}</ul>
      <p className="muted">{risk.tax_disclaimer}</p>
    </section>
  )
}
