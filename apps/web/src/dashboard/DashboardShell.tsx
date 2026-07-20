import { type ReactNode, useState } from 'react'

import DashboardErrorBoundary from './DashboardErrorBoundary'
import AnalyticsPanel from './AnalyticsPanel'
import CandidateDetailPanel from './CandidateDetailPanel'
import JournalPanel from './JournalPanel'
import { dashboardNavigation, type DashboardView } from './navigation'
import OverviewPanel from './OverviewPanel'
import ApprovalQueue from '../paper/ApprovalQueue'
import RiskPanel from './RiskPanel'
import ScannerPanel from './ScannerPanel'

type DashboardShellProps = {
  panels?: Partial<Record<DashboardView, ReactNode>>
}

const defaultPanels: Record<DashboardView, ReactNode> = {
  overview: <OverviewPanel />,
  scanner: <ScannerPanel />,
  candidate: <CandidateDetailPanel />,
  risk: <RiskPanel />,
  journal: <JournalPanel />,
  analytics: <AnalyticsPanel />,
  paperApprovals: <ApprovalQueue />,
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
