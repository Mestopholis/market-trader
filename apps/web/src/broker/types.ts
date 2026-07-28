export type SchwabConnectionState =
  | 'unconfigured'
  | 'disconnected'
  | 'connected'
  | 'expired'
  | 'revoked'

export type SchwabAccountsTradingState = SchwabConnectionState

export type SchwabMarketDataState =
  | 'unconfigured'
  | 'unknown'
  | 'available'
  | 'stale'
  | 'rate_limited'
  | 'unavailable'
  | 'quarantined'

export type SchwabTokenStatus = {
  token_id: string
  product: string
  status: string
  token_type: string
  scope: string
  access_token_expires_at: string
  refresh_token_expires_at: string | null
  encryption_key_id: string
  issued_at: string
  refreshed_at: string | null
  revoked_at: string | null
  last_error_code: string | null
  last_error_at: string | null
  is_expired: boolean
}

export type SchwabMarketDataRefreshStatus = {
  sync_key: string
  data_kind: string
  status: string
  provider_state: string
  observed_at: string | null
  completed_at: string | null
  correlation_id: string
  is_stale: boolean
}

export type SchwabBrokerStatus = {
  configured: boolean
  accounts_trading_configured: boolean
  callback_url: string
  connection_state: SchwabConnectionState
  market_data_state: SchwabMarketDataState
  accounts_trading_state: SchwabAccountsTradingState
  token: SchwabTokenStatus | null
  accounts_trading_token: SchwabTokenStatus | null
  last_market_data_refresh: SchwabMarketDataRefreshStatus | null
  actions: {
    oauth_start: boolean
    refresh: boolean
    revoke: boolean
    accounts_oauth_start: boolean
    accounts_refresh: boolean
    accounts_revoke: boolean
  }
}
