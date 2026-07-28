import { csrfToken } from '../auth/api'
import type { ApiResult } from '../api'
import type { SchwabBrokerStatus, SchwabTokenStatus } from './types'

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

async function schwabPost<T>(url: string, label: string, signal?: AbortSignal): Promise<T> {
  const response = await fetch(url, {
    method: 'POST',
    headers: { Accept: 'application/json', 'X-CSRF-Token': csrfToken() },
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
