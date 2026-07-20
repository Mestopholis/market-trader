import { useEffect, useState } from 'react'

import { fetchDashboardOverview } from '../api'
import { formatDashboardTime, labelize } from './formatting'
import type { DashboardOverview } from './types'

type LoadState =
  | { kind: 'loading' }
  | { kind: 'ready'; overview: DashboardOverview }
  | { kind: 'error' }

export default function OverviewPanel() {
  const [state, setState] = useState<LoadState>({ kind: 'loading' })

  useEffect(() => {
    const controller = new AbortController()
    fetchDashboardOverview(controller.signal)
      .then((overview) => setState({ kind: 'ready', overview }))
      .catch(() => {
        if (!controller.signal.aborted) setState({ kind: 'error' })
      })
    return () => controller.abort()
  }, [])

  if (state.kind === 'loading') {
    return <section className="dashboard-panel"><p>Loading market overview...</p></section>
  }

  if (state.kind === 'error') {
    return (
      <section role="alert" className="dashboard-panel dashboard-panel-unavailable">
        <h2>Market overview unavailable</h2>
        <p>Dashboard overview data could not be loaded.</p>
      </section>
    )
  }

  const overview = state.overview
  return (
    <section className="dashboard-panel" aria-labelledby="overview-panel-title">
      <h2 id="overview-panel-title">Market overview</h2>
      <dl className="dashboard-facts">
        <dt>Market state</dt><dd>{overview.market_state}</dd>
        <dt>Data state</dt><dd>{overview.data_state}</dd>
        <dt>As of</dt><dd>{formatDashboardTime(overview.as_of)}</dd>
      </dl>
      <h3>Sources</h3>
      <div className="dashboard-table-wrap">
        <table className="dashboard-table">
          <thead>
            <tr><th>Source</th><th>State</th><th>Version</th><th>Observed</th></tr>
          </thead>
          <tbody>
            {overview.sources.map((source) => (
              <tr key={source.stable_key}>
                <td>{labelize(source.name)}</td>
                <td><span className={`state-chip state-${source.state}`}>{source.state}</span></td>
                <td>{source.version}</td>
                <td>{formatDashboardTime(source.observed_at)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {overview.warnings.length > 0 && (
        <ul className="dashboard-warnings">
          {overview.warnings.map((warning) => (
            <li key={warning.code}>{warning.message}</li>
          ))}
        </ul>
      )}
    </section>
  )
}
