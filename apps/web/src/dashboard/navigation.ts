export type DashboardView =
  | 'overview'
  | 'scanner'
  | 'candidate'
  | 'risk'
  | 'journal'
  | 'analytics'
  | 'paperApprovals'
  | 'paperOrders'
  | 'paperPositions'
  | 'paperRecovery'

export type DashboardNavItem = {
  id: DashboardView
  label: string
}

export const dashboardNavigation: DashboardNavItem[] = [
  { id: 'overview', label: 'Overview' },
  { id: 'scanner', label: 'Scanner' },
  { id: 'candidate', label: 'Candidate' },
  { id: 'risk', label: 'Risk' },
  { id: 'journal', label: 'Journal' },
  { id: 'analytics', label: 'Analytics' },
  { id: 'paperApprovals', label: 'Paper Approvals' },
  { id: 'paperOrders', label: 'Paper Orders' },
  { id: 'paperPositions', label: 'Paper Positions' },
  { id: 'paperRecovery', label: 'Paper Recovery' },
]
