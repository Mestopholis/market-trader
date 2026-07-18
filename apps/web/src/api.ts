export type HealthResponse = {
  status: 'ok'
  environment: string
  trading_mode: 'paper'
  version: string
  database: 'ok' | 'unavailable'
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
