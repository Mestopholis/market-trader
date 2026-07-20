export type DataState = 'ready' | 'stale' | 'partial' | 'unavailable'

export type SourceSummary = {
  name: string
  state: DataState
  version: string
  observed_at: string
  stable_key: string
  digest: string | null
}

export type WarningSummary = {
  code: string
  severity: string
  message: string
  source_keys: string[]
}

export type DashboardOverview = {
  as_of: string
  data_state: DataState
  paper_mode: boolean
  market_state: string
  entry_allowed: boolean
  sources: SourceSummary[]
  warnings: WarningSummary[]
}

export type CandidateListItem = {
  candidate_key: string
  symbol: string
  direction: string
  strategy: string
  score: string
  qualification_state: string
  catalyst_state: string
  risk_state: string
  data_state: DataState
  observed_at: string
  reason_codes: string[]
  source_keys: string[]
}

export type CandidateListResponse = {
  as_of: string
  data_state: DataState
  candidates: CandidateListItem[]
  next_cursor: string | null
  sources: SourceSummary[]
  warnings: WarningSummary[]
}

export type CandidateDetail = {
  candidate_key: string
  symbol: string
  data_state: DataState
  as_of: string
  scanner: Record<string, unknown>
  catalysts: Record<string, unknown>
  options: Record<string, unknown>
  risk: Record<string, unknown>
  sources: SourceSummary[]
  warnings: WarningSummary[]
}

export type RiskSummary = {
  as_of: string
  data_state: DataState
  latest_decision_key: string | null
  status: string
  checks: WarningSummary[]
  active_locks: string[]
  tax_disclaimer: string
  sources: SourceSummary[]
  warnings: WarningSummary[]
}

export type JournalEventSummary = {
  event_key: string
  event_type: string
  occurred_at: string
  correlation_id: string
  actor: string
  source_key: string
  payload_summary: Record<string, unknown>
}

export type JournalEventListResponse = {
  as_of: string
  data_state: DataState
  events: JournalEventSummary[]
  next_cursor: string | null
  sources: SourceSummary[]
  warnings: WarningSummary[]
}

export type AnalyticsSummary = {
  as_of: string
  data_state: DataState
  candidate_counts: Record<string, number>
  strategy_mix: Record<string, number>
  block_reasons: Record<string, number>
  stale_counts: Record<string, number>
  risk_status_distribution: Record<string, number>
  sources: SourceSummary[]
  warnings: WarningSummary[]
}
