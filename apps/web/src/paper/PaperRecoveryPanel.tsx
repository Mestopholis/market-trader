import { useEffect, useState } from 'react'

import { recoverPaperLifecycle } from '../api'
import { labelize } from '../dashboard/formatting'
import type { PaperRecoveryResponse } from './types'

type LoadState =
  | { kind: 'loading' }
  | { kind: 'ready'; recovery: PaperRecoveryResponse }
  | { kind: 'error' }

export default function PaperRecoveryPanel() {
  const [state, setState] = useState<LoadState>({ kind: 'loading' })

  useEffect(() => {
    void loadRecovery()
  }, [])

  async function loadRecovery() {
    try {
      setState({ kind: 'ready', recovery: await recoverPaperLifecycle() })
    } catch {
      setState({ kind: 'error' })
    }
  }

  if (state.kind === 'loading') {
    return <section className="dashboard-panel"><p>Loading paper recovery...</p></section>
  }

  if (state.kind === 'error') {
    return (
      <section role="alert" className="dashboard-panel dashboard-panel-unavailable">
        <h2>Paper recovery unavailable</h2>
        <p>Paper recovery state could not be loaded.</p>
      </section>
    )
  }

  const recovery = state.recovery
  return (
    <section className="dashboard-panel" aria-labelledby="paper-recovery-title">
      <div className="dashboard-panel-heading">
        <h2 id="paper-recovery-title">Paper recovery</h2>
        <button type="button" className="paper-action-button" onClick={loadRecovery}>
          Refresh paper recovery
        </button>
      </div>
      <div className="paper-recovery-grid">
        <RecoveryFact count={recovery.open_approvals.length} singular="open approval" />
        <RecoveryFact count={recovery.working_orders.length} singular="working order" />
        <RecoveryFact count={recovery.timed_out_orders.length} singular="timed-out order" />
        <RecoveryFact count={recovery.open_positions.length} singular="open position" />
      </div>
      <section className="dashboard-subsection" aria-labelledby="timed-out-orders-title">
        <h3 id="timed-out-orders-title">Timed-out paper orders</h3>
        {recovery.timed_out_orders.length === 0 ? (
          <p className="muted">No timed-out paper orders.</p>
        ) : (
          <ul className="dashboard-list">
            {recovery.timed_out_orders.map((order) => (
              <li key={order.order_id}>{order.order_id} · {labelize(order.status)}</li>
            ))}
          </ul>
        )}
      </section>
    </section>
  )
}

function RecoveryFact({ count, singular }: { count: number; singular: string }) {
  return <span className="state-chip">{count} {count === 1 ? singular : `${singular}s`}</span>
}
