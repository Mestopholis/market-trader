import { useEffect, useMemo, useState } from 'react'

import { fetchDashboardCandidates } from '../api'
import { formatDashboardTime } from './formatting'
import type { CandidateListResponse } from './types'

type LoadState =
  | { kind: 'loading' }
  | { kind: 'ready'; candidates: CandidateListResponse }
  | { kind: 'error' }

export default function ScannerPanel() {
  const [state, setState] = useState<LoadState>({ kind: 'loading' })
  const [filter, setFilter] = useState('')

  useEffect(() => {
    const controller = new AbortController()
    fetchDashboardCandidates({ limit: 50 }, controller.signal)
      .then((candidates) => setState({ kind: 'ready', candidates }))
      .catch(() => {
        if (!controller.signal.aborted) setState({ kind: 'error' })
      })
    return () => controller.abort()
  }, [])

  const visibleCandidates = useMemo(() => {
    if (state.kind !== 'ready') return []
    const normalized = filter.trim().toUpperCase()
    if (!normalized) return state.candidates.candidates
    return state.candidates.candidates.filter((candidate) => candidate.symbol.includes(normalized))
  }, [filter, state])

  if (state.kind === 'loading') {
    return <section className="dashboard-panel"><p>Loading scanner candidates...</p></section>
  }

  if (state.kind === 'error') {
    return (
      <section role="alert" className="dashboard-panel dashboard-panel-unavailable">
        <h2>Scanner unavailable</h2>
        <p>Scanner candidates could not be loaded.</p>
      </section>
    )
  }

  return (
    <section className="dashboard-panel" aria-labelledby="scanner-panel-title">
      <div className="dashboard-panel-heading">
        <h2 id="scanner-panel-title">Scanner</h2>
        <label className="filter-label">
          Filter candidates
          <input
            value={filter}
            onChange={(event) => setFilter(event.target.value)}
            aria-label="Filter candidates"
          />
        </label>
      </div>
      <div className="dashboard-table-wrap">
        <table className="dashboard-table">
          <thead>
            <tr>
              <th>Symbol</th><th>Direction</th><th>Strategy</th><th>Score</th>
              <th>State</th><th>Risk</th><th>Reasons</th><th>Observed</th>
            </tr>
          </thead>
          <tbody>
            {visibleCandidates.map((candidate) => (
              <tr key={candidate.candidate_key}>
                <td>{candidate.symbol}</td>
                <td>{candidate.direction}</td>
                <td>{candidate.strategy}</td>
                <td>{candidate.score}</td>
                <td><span className={`state-chip state-${candidate.data_state}`}>{candidate.data_state}</span></td>
                <td>{candidate.risk_state}</td>
                <td>{candidate.reason_codes.join(', ')}</td>
                <td>{formatDashboardTime(candidate.observed_at)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  )
}
