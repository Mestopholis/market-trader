import { render, screen } from '@testing-library/react'
import { afterEach, expect, test, vi } from 'vitest'

import App from './App'

afterEach(() => {
  vi.restoreAllMocks()
})

test('shows an unmistakable paper mode banner', async () => {
  vi.spyOn(globalThis, 'fetch').mockResolvedValue(
    new Response(
      JSON.stringify({
        status: 'ok',
        environment: 'local',
        trading_mode: 'paper',
        version: '0.1.0',
      }),
      { status: 200 },
    ),
  )

  render(<App />)

  expect(await screen.findByRole('status')).toHaveTextContent('PAPER MODE')
  expect(screen.getByText(/No live orders can be submitted/i)).toBeInTheDocument()
})

test('shows a safe unavailable state when health fails', async () => {
  vi.spyOn(globalThis, 'fetch').mockRejectedValue(new Error('offline'))

  render(<App />)

  expect(await screen.findByRole('alert')).toHaveTextContent('Trading controls unavailable')
})
