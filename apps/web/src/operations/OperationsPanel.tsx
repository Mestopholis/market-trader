import { useEffect, useState } from 'react'

import { fetchReadinessWithMeta, recoverPaperLifecycleWithMeta } from '../api'
import type { PaperRecoveryResponse } from '../paper/types'
import RecoveryPanel from './RecoveryPanel'
import SystemHealthPanel from './SystemHealthPanel'
import type { ReadinessResponse } from '../api'

type PanelState =
  | { kind: 'loading' }
  | {
      kind: 'ready'
      readiness: ReadinessResponse
      readinessCorrelationId?: string
      recovery: PaperRecoveryResponse
      recoveryCorrelationId?: string
    }
  | { kind: 'error'; area: 'health' | 'recovery' }

export default function OperationsPanel() {
  const [state, setState] = useState<PanelState>({ kind: 'loading' })

  async function loadAll(signal?: AbortSignal) {
    try {
      const readiness = await fetchReadinessWithMeta(signal)
      const recovery = await recoverPaperLifecycleWithMeta(signal)
      setState({
        kind: 'ready',
        readiness: readiness.data,
        readinessCorrelationId: readiness.correlationId,
        recovery: recovery.data,
        recoveryCorrelationId: recovery.correlationId,
      })
    } catch {
      if (!signal?.aborted) setState({ kind: 'error', area: 'health' })
    }
  }

  async function refreshRecovery() {
    if (state.kind !== 'ready') return
    try {
      const recovery = await recoverPaperLifecycleWithMeta()
      setState({
        ...state,
        recovery: recovery.data,
        recoveryCorrelationId: recovery.correlationId,
      })
    } catch {
      setState({ kind: 'error', area: 'recovery' })
    }
  }

  useEffect(() => {
    const controller = new AbortController()
    void loadAll(controller.signal)
    return () => controller.abort()
  }, [])

  if (state.kind === 'loading') {
    return <section className="dashboard-panel"><p>Loading operations state...</p></section>
  }

  if (state.kind === 'error') {
    return (
      <section role="alert" className="dashboard-panel-unavailable">
        <h2>{state.area === 'recovery' ? 'Recovery drill unavailable' : 'System health unavailable'}</h2>
        <p>Operations state could not be loaded.</p>
      </section>
    )
  }

  return (
    <div className="dashboard-stack">
      <SystemHealthPanel readiness={state.readiness} correlationId={state.readinessCorrelationId} />
      <RecoveryPanel
        recovery={state.recovery}
        correlationId={state.recoveryCorrelationId}
        onRefresh={refreshRecovery}
      />
    </div>
  )
}
