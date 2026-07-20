import { type ReactNode, useState } from 'react'

import DashboardErrorBoundary from './DashboardErrorBoundary'
import { dashboardNavigation, type DashboardView } from './navigation'
import OverviewPanel from './OverviewPanel'
import ScannerPanel from './ScannerPanel'

type DashboardShellProps = {
  panels?: Partial<Record<DashboardView, ReactNode>>
}

const defaultPanels: Record<DashboardView, ReactNode> = {
  overview: <OverviewPanel />,
  scanner: <ScannerPanel />,
  candidate: <PlaceholderPanel title="Candidate" />,
  risk: <PlaceholderPanel title="Risk" />,
  journal: <PlaceholderPanel title="Journal" />,
  analytics: <PlaceholderPanel title="Analytics" />,
}

export default function DashboardShell({ panels = {} }: DashboardShellProps) {
  const [activeView, setActiveView] = useState<DashboardView>('overview')
  const activeItem = dashboardNavigation.find((item) => item.id === activeView)
  const activeLabel = activeItem?.label ?? 'Overview'
  const mergedPanels = { ...defaultPanels, ...panels }

  return (
    <main className="dashboard-shell">
      <section role="status" className="paper-banner">
        <strong>PAPER MODE</strong>
        <span>No live orders can be submitted.</span>
      </section>
      <header className="dashboard-header">
        <h1>Market Trader</h1>
      </header>
      <nav aria-label="Dashboard views" className="dashboard-tabs">
        {dashboardNavigation.map((item) => (
          <button
            key={item.id}
            type="button"
            role="tab"
            aria-selected={activeView === item.id}
            className="dashboard-tab"
            onClick={() => setActiveView(item.id)}
          >
            {item.label}
          </button>
        ))}
      </nav>
      <section role="tabpanel" aria-label={activeLabel} className="dashboard-tabpanel">
        <DashboardErrorBoundary panelName={activeLabel}>
          {mergedPanels[activeView]}
        </DashboardErrorBoundary>
      </section>
    </main>
  )
}

function PlaceholderPanel({ title }: { title: string }) {
  return (
    <section className="dashboard-panel" aria-labelledby={`${title.toLowerCase()}-panel-title`}>
      <h2 id={`${title.toLowerCase()}-panel-title`}>{title}</h2>
      <p className="muted">Read-only dashboard data will appear here.</p>
    </section>
  )
}
