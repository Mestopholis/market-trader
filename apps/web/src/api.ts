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
import type {
  ModifyPaperApprovalCardRequest,
  PaperApproval,
  PaperApprovalCardListResponse,
  PaperOrderActionResponse,
  PaperOrdersResponse,
  PaperPositionsResponse,
  PaperPreview,
  PaperRecoveryResponse,
  ReplacePaperOrderRequest,
  SubmitPaperApprovalRequest,
  SubmittedPaperOrder,
} from './paper/types'

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

export async function fetchPaperApprovalCards(
  signal?: AbortSignal,
): Promise<PaperApprovalCardListResponse> {
  return paperGet('/api/paper/approval-cards', 'Paper approval cards', signal)
}

export async function approvePaperApprovalCard(
  cardKey: string,
  signal?: AbortSignal,
): Promise<PaperApproval> {
  const encodedKey = encodeURIComponent(cardKey)
  return paperPost(
    `/api/paper/approval-cards/${encodedKey}/approve`,
    'Paper approval approve',
    undefined,
    signal,
  )
}

export async function modifyPaperApprovalCard(
  cardKey: string,
  request: ModifyPaperApprovalCardRequest,
  signal?: AbortSignal,
): Promise<PaperApproval> {
  const encodedKey = encodeURIComponent(cardKey)
  return paperPost(
    `/api/paper/approval-cards/${encodedKey}/modify`,
    'Paper approval modify',
    request,
    signal,
  )
}

export async function rejectPaperApprovalCard(
  cardKey: string,
  signal?: AbortSignal,
): Promise<PaperApproval> {
  const encodedKey = encodeURIComponent(cardKey)
  return paperPost(
    `/api/paper/approval-cards/${encodedKey}/reject`,
    'Paper approval reject',
    undefined,
    signal,
  )
}

export async function previewPaperApproval(
  approvalId: string,
  signal?: AbortSignal,
): Promise<PaperPreview> {
  const encodedId = encodeURIComponent(approvalId)
  return paperPost(
    `/api/paper/approvals/${encodedId}/preview`,
    'Paper approval preview',
    undefined,
    signal,
  )
}

export async function submitPaperApproval(
  approvalId: string,
  request: SubmitPaperApprovalRequest,
  signal?: AbortSignal,
): Promise<SubmittedPaperOrder> {
  const encodedId = encodeURIComponent(approvalId)
  return paperPost(
    `/api/paper/approvals/${encodedId}/submit`,
    'Paper approval submit',
    request,
    signal,
  )
}

export async function cancelPaperOrder(
  orderId: string,
  signal?: AbortSignal,
): Promise<PaperOrderActionResponse> {
  const encodedId = encodeURIComponent(orderId)
  return paperPost(
    `/api/paper/orders/${encodedId}/cancel`,
    'Paper order cancel',
    undefined,
    signal,
  )
}

export async function replacePaperOrder(
  orderId: string,
  request: ReplacePaperOrderRequest,
  signal?: AbortSignal,
): Promise<PaperOrderActionResponse> {
  const encodedId = encodeURIComponent(orderId)
  return paperPost(
    `/api/paper/orders/${encodedId}/replace`,
    'Paper order replace',
    request,
    signal,
  )
}

export async function fetchPaperOrders(signal?: AbortSignal): Promise<PaperOrdersResponse> {
  return paperGet('/api/paper/orders', 'Paper orders', signal)
}

export async function fetchPaperPositions(
  signal?: AbortSignal,
): Promise<PaperPositionsResponse> {
  return paperGet('/api/paper/positions', 'Paper positions', signal)
}

export async function recoverPaperLifecycle(
  signal?: AbortSignal,
): Promise<PaperRecoveryResponse> {
  return paperPost('/api/paper/recover', 'Paper recovery', undefined, signal)
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

async function paperGet<T>(
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

async function paperPost<T>(
  url: string,
  label: string,
  body?: Record<string, unknown>,
  signal?: AbortSignal,
): Promise<T> {
  const response = await fetch(
    url,
    body === undefined
      ? {
          method: 'POST',
          headers: { Accept: 'application/json' },
          cache: 'no-store',
          signal,
        }
      : {
          method: 'POST',
          headers: {
            Accept: 'application/json',
            'Content-Type': 'application/json',
          },
          body: JSON.stringify(body),
          cache: 'no-store',
          signal,
        },
  )
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
