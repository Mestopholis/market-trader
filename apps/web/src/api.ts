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
