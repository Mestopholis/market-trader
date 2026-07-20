import { Fragment, useEffect, useState } from 'react'

import { fetchDashboardAnalytics } from '../api'
import type { AnalyticsSummary } from './types'

type LoadState =
  | { kind: 'loading' }
  | { kind: 'ready'; analytics: AnalyticsSummary }
  | { kind: 'error' }

export default function AnalyticsPanel() {
  const [state, setState] = useState<LoadState>({ kind: 'loading' })

  useEffect(() => {
    const controller = new AbortController()
    fetchDashboardAnalytics(controller.signal)
      .then((analytics) => setState({ kind: 'ready', analytics }))
      .catch(() => {
        if (!controller.signal.aborted) setState({ kind: 'error' })
      })
    return () => controller.abort()
  }, [])

  if (state.kind === 'loading') return <section className="dashboard-panel"><p>Loading analytics...</p></section>
  if (state.kind === 'error') {
    return (
      <section role="alert" className="dashboard-panel dashboard-panel-unavailable">
        <h2>Analytics unavailable</h2>
        <p>Analytics data could not be loaded.</p>
      </section>
    )
  }

  const analytics = state.analytics
  return (
    <section className="dashboard-panel" aria-labelledby="analytics-panel-title">
      <h2 id="analytics-panel-title">Analytics</h2>
      <MetricGroup title="Candidates" metrics={analytics.candidate_counts} />
      <MetricGroup title="Strategy mix" metrics={analytics.strategy_mix} />
      <MetricGroup title="Block reasons" metrics={analytics.block_reasons} />
      <MetricGroup title="Stale data" metrics={analytics.stale_counts} />
      <MetricGroup title="Risk status" metrics={analytics.risk_status_distribution} />
    </section>
  )
}

function MetricGroup({ title, metrics }: { title: string; metrics: Record<string, number> }) {
  return (
    <section className="dashboard-subsection" aria-label={title}>
      <h3>{title}</h3>
      <dl className="dashboard-facts">
        {Object.entries(metrics).map(([key, value]) => (
          <Fragment key={key}>
            <dt>{key}</dt>
            <dd>{value}</dd>
          </Fragment>
        ))}
      </dl>
    </section>
  )
}
