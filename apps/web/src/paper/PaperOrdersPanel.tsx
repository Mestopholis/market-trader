import { useEffect, useState } from 'react'

import { cancelPaperOrder, fetchPaperOrders, replacePaperOrder } from '../api'
import { formatDashboardTime, labelize } from '../dashboard/formatting'
import { usePaperActionBlock } from '../dashboard/SystemReadinessHooks'
import type { PaperOrder, PaperOrdersResponse } from './types'

type LoadState =
  | { kind: 'loading' }
  | { kind: 'ready'; orders: PaperOrdersResponse }
  | { kind: 'error' }

export default function PaperOrdersPanel() {
  const [state, setState] = useState<LoadState>({ kind: 'loading' })
  const [replaceLimits, setReplaceLimits] = useState<Record<string, string>>({})
  const [message, setMessage] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)
  const actionBlock = usePaperActionBlock()

  useEffect(() => {
    const controller = new AbortController()
    fetchPaperOrders(controller.signal)
      .then((orders) => setState({ kind: 'ready', orders }))
      .catch(() => {
        if (!controller.signal.aborted) setState({ kind: 'error' })
      })
    return () => controller.abort()
  }, [])

  async function handleCancel(orderId: string) {
    if (actionBlock) return
    setMessage(null)
    setError(null)
    try {
      const order = await cancelPaperOrder(orderId)
      setMessage(`Paper order canceled: ${order.order_id}`)
    } catch (caught) {
      setError(messageFrom(caught))
    }
  }

  async function handleReplace(order: PaperOrder) {
    if (actionBlock) return
    setMessage(null)
    setError(null)
    try {
      const replaced = await replacePaperOrder(order.order_id, {
        limit_price: replaceLimits[order.order_id] ?? order.limit_price ?? '',
      })
      setMessage(`Paper order replaced: ${replaced.order_id}`)
    } catch (caught) {
      setError(messageFrom(caught))
    }
  }

  if (state.kind === 'loading') {
    return <section className="dashboard-panel"><p>Loading paper orders...</p></section>
  }

  if (state.kind === 'error') {
    return (
      <section role="alert" className="dashboard-panel dashboard-panel-unavailable">
        <h2>Paper orders unavailable</h2>
        <p>Paper order state could not be loaded.</p>
      </section>
    )
  }

  return (
    <section className="dashboard-panel" aria-labelledby="paper-orders-title">
      <div className="dashboard-panel-heading">
        <h2 id="paper-orders-title">Paper orders</h2>
        <span className="state-chip">{state.orders.orders.length} open</span>
      </div>
      {actionBlock && <p className="paper-action-error">Paper actions blocked: {actionBlock.code}</p>}
      {message && <p>{message}</p>}
      {error && <p role="alert" className="paper-action-error">{error}</p>}

      {state.orders.orders.length === 0 ? (
        <p className="muted">No paper orders are open.</p>
      ) : (
        <div className="dashboard-table-wrap">
          <table className="dashboard-table">
            <thead>
              <tr>
                <th>Order</th>
                <th>Status</th>
                <th>Fill</th>
                <th>Limit</th>
                <th>Updated</th>
                <th>Paper controls</th>
              </tr>
            </thead>
            <tbody>
              {state.orders.orders.map((order) => (
                <tr key={order.order_id}>
                  <td>{order.order_id}</td>
                  <td><span className={`state-chip state-${order.status}`}>{labelize(order.status)}</span></td>
                  <td>{order.filled_quantity ?? 0} / {order.requested_quantity ?? 0} filled</td>
                  <td>{formatCurrency(order.limit_price)}</td>
                  <td>{formatDashboardTime(order.updated_at)}</td>
                  <td>
                    <div className="paper-order-controls">
                      <button
                        type="button"
                        className="paper-action-button"
                        disabled={actionBlock !== null}
                        onClick={() => handleCancel(order.order_id)}
                      >
                        Cancel paper order {order.order_id}
                      </button>
                      <label className="filter-label">
                        Replacement limit for {order.order_id}
                        <input
                          aria-label={`Replacement limit for ${order.order_id}`}
                          value={replaceLimits[order.order_id] ?? order.limit_price ?? ''}
                          onChange={(event) => setReplaceLimits({
                            ...replaceLimits,
                            [order.order_id]: event.target.value,
                          })}
                        />
                      </label>
                      <button
                        type="button"
                        className="paper-action-button"
                        disabled={actionBlock !== null}
                        onClick={() => handleReplace(order)}
                      >
                        Replace paper order {order.order_id}
                      </button>
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </section>
  )
}

function formatCurrency(value: string | null | undefined): string {
  if (!value) return 'Unavailable'
  const numeric = Number(value)
  if (Number.isNaN(numeric)) return value
  return new Intl.NumberFormat('en-US', {
    style: 'currency',
    currency: 'USD',
  }).format(numeric)
}

function messageFrom(caught: unknown): string {
  return caught instanceof Error ? caught.message : 'Paper request failed'
}
