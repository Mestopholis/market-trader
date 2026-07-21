import type { ReadinessResponse } from '../api'

type SystemHealthPanelProps = {
  correlationId?: string
  readiness: ReadinessResponse
}

export default function SystemHealthPanel({ correlationId, readiness }: SystemHealthPanelProps) {
  return (
    <section className="dashboard-panel" aria-labelledby="system-health-title">
      <div className="dashboard-panel-heading">
        <div>
          <h2 id="system-health-title">System health</h2>
          <p className="muted">{readiness.status}</p>
        </div>
        {correlationId ? <span className="state-chip">{correlationId}</span> : null}
      </div>
      <div className="dashboard-table-wrap">
        <table className="dashboard-table operations-table">
          <thead>
            <tr>
              <th>Component</th>
              <th>Status</th>
              <th>Code</th>
              <th>Summary</th>
            </tr>
          </thead>
          <tbody>
            {readiness.components.map((component) => (
              <tr key={`${component.name}:${component.code}`}>
                <td>{component.name}</td>
                <td><span className={`state-chip state-${component.status}`}>{component.status}</span></td>
                <td>{component.code}</td>
                <td>{component.summary}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  )
}
