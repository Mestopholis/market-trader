import type { PaperRecoveryResponse } from '../paper/types'

type RecoveryPanelProps = {
  correlationId?: string
  recovery: PaperRecoveryResponse
  onRefresh: () => void
}

export default function RecoveryPanel({ correlationId, recovery, onRefresh }: RecoveryPanelProps) {
  return (
    <section className="dashboard-panel" aria-labelledby="operations-recovery-title">
      <div className="dashboard-panel-heading">
        <div>
          <h2 id="operations-recovery-title">Recovery drill</h2>
          <p className="muted">Paper lifecycle reconciliation</p>
        </div>
        <div className="operations-actions">
          {correlationId ? <span className="state-chip">{correlationId}</span> : null}
          <button type="button" className="paper-action-button" onClick={onRefresh}>
            Refresh recovery drill
          </button>
        </div>
      </div>
      <div className="paper-recovery-grid">
        <RecoveryFact count={recovery.open_approvals.length} singular="open approval" />
        <RecoveryFact count={recovery.working_orders.length} singular="working order" />
        <RecoveryFact count={recovery.timed_out_orders.length} singular="timed-out order" />
        <RecoveryFact count={recovery.open_positions.length} singular="open position" />
      </div>
    </section>
  )
}

function RecoveryFact({ count, singular }: { count: number; singular: string }) {
  return <span className="state-chip">{count} {count === 1 ? singular : `${singular}s`}</span>
}
