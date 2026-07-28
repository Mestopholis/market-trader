import { csrfToken } from '../auth/api'
import type { ApiResult } from '../api'
import type {
  SchwabBrokerStatus,
  SchwabLiveScanResponse,
  SchwabQuoteRefreshResponse,
  SchwabTokenStatus,
} from './types'

export async function fetchSchwabBrokerStatusWithMeta(
  signal?: AbortSignal,
): Promise<ApiResult<SchwabBrokerStatus>> {
  const response = await fetch('/api/broker/schwab/status', {
    headers: { Accept: 'application/json' },
    cache: 'no-store',
    credentials: 'same-origin',
    signal,
  })
  if (!response.ok) {
    throw new Error(`Schwab status request failed with ${response.status}`)
  }
  return { data: (await response.json()) as SchwabBrokerStatus, correlationId: correlationId(response) }
}

export async function refreshSchwabToken(signal?: AbortSignal): Promise<SchwabTokenStatus> {
  return schwabPost('/api/broker/schwab/oauth/refresh', 'Schwab token refresh', signal)
}

export async function revokeSchwabToken(signal?: AbortSignal): Promise<SchwabTokenStatus> {
  return schwabPost('/api/broker/schwab/oauth/revoke', 'Schwab token revoke', signal)
}

export async function refreshSchwabAccountsToken(signal?: AbortSignal): Promise<SchwabTokenStatus> {
  return schwabPost('/api/broker/schwab/accounts/oauth/refresh', 'Schwab accounts token refresh', signal)
}

export async function revokeSchwabAccountsToken(signal?: AbortSignal): Promise<SchwabTokenStatus> {
  return schwabPost('/api/broker/schwab/accounts/oauth/revoke', 'Schwab accounts token revoke', signal)
}

export async function refreshSchwabQuotes(
  symbols: string[],
  signal?: AbortSignal,
): Promise<SchwabQuoteRefreshResponse> {
  return schwabPost(
    '/api/broker/schwab/market-data/quotes/refresh',
    'Schwab quote refresh',
    signal,
    { symbols },
  )
}

export async function runSchwabLiveScan(signal?: AbortSignal): Promise<SchwabLiveScanResponse> {
  return schwabPost(
    '/api/broker/schwab/market-data/scan-live',
    'Schwab live scanner',
    signal,
    { source: 'schwab', observed_lookback_minutes: 15, refresh_quotes: true },
  )
}

async function schwabPost<T>(
  url: string,
  label: string,
  signal?: AbortSignal,
  body?: unknown,
): Promise<T> {
  const response = await fetch(url, {
    method: 'POST',
    headers: {
      Accept: 'application/json',
      'X-CSRF-Token': csrfToken(),
      ...(body === undefined ? {} : { 'Content-Type': 'application/json' }),
    },
    body: body === undefined ? undefined : JSON.stringify(body),
    cache: 'no-store',
    credentials: 'same-origin',
    signal,
  })
  if (!response.ok) {
    throw new Error(`${label} request failed with ${response.status}`)
  }
  return (await response.json()) as T
}

function correlationId(response: Response): string | undefined {
  return response.headers.get('X-Correlation-ID') ?? undefined
}
