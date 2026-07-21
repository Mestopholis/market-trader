import { cleanup, render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, expect, test, vi } from 'vitest'

import App from '../App'

afterEach(() => {
  cleanup()
  vi.restoreAllMocks()
})

const health = {
  status: 'ok',
  environment: 'local',
  trading_mode: 'paper',
  version: '0.1.0',
  database: 'ok',
}

const overview = {
  as_of: '2026-07-20T15:30:00Z',
  data_state: 'ready',
  paper_mode: true,
  market_state: 'entry_open',
  entry_allowed: true,
  sources: [],
  warnings: [],
}

function response(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), { status, headers: { 'Content-Type': 'application/json' } })
}

test('routes unauthenticated operators to local login', async () => {
  vi.spyOn(globalThis, 'fetch').mockImplementation(async (input) => {
    const url = String(input)
    if (url.includes('/api/health')) return response(health)
    if (url.includes('/api/auth/session')) return response({ code: 'unauthenticated' }, 401)
    return response(overview)
  })

  render(<App />)

  expect(await screen.findByRole('heading', { name: 'Local operator login' })).toBeInTheDocument()
  expect(screen.queryByText('PAPER MODE')).not.toBeInTheDocument()
})

test('logs in and shows the dashboard without echoing rejected secrets', async () => {
  const user = userEvent.setup()
  const fetchMock = vi.spyOn(globalThis, 'fetch').mockImplementation(async (input) => {
    const url = String(input)
    if (url.includes('/api/health')) return response(health)
    if (url.includes('/api/auth/session')) return response({ code: 'unauthenticated' }, 401)
    if (url.includes('/api/auth/login')) return response({ authenticated: true, username: 'operator' })
    return response(overview)
  })

  render(<App />)

  await user.type(await screen.findByLabelText('Username'), 'operator')
  await user.type(screen.getByLabelText('Password'), 'local-password')
  await user.click(screen.getByRole('button', { name: 'Sign in' }))

  expect(await screen.findByText('PAPER MODE')).toBeInTheDocument()
  expect(await screen.findByRole('heading', { name: 'Market overview' })).toBeInTheDocument()
  expect(document.body.textContent).not.toContain('local-password')
  expect(fetchMock.mock.calls.some((call) => String(call[0]).includes('/api/auth/login'))).toBe(true)
})

test('returns to login when the operator signs out', async () => {
  const user = userEvent.setup()
  vi.spyOn(globalThis, 'fetch').mockImplementation(async (input) => {
    const url = String(input)
    if (url.includes('/api/health')) return response(health)
    if (url.includes('/api/auth/session')) return response({ authenticated: true, username: 'operator' })
    if (url.includes('/api/auth/logout')) return new Response(null, { status: 204 })
    return response(overview)
  })

  render(<App />)

  expect(await screen.findByText('PAPER MODE')).toBeInTheDocument()
  await user.click(screen.getByRole('button', { name: 'Sign out' }))

  expect(await screen.findByRole('heading', { name: 'Local operator login' })).toBeInTheDocument()
  expect(screen.getByRole('alert')).toHaveTextContent('Session expired. Sign in again.')
})
