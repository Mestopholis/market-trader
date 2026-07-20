export type HealthResponse = {
  status: 'ok'
  environment: string
  trading_mode: 'paper'
  version: string
  database: 'ok' | 'unavailable'
}

export type MarketState =
  | 'closed'
  | 'pre_market'
  | 'opening_buffer'
  | 'entry_open'
  | 'entry_closed'
  | 'post_market'

export type MarketStateResponse = {
  market_state: MarketState
  entry_allowed: boolean
  calendar: 'XNYS'
  policy_version: string
  observed_at: string
  valid_until: string
  next_transition: string
  session_date: string | null
  market_open: string | null
  market_close: string | null
  entry_window_open: string | null
  entry_window_close: string | null
  is_early_close: boolean | null
  next_session_date: string
  next_session_open: string
  calendar_timezone: string
  display_timezone: string
}

export type MarketStateUnavailableResponse = {
  market_state: 'unavailable'
  entry_allowed: false
  error_code: 'market_calendar_unavailable'
}

import type {
  AnalyticsSummary,
  CandidateDetail,
  CandidateListResponse,
  DashboardOverview,
  JournalEventListResponse,
  RiskSummary,
} from './dashboard/types'

export async function fetchHealth(signal?: AbortSignal): Promise<HealthResponse> {
  const response = await fetch('/api/health', {
    headers: { Accept: 'application/json' },
    signal,
  })
  if (!response.ok) {
    throw new Error(`Health request failed with ${response.status}`)
  }
  return (await response.json()) as HealthResponse
}

export async function fetchMarketState(signal?: AbortSignal): Promise<MarketStateResponse> {
  const response = await fetch('/api/market-state', {
    headers: { Accept: 'application/json' },
    cache: 'no-store',
    signal,
  })
  if (!response.ok) {
    throw new Error(`Market state request failed with ${response.status}`)
  }
  return (await response.json()) as MarketStateResponse
}

export type CandidateQuery = {
  limit?: number
  cursor?: string
}

export type JournalQuery = {
  limit?: number
  cursor?: string
  eventType?: string
  correlationId?: string
}

export async function fetchDashboardOverview(
  signal?: AbortSignal,
): Promise<DashboardOverview> {
  return dashboardGet('/api/dashboard/overview', 'Dashboard overview', signal)
}

export async function fetchDashboardCandidates(
  query: CandidateQuery = {},
  signal?: AbortSignal,
): Promise<CandidateListResponse> {
  return dashboardGet(`/api/dashboard/candidates${queryString(query)}`, 'Dashboard candidates', signal)
}

export async function fetchDashboardCandidateDetail(
  candidateKey: string,
  signal?: AbortSignal,
): Promise<CandidateDetail> {
  const encodedKey = encodeURIComponent(candidateKey)
  return dashboardGet(
    `/api/dashboard/candidates/${encodedKey}`,
    'Dashboard candidate detail',
    signal,
  )
}

export async function fetchDashboardRisk(signal?: AbortSignal): Promise<RiskSummary> {
  return dashboardGet('/api/dashboard/risk', 'Dashboard risk', signal)
}

export async function fetchDashboardJournal(
  query: JournalQuery = {},
  signal?: AbortSignal,
): Promise<JournalEventListResponse> {
  const params = {
    limit: query.limit,
    cursor: query.cursor,
    event_type: query.eventType,
    correlation_id: query.correlationId,
  }
  return dashboardGet(`/api/dashboard/journal${queryString(params)}`, 'Dashboard journal', signal)
}

export async function fetchDashboardAnalytics(
  signal?: AbortSignal,
): Promise<AnalyticsSummary> {
  return dashboardGet('/api/dashboard/analytics', 'Dashboard analytics', signal)
}

async function dashboardGet<T>(
  url: string,
  label: string,
  signal?: AbortSignal,
): Promise<T> {
  const response = await fetch(url, {
    headers: { Accept: 'application/json' },
    cache: 'no-store',
    signal,
  })
  if (!response.ok) {
    throw new Error(`${label} request failed with ${response.status}`)
  }
  return (await response.json()) as T
}

function queryString(query: Record<string, string | number | undefined>): string {
  const params = new URLSearchParams()
  for (const [key, value] of Object.entries(query)) {
    if (value !== undefined) {
      params.set(key, String(value))
    }
  }
  const rendered = params.toString()
  return rendered ? `?${rendered}` : ''
}
