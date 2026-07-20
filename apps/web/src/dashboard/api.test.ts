import { afterEach, expect, test, vi } from 'vitest'

import {
  fetchDashboardAnalytics,
  fetchDashboardCandidateDetail,
  fetchDashboardCandidates,
  fetchDashboardJournal,
  fetchDashboardOverview,
  fetchDashboardRisk,
} from '../api'
import type { DashboardOverview } from './types'

const overview: DashboardOverview = {
  as_of: '2026-07-20T15:30:00Z',
  data_state: 'partial',
  paper_mode: true,
  market_state: 'entry_open',
  entry_allowed: true,
  sources: [
    {
      name: 'risk',
      state: 'ready',
      version: 'risk-policy-v1',
      observed_at: '2026-07-20T15:30:00Z',
      stable_key: 'risk:latest',
      digest: null,
    },
  ],
  warnings: [],
}

afterEach(() => {
  vi.restoreAllMocks()
})

function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), { status })
}

test('fetches dashboard overview with no-store cache headers', async () => {
  const fetchMock = vi.spyOn(globalThis, 'fetch').mockResolvedValue(jsonResponse(overview))

  await expect(fetchDashboardOverview()).resolves.toEqual(overview)

  expect(fetchMock).toHaveBeenCalledWith('/api/dashboard/overview', {
    headers: { Accept: 'application/json' },
    cache: 'no-store',
    signal: undefined,
  })
})

test('encodes candidate pagination parameters', async () => {
  const fetchMock = vi.spyOn(globalThis, 'fetch').mockResolvedValue(
    jsonResponse({
      as_of: overview.as_of,
      data_state: 'ready',
      candidates: [],
      next_cursor: null,
      sources: [],
      warnings: [],
    }),
  )

  await fetchDashboardCandidates({ limit: 25, cursor: 'cursor:next' })

  expect(fetchMock).toHaveBeenCalledWith(
    '/api/dashboard/candidates?limit=25&cursor=cursor%3Anext',
    {
      headers: { Accept: 'application/json' },
      cache: 'no-store',
      signal: undefined,
    },
  )
})

test('encodes journal filters and pagination parameters', async () => {
  const fetchMock = vi.spyOn(globalThis, 'fetch').mockResolvedValue(
    jsonResponse({
      as_of: overview.as_of,
      data_state: 'ready',
      events: [],
      next_cursor: null,
      sources: [],
      warnings: [],
    }),
  )

  await fetchDashboardJournal({
    limit: 10,
    cursor: 'journal:next',
    eventType: 'risk_decision.recorded',
    correlationId: 'corr:1',
  })

  expect(fetchMock).toHaveBeenCalledWith(
    '/api/dashboard/journal?limit=10&cursor=journal%3Anext&event_type=risk_decision.recorded&correlation_id=corr%3A1',
    {
      headers: { Accept: 'application/json' },
      cache: 'no-store',
      signal: undefined,
    },
  )
})

test('fetches candidate detail, risk, and analytics endpoints', async () => {
  const fetchMock = vi
    .spyOn(globalThis, 'fetch')
    .mockImplementation(async () => jsonResponse({ ok: true }))

  await fetchDashboardCandidateDetail('candidate:aapl:2026-07-20')
  await fetchDashboardRisk()
  await fetchDashboardAnalytics()

  expect(fetchMock.mock.calls.map((call) => call[0])).toEqual([
    '/api/dashboard/candidates/candidate%3Aaapl%3A2026-07-20',
    '/api/dashboard/risk',
    '/api/dashboard/analytics',
  ])
})

test('throws clear errors for dashboard request failures', async () => {
  vi.spyOn(globalThis, 'fetch').mockResolvedValue(jsonResponse({ detail: 'nope' }, 503))

  await expect(fetchDashboardOverview()).rejects.toThrow(
    'Dashboard overview request failed with 503',
  )
})
