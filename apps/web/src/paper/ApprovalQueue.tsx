import { useEffect, useMemo, useState } from 'react'

import { fetchPaperApprovalCards } from '../api'
import { formatDashboardTime, labelize } from '../dashboard/formatting'
import ApprovalCardDetail from './ApprovalCardDetail'
import PaperActionPanel from './PaperActionPanel'
import type { PaperApprovalCard, PaperApprovalCardListResponse } from './types'

type LoadState =
  | { kind: 'loading' }
  | { kind: 'ready'; cards: PaperApprovalCardListResponse }
  | { kind: 'error' }

export default function ApprovalQueue() {
  const [state, setState] = useState<LoadState>({ kind: 'loading' })
  const [selectedKey, setSelectedKey] = useState<string | null>(null)

  useEffect(() => {
    const controller = new AbortController()
    fetchPaperApprovalCards(controller.signal)
      .then((cards) => setState({ kind: 'ready', cards }))
      .catch(() => {
        if (!controller.signal.aborted) setState({ kind: 'error' })
      })
    return () => controller.abort()
  }, [])

  const selectedCard = useMemo(() => {
    if (state.kind !== 'ready') return null
    return (
      state.cards.approval_cards.find((card) => card.card_key === selectedKey)
      ?? state.cards.approval_cards[0]
      ?? null
    )
  }, [selectedKey, state])

  if (state.kind === 'loading') {
    return <section className="dashboard-panel"><p>Loading paper approvals...</p></section>
  }

  if (state.kind === 'error') {
    return (
      <section role="alert" className="dashboard-panel dashboard-panel-unavailable">
        <h2>Paper approvals unavailable</h2>
        <p>Approval cards could not be loaded.</p>
      </section>
    )
  }

  return (
    <section className="dashboard-panel paper-approvals" aria-labelledby="paper-queue-title">
      <div className="dashboard-panel-heading">
        <div>
          <h2 id="paper-queue-title">Paper approvals</h2>
          <p className="muted">Paper-only approval cards from current risk decisions.</p>
        </div>
        <span className="state-chip">{state.cards.approval_cards.length} available</span>
      </div>

      {state.cards.approval_cards.length === 0 ? (
        <p className="muted">No paper approval cards are available.</p>
      ) : (
        <div className="paper-approval-layout">
          <ApprovalCardList
            cards={state.cards.approval_cards}
            selectedKey={selectedCard?.card_key ?? null}
            onSelect={setSelectedKey}
          />
          {selectedCard && (
            <div className="paper-selected-stack">
              <ApprovalCardDetail card={selectedCard} />
              <PaperActionPanel card={selectedCard} />
            </div>
          )}
        </div>
      )}
    </section>
  )
}

type ApprovalCardListProps = {
  cards: PaperApprovalCard[]
  selectedKey: string | null
  onSelect: (cardKey: string) => void
}

function ApprovalCardList({ cards, selectedKey, onSelect }: ApprovalCardListProps) {
  return (
    <div className="paper-card-list" aria-label="Paper approval cards">
      {cards.map((card) => (
        <button
          key={card.card_key}
          type="button"
          className="paper-card-row"
          aria-pressed={selectedKey === card.card_key}
          onClick={() => onSelect(card.card_key)}
        >
          <span className="paper-card-row-main">
            <strong>{card.symbol}</strong>
            <span>{card.direction} {labelize(card.proposal_kind)}</span>
          </span>
          <span className={`state-chip state-${card.state}`}>{card.state}</span>
          <span className="muted">Expires {formatDashboardTime(card.expires_at)}</span>
        </button>
      ))}
    </div>
  )
}
