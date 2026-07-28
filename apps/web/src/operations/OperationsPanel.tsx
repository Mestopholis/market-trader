import { useEffect, useState } from 'react'

import { fetchReadinessWithMeta, recoverPaperLifecycleWithMeta } from '../api'
import {
  fetchSchwabBrokerStatusWithMeta,
  refreshSchwabQuotes,
  refreshSchwabAccountsToken,
  refreshSchwabToken,
  runSchwabLiveScan,
  revokeSchwabAccountsToken,
  revokeSchwabToken,
} from '../broker/api'
import BrokerStatusPanel from '../broker/BrokerStatusPanel'
import type { SchwabBrokerStatus } from '../broker/types'
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
      brokerStatus: SchwabBrokerStatus
      brokerCorrelationId?: string
      recovery: PaperRecoveryResponse
      recoveryCorrelationId?: string
    }
  | { kind: 'error'; area: 'health' | 'recovery' }

export default function OperationsPanel() {
  const [state, setState] = useState<PanelState>({ kind: 'loading' })

  async function loadAll(signal?: AbortSignal) {
    try {
      const readiness = await fetchReadinessWithMeta(signal)
      const brokerStatus = await fetchSchwabBrokerStatusWithMeta(signal)
      const recovery = await recoverPaperLifecycleWithMeta(signal)
      setState({
        kind: 'ready',
        readiness: readiness.data,
        readinessCorrelationId: readiness.correlationId,
        brokerStatus: brokerStatus.data,
        brokerCorrelationId: brokerStatus.correlationId,
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

  async function refreshBrokerToken() {
    if (state.kind !== 'ready') return
    try {
      await refreshSchwabToken()
      const brokerStatus = await fetchSchwabBrokerStatusWithMeta()
      setState({
        ...state,
        brokerStatus: brokerStatus.data,
        brokerCorrelationId: brokerStatus.correlationId,
      })
    } catch {
      setState({ kind: 'error', area: 'health' })
    }
  }

  async function revokeBrokerToken() {
    if (state.kind !== 'ready') return
    try {
      await revokeSchwabToken()
      const brokerStatus = await fetchSchwabBrokerStatusWithMeta()
      setState({
        ...state,
        brokerStatus: brokerStatus.data,
        brokerCorrelationId: brokerStatus.correlationId,
      })
    } catch {
      setState({ kind: 'error', area: 'health' })
    }
  }

  async function refreshLiveQuote() {
    if (state.kind !== 'ready') return
    try {
      await refreshSchwabQuotes(['SPY'])
      const brokerStatus = await fetchSchwabBrokerStatusWithMeta()
      setState({
        ...state,
        brokerStatus: brokerStatus.data,
        brokerCorrelationId: brokerStatus.correlationId,
      })
    } catch {
      setState({ kind: 'error', area: 'health' })
    }
  }

  async function runLiveScanner() {
    if (state.kind !== 'ready') return
    try {
      await runSchwabLiveScan()
      const brokerStatus = await fetchSchwabBrokerStatusWithMeta()
      setState({
        ...state,
        brokerStatus: brokerStatus.data,
        brokerCorrelationId: brokerStatus.correlationId,
      })
    } catch {
      setState({ kind: 'error', area: 'health' })
    }
  }

  async function refreshAccountsToken() {
    if (state.kind !== 'ready') return
    try {
      await refreshSchwabAccountsToken()
      const brokerStatus = await fetchSchwabBrokerStatusWithMeta()
      setState({
        ...state,
        brokerStatus: brokerStatus.data,
        brokerCorrelationId: brokerStatus.correlationId,
      })
    } catch {
      setState({ kind: 'error', area: 'health' })
    }
  }

  async function revokeAccountsToken() {
    if (state.kind !== 'ready') return
    try {
      await revokeSchwabAccountsToken()
      const brokerStatus = await fetchSchwabBrokerStatusWithMeta()
      setState({
        ...state,
        brokerStatus: brokerStatus.data,
        brokerCorrelationId: brokerStatus.correlationId,
      })
    } catch {
      setState({ kind: 'error', area: 'health' })
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
      <BrokerStatusPanel
        status={state.brokerStatus}
        correlationId={state.brokerCorrelationId}
        onRefresh={refreshBrokerToken}
        onRevoke={revokeBrokerToken}
        onQuoteRefresh={refreshLiveQuote}
        onLiveScan={runLiveScanner}
        onAccountsRefresh={refreshAccountsToken}
        onAccountsRevoke={revokeAccountsToken}
      />
      <RecoveryPanel
        recovery={state.recovery}
        correlationId={state.recoveryCorrelationId}
        onRefresh={refreshRecovery}
      />
    </div>
  )
}
