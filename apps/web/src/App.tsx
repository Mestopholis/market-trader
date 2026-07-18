import { useEffect, useState } from 'react'

import { fetchHealth, type HealthResponse } from './api'
import './index.css'

type LoadState =
  | { kind: 'loading' }
  | { kind: 'ready'; health: HealthResponse }
  | { kind: 'error' }

export default function App() {
  const [state, setState] = useState<LoadState>({ kind: 'loading' })

  useEffect(() => {
    const controller = new AbortController()
    fetchHealth(controller.signal)
      .then((health) => setState({ kind: 'ready', health }))
      .catch(() => {
        if (!controller.signal.aborted) setState({ kind: 'error' })
      })
    return () => controller.abort()
  }, [])

  if (state.kind === 'loading') {
    return <main><p>Checking system safety state…</p></main>
  }

  if (state.kind === 'error') {
    return (
      <main>
        <section role="alert" className="unavailable">
          <h1>Trading controls unavailable</h1>
          <p>The backend safety state could not be verified.</p>
        </section>
      </main>
    )
  }

  return (
    <main>
      <section role="status" className="paper-banner">
        <strong>PAPER MODE</strong>
        <span>No live orders can be submitted.</span>
      </section>
      <h1>Market Trader</h1>
      <dl>
        <dt>Environment</dt><dd>{state.health.environment}</dd>
        <dt>Version</dt><dd>{state.health.version}</dd>
        <dt>Database</dt><dd>{state.health.database}</dd>
      </dl>
    </main>
  )
}
