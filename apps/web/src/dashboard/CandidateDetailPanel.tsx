import { Fragment, useEffect, useState } from 'react'

import { fetchDashboardCandidateDetail } from '../api'
import { formatDashboardTime } from './formatting'
import type { CandidateDetail } from './types'

type LoadState =
  | { kind: 'loading' }
  | { kind: 'ready'; detail: CandidateDetail }
  | { kind: 'error' }

export default function CandidateDetailPanel({ candidateKey = 'candidate:aapl' }: { candidateKey?: string }) {
  const [state, setState] = useState<LoadState>({ kind: 'loading' })

  useEffect(() => {
    const controller = new AbortController()
    fetchDashboardCandidateDetail(candidateKey, controller.signal)
      .then((detail) => setState({ kind: 'ready', detail }))
      .catch(() => {
        if (!controller.signal.aborted) setState({ kind: 'error' })
      })
    return () => controller.abort()
  }, [candidateKey])

  if (state.kind === 'loading') return <section className="dashboard-panel"><p>Loading candidate detail...</p></section>
  if (state.kind === 'error') {
    return (
      <section role="alert" className="dashboard-panel dashboard-panel-unavailable">
        <h2>Candidate detail unavailable</h2>
        <p>Candidate trace data could not be loaded.</p>
      </section>
    )
  }

  const detail = state.detail
  return (
    <section className="dashboard-panel" aria-labelledby="candidate-detail-title">
      <h2 id="candidate-detail-title">Candidate detail</h2>
      <dl className="dashboard-facts">
        <dt>Symbol</dt><dd>{detail.symbol}</dd>
        <dt>State</dt><dd>{detail.data_state}</dd>
        <dt>As of</dt><dd>{formatDashboardTime(detail.as_of)}</dd>
      </dl>
      <PayloadSection title="Scanner" payload={detail.scanner} />
      <PayloadSection title="Catalysts" payload={detail.catalysts} />
      <PayloadSection title="Options" payload={detail.options} />
      <PayloadSection title="Risk" payload={detail.risk} />
      <h3>Sources</h3>
      <ul className="dashboard-list">
        {detail.sources.map((source) => (
          <li key={source.stable_key}>{source.stable_key}</li>
        ))}
      </ul>
    </section>
  )
}

function PayloadSection({ title, payload }: { title: string; payload: Record<string, unknown> }) {
  return (
    <section className="dashboard-subsection" aria-label={title}>
      <h3>{title}</h3>
      <dl className="dashboard-facts">
        {Object.entries(payload).map(([key, value]) => (
          <Fragment key={key}>
            <dt>{key}</dt>
            <dd>{String(value)}</dd>
          </Fragment>
        ))}
      </dl>
    </section>
  )
}
