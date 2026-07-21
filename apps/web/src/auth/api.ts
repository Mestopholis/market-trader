import type { AuthenticatedSession, LoginRequest, SessionState } from './types'

const CSRF_COOKIE_NAME = 'market_trader_csrf'
const CSRF_HEADER_NAME = 'X-CSRF-Token'

export async function fetchSession(signal?: AbortSignal): Promise<SessionState> {
  const response = await fetch('/api/auth/session', {
    headers: { Accept: 'application/json' },
    cache: 'no-store',
    credentials: 'same-origin',
    signal,
  })
  if (response.status === 401) {
    return { authenticated: false }
  }
  if (!response.ok) {
    throw new Error(`Session request failed with ${response.status}`)
  }
  return (await response.json()) as AuthenticatedSession
}

export async function login(
  request: LoginRequest,
  signal?: AbortSignal,
): Promise<AuthenticatedSession> {
  const response = await fetch('/api/auth/login', {
    method: 'POST',
    headers: { Accept: 'application/json', 'Content-Type': 'application/json' },
    body: JSON.stringify(request),
    cache: 'no-store',
    credentials: 'same-origin',
    signal,
  })
  if (!response.ok) {
    throw new Error(`Login request failed with ${response.status}`)
  }
  return (await response.json()) as AuthenticatedSession
}

export async function logout(signal?: AbortSignal): Promise<void> {
  const response = await fetch('/api/auth/logout', {
    method: 'POST',
    headers: { Accept: 'application/json', [CSRF_HEADER_NAME]: csrfToken() },
    cache: 'no-store',
    credentials: 'same-origin',
    signal,
  })
  if (!response.ok && response.status !== 401) {
    throw new Error(`Logout request failed with ${response.status}`)
  }
}

export function csrfToken(): string {
  const cookie = document.cookie
    .split(';')
    .map((part) => part.trim())
    .find((part) => part.startsWith(`${CSRF_COOKIE_NAME}=`))
  return cookie ? decodeURIComponent(cookie.split('=', 2)[1]) : ''
}
