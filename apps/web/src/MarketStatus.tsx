import { useEffect, useState } from 'react'

import { fetchMarketState, type MarketState, type MarketStateResponse } from './api'
import { formatMarketTime, isSnapshotFresh } from './marketTime'

type MarketLoadState =
  | { kind: 'loading' }
  | { kind: 'ready'; snapshot: MarketStateResponse }
  | { kind: 'unavailable' }

const stateLabels: Record<MarketState, string> = {
  closed: 'Market closed',
  pre_market: 'Pre-market',
  opening_buffer: 'Opening buffer',
  entry_open: 'Entry window open',
  entry_closed: 'Entry window closed',
  post_market: 'Post-market',
}

export default function MarketStatus() {
  const [state, setState] = useState<MarketLoadState>({ kind: 'loading' })

  useEffect(() => {
    let mounted = true
    let activeController: AbortController | undefined
    let expiryTimer: ReturnType<typeof setTimeout> | undefined

    const clearExpiry = () => {
      if (expiryTimer !== undefined) clearTimeout(expiryTimer)
      expiryTimer = undefined
    }

    const scheduleExpiry = (snapshot: MarketStateResponse) => {
      clearExpiry()
      const delay = Math.max(0, new Date(snapshot.valid_until).getTime() - Date.now())
      const boundedDelay = Math.min(delay, 2_147_483_646)
      expiryTimer = setTimeout(() => {
        if (!mounted) return
        setState((current) => {
          if (
            current.kind === 'ready' &&
            current.snapshot.observed_at === snapshot.observed_at &&
            !isSnapshotFresh(current.snapshot, new Date())
          ) {
            return { kind: 'unavailable' }
          }
          return current
        })
      }, boundedDelay + 1)
    }

    const load = async () => {
      activeController?.abort()
      const controller = new AbortController()
      activeController = controller
      try {
        const snapshot = await fetchMarketState(controller.signal)
        if (!mounted || controller.signal.aborted) return
        if (!isSnapshotFresh(snapshot, new Date())) {
          clearExpiry()
          setState({ kind: 'unavailable' })
          return
        }
        setState({ kind: 'ready', snapshot })
        scheduleExpiry(snapshot)
      } catch {
        if (!mounted || controller.signal.aborted) return
        setState((current) => {
          if (current.kind === 'ready' && isSnapshotFresh(current.snapshot, new Date())) {
            return current
          }
          return { kind: 'unavailable' }
        })
      }
    }

    void load()
    const pollTimer = setInterval(() => void load(), 30_000)
    return () => {
      mounted = false
      activeController?.abort()
      clearInterval(pollTimer)
      clearExpiry()
    }
  }, [])

  if (state.kind === 'loading') {
    return (
      <section className="market-status market-status-loading" aria-labelledby="market-status-title">
        <h2 id="market-status-title">Market status</h2>
        <p>Checking market schedule...</p>
      </section>
    )
  }

  if (state.kind === 'unavailable') {
    return (
      <section className="market-status market-status-unavailable" aria-labelledby="market-status-title">
        <h2 id="market-status-title">Market status</h2>
        <strong>Market schedule unavailable</strong>
        <p>Entry eligibility cannot be verified.</p>
      </section>
    )
  }

  const { snapshot } = state
  return (
    <section className={`market-status market-status-${snapshot.market_state}`} aria-labelledby="market-status-title">
      <div className="market-status-heading">
        <h2 id="market-status-title">Market status</h2>
        {snapshot.is_early_close && <span className="status-flag">Early close</span>}
      </div>
      <p className="market-state-label">{stateLabels[snapshot.market_state]}</p>
      <dl className="market-status-details">
        <dt>Current time</dt>
        <dd>{dualTime(snapshot.observed_at, snapshot)}</dd>
        {snapshot.market_open && snapshot.market_close ? (
          <>
            <dt>Session</dt>
            <dd>{dualRange(snapshot.market_open, snapshot.market_close, snapshot)}</dd>
          </>
        ) : (
          <>
            <dt>Next session</dt>
            <dd>{dualTime(snapshot.next_session_open, snapshot)}</dd>
          </>
        )}
        {snapshot.entry_window_open && snapshot.entry_window_close && (
          <>
            <dt>Entry window</dt>
            <dd>{dualRange(snapshot.entry_window_open, snapshot.entry_window_close, snapshot)}</dd>
          </>
        )}
        <dt>Next transition</dt>
        <dd>{dualTime(snapshot.next_transition, snapshot)}</dd>
      </dl>
    </section>
  )
}

function dualTime(value: string, snapshot: MarketStateResponse): string {
  return `${formatMarketTime(value, snapshot.calendar_timezone, 'ET')} / ${formatMarketTime(
    value,
    snapshot.display_timezone,
    'CT',
  )}`
}

function dualRange(start: string, end: string, snapshot: MarketStateResponse): string {
  return `${dualTime(start, snapshot)} - ${dualTime(end, snapshot)}`
}
