import { afterEach, expect, test, vi } from 'vitest'

import { fetchSession, login, logout } from './api'

afterEach(() => {
  vi.restoreAllMocks()
  document.cookie = 'market_trader_csrf=; Max-Age=0; path=/'
})

function jsonResponse(body: unknown, init: ResponseInit = {}): Response {
  return new Response(JSON.stringify(body), {
    status: 200,
    headers: { 'Content-Type': 'application/json', ...init.headers },
    ...init,
  })
}

test('login posts credentials without exposing them in thrown errors', async () => {
  const fetchMock = vi.spyOn(globalThis, 'fetch').mockResolvedValue(
    jsonResponse({ authenticated: true, username: 'operator' }),
  )

  await expect(login({ username: 'operator', password: 'local-password' })).resolves.toEqual({
    authenticated: true,
    username: 'operator',
  })

  expect(fetchMock).toHaveBeenCalledWith('/api/auth/login', {
    method: 'POST',
    headers: { Accept: 'application/json', 'Content-Type': 'application/json' },
    body: JSON.stringify({ username: 'operator', password: 'local-password' }),
    cache: 'no-store',
    credentials: 'same-origin',
    signal: undefined,
  })
})

test('session returns unauthenticated instead of throwing on 401', async () => {
  vi.spyOn(globalThis, 'fetch').mockResolvedValue(
    jsonResponse({ code: 'unauthenticated', summary: 'Authentication required.' }, { status: 401 }),
  )

  await expect(fetchSession()).resolves.toEqual({ authenticated: false })
})

test('logout sends csrf token from the readable csrf cookie', async () => {
  document.cookie = 'market_trader_csrf=csrf-token; path=/'
  const fetchMock = vi.spyOn(globalThis, 'fetch').mockResolvedValue(new Response(null, { status: 204 }))

  await logout()

  expect(fetchMock).toHaveBeenCalledWith('/api/auth/logout', {
    method: 'POST',
    headers: { Accept: 'application/json', 'X-CSRF-Token': 'csrf-token' },
    cache: 'no-store',
    credentials: 'same-origin',
    signal: undefined,
  })
})
