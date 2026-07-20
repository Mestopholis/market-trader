import { useEffect, useState } from 'react'

import { fetchHealth } from './api'
import DashboardShell from './dashboard/DashboardShell'
import './index.css'

type LoadState =
  | { kind: 'loading' }
  | { kind: 'ready' }
  | { kind: 'error' }

export default function App() {
  const [state, setState] = useState<LoadState>({ kind: 'loading' })

  useEffect(() => {
    const controller = new AbortController()
    fetchHealth(controller.signal)
      .then(() => setState({ kind: 'ready' }))
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

  return <DashboardShell />
}
