import { cleanup, render, screen } from '@testing-library/react'
import { afterEach, expect, test, vi } from 'vitest'

import CandidateDetailPanel from './CandidateDetailPanel'
import type { CandidateDetail } from './types'

const detail: CandidateDetail = {
  candidate_key: 'candidate:aapl',
  symbol: 'AAPL',
  data_state: 'partial',
  as_of: '2026-07-20T15:30:00Z',
  scanner: { score: '87.50', policy_version: 'scanner-policy-v1', result_digest: 'scanner-result' },
  catalysts: { decision: 'confirmed', result_digest: 'catalyst-result' },
  options: { state: 'unavailable' },
  risk: { status: 'warning', policy_version: 'risk-policy-v1', result_digest: 'risk-result' },
  sources: [
    {
      name: 'scanner',
      state: 'ready',
      version: 'scanner-policy-v1',
      observed_at: '2026-07-20T15:30:00Z',
      stable_key: 'scanner:run:1',
      digest: null,
    },
  ],
  warnings: [],
}

afterEach(() => {
  cleanup()
  vi.restoreAllMocks()
})

test('renders candidate trace sections with source keys and versions', async () => {
  vi.spyOn(globalThis, 'fetch').mockResolvedValue(new Response(JSON.stringify(detail), { status: 200 }))

  render(<CandidateDetailPanel candidateKey="candidate:aapl" />)

  expect(await screen.findByRole('heading', { name: 'Candidate detail' })).toBeInTheDocument()
  expect(screen.getByText('AAPL')).toBeInTheDocument()
  expect(screen.getByText('scanner-policy-v1')).toBeInTheDocument()
  expect(screen.getByText('catalyst-result')).toBeInTheDocument()
  expect(screen.getByText('risk-result')).toBeInTheDocument()
  expect(screen.getByText('scanner:run:1')).toBeInTheDocument()
  expect(screen.queryByRole('button', { name: /approve|submit|buy|sell/i })).not.toBeInTheDocument()
})

test('renders candidate detail unavailable state', async () => {
  vi.spyOn(globalThis, 'fetch').mockRejectedValue(new Error('offline'))

  render(<CandidateDetailPanel candidateKey="candidate:aapl" />)

  expect(await screen.findByRole('alert')).toHaveTextContent('Candidate detail unavailable')
})
