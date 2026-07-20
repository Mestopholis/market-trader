import { cleanup, render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, expect, test, vi } from 'vitest'

import DashboardErrorBoundary from './DashboardErrorBoundary'
import DashboardShell from './DashboardShell'

afterEach(() => {
  cleanup()
})

function ThrowingPanel(): React.JSX.Element {
  throw new Error('panel failed')
}

test('keeps paper banner and dashboard navigation visible', () => {
  render(<DashboardShell />)

  expect(screen.getByRole('status')).toHaveTextContent('PAPER MODE')
  expect(screen.getByRole('navigation', { name: 'Dashboard views' })).toBeInTheDocument()
  expect(screen.getByRole('tab', { name: 'Overview' })).toHaveAttribute('aria-selected', 'true')
  expect(screen.getByRole('tabpanel', { name: 'Overview' })).toBeInTheDocument()
})

test('switches dashboard panels with accessible tabs', async () => {
  const user = userEvent.setup()
  render(<DashboardShell />)

  await user.click(screen.getByRole('tab', { name: 'Risk' }))

  expect(screen.getByRole('tab', { name: 'Risk' })).toHaveAttribute('aria-selected', 'true')
  expect(screen.getByRole('tabpanel', { name: 'Risk' })).toHaveTextContent('Risk')
})

test('includes paper approvals as a dashboard tab', async () => {
  const user = userEvent.setup()
  render(
    <DashboardShell
      panels={{
        paperApprovals: <section>Paper approval queue test panel</section>,
      }}
    />,
  )

  await user.click(screen.getByRole('tab', { name: 'Paper Approvals' }))

  expect(screen.getByRole('tab', { name: 'Paper Approvals' }))
    .toHaveAttribute('aria-selected', 'true')
  expect(screen.getByRole('tabpanel', { name: 'Paper Approvals' }))
    .toHaveTextContent('Paper approval queue test panel')
})

test('includes paper order, position, and recovery tabs', async () => {
  const user = userEvent.setup()
  render(
    <DashboardShell
      panels={{
        paperOrders: <section>Paper order table test panel</section>,
        paperPositions: <section>Paper position table test panel</section>,
        paperRecovery: <section>Paper recovery test panel</section>,
      }}
    />,
  )

  await user.click(screen.getByRole('tab', { name: 'Paper Orders' }))
  expect(screen.getByRole('tabpanel', { name: 'Paper Orders' }))
    .toHaveTextContent('Paper order table test panel')

  await user.click(screen.getByRole('tab', { name: 'Paper Positions' }))
  expect(screen.getByRole('tabpanel', { name: 'Paper Positions' }))
    .toHaveTextContent('Paper position table test panel')

  await user.click(screen.getByRole('tab', { name: 'Paper Recovery' }))
  expect(screen.getByRole('tabpanel', { name: 'Paper Recovery' }))
    .toHaveTextContent('Paper recovery test panel')
})

test('panel errors render an unavailable state without hiding the shell', () => {
  vi.spyOn(console, 'error').mockImplementation(() => undefined)

  render(
    <DashboardShell
      panels={{
        overview: (
          <DashboardErrorBoundary panelName="Overview">
            <ThrowingPanel />
          </DashboardErrorBoundary>
        ),
      }}
    />,
  )

  expect(screen.getByRole('status')).toHaveTextContent('PAPER MODE')
  expect(screen.getByRole('alert')).toHaveTextContent('Overview unavailable')
  expect(screen.getByRole('navigation', { name: 'Dashboard views' })).toBeInTheDocument()
})

test('does not render executable trading controls', () => {
  render(<DashboardShell />)

  const forbidden = /approve|preview|submit|buy|sell|execute|connect broker|arm live|clear lock/i
  expect(screen.queryByRole('button', { name: forbidden })).not.toBeInTheDocument()
  expect(screen.queryByRole('link', { name: forbidden })).not.toBeInTheDocument()
})
