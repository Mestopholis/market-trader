import { useEffect, useState } from 'react'

import { fetchDashboardJournal } from '../api'
import { formatDashboardTime } from './formatting'
import type { JournalEventListResponse } from './types'

type LoadState =
  | { kind: 'loading' }
  | { kind: 'ready'; journal: JournalEventListResponse }
  | { kind: 'error' }

export default function JournalPanel() {
  const [state, setState] = useState<LoadState>({ kind: 'loading' })

  useEffect(() => {
    const controller = new AbortController()
    fetchDashboardJournal({ limit: 50 }, controller.signal)
      .then((journal) => setState({ kind: 'ready', journal }))
      .catch(() => {
        if (!controller.signal.aborted) setState({ kind: 'error' })
      })
    return () => controller.abort()
  }, [])

  if (state.kind === 'loading') return <section className="dashboard-panel"><p>Loading journal...</p></section>
  if (state.kind === 'error') {
    return (
      <section role="alert" className="dashboard-panel dashboard-panel-unavailable">
        <h2>Journal unavailable</h2>
        <p>Journal events could not be loaded.</p>
      </section>
    )
  }

  return (
    <section className="dashboard-panel" aria-labelledby="journal-panel-title">
      <h2 id="journal-panel-title">Journal</h2>
      <div className="dashboard-table-wrap">
        <table className="dashboard-table">
          <thead><tr><th>Event</th><th>Correlation</th><th>Source</th><th>Occurred</th></tr></thead>
          <tbody>
            {state.journal.events.map((event) => (
              <tr key={event.event_key}>
                <td>{event.event_type}</td>
                <td>{event.correlation_id}</td>
                <td>{event.source_key}</td>
                <td>{formatDashboardTime(event.occurred_at)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  )
}
