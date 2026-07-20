export type PaperAction =
  | 'approve'
  | 'modify'
  | 'reject'
  | 'preview'
  | 'submit_paper_order'
  | 'cancel_paper_order'
  | 'replace_paper_order'

export type PaperBrokerScenario =
  | 'accepted_unfilled'
  | 'full_fill'
  | 'partial_fill'
  | 'reject'
  | 'cancel'
  | 'cancel_replace'
  | 'timeout'
  | 'assignment'

export type ApprovalCardState = 'ready' | 'stale' | 'expired' | 'unavailable'

export type PaperOrderStatus =
  | 'pending'
  | 'accepted'
  | 'working'
  | 'partially_filled'
  | 'filled'
  | 'rejected'
  | 'canceled'
  | 'replaced'
  | 'timed_out'
  | 'reconciled'

export type PaperPositionStatus =
  | 'open'
  | 'partially_closed'
  | 'closed'
  | 'expired'
  | 'assigned'

export type PaperOrderType = 'limit'

export type PaperModePayload = {
  paper_mode: true
}

export type PaperApprovalCard = PaperModePayload & {
  card_key: string
  state: ApprovalCardState
  candidate_key: string
  symbol: string
  direction: string
  proposal_kind: string
  quantity: number
  limit_price: string
  maximum_loss: string
  risk_decision_key: string
  risk_status: string
  risk_input_digest: string
  risk_result_digest: string
  source_keys: string[]
  allowed_actions: PaperAction[]
  expires_at: string
  as_of: string
  warnings: string[]
}

export type PaperApprovalCardListResponse = PaperModePayload & {
  approval_cards: PaperApprovalCard[]
}

export type PaperOrderIntent = {
  intent_key: string
  approval_id: string
  proposed_trade_id: string
  risk_decision_key: string
  symbol: string
  side: 'buy' | 'sell'
  order_type: PaperOrderType
  quantity: number
  limit_price: string
  time_in_force: string
  source_keys: string[]
  correlation_id: string
  created_at: string
  payload: Record<string, unknown>
}

export type PaperApproval = PaperModePayload & {
  id: string
  status?: string
  decision_payload?: Record<string, unknown>
  order_intent_payload?: Record<string, unknown> | null
  preview_payload?: Record<string, unknown> | null
}

export type PaperPreview = PaperModePayload & {
  preview_key: string
  approval_id: string
  intent_key: string
  quote_observed_at: string
  quote_expires_at: string
  bid: string
  ask: string
  limit_price: string
  estimated_maximum_loss: string
  reserved_risk: string
  warnings: string[]
  preview_digest: string
  source_keys: string[]
  as_of: string
}

export type PaperOrder = {
  order_id: string
  intent_key: string
  status: PaperOrderStatus
  scenario?: PaperBrokerScenario
  requested_quantity?: number
  filled_quantity?: number
  remaining_quantity?: number
  limit_price?: string
  average_fill_price?: string | null
  simulated_broker_reference?: string
  correlation_id?: string
  source_keys?: string[]
  created_at?: string
  updated_at?: string
  terminal_at?: string | null
  broker_reference?: null
}

export type PaperOrderActionResponse = PaperModePayload & PaperOrder

export type PaperPosition = {
  position_key: string
  symbol: string
  status: PaperPositionStatus
  quantity: number
  average_price: string
  realized_pl: string
  unrealized_pl: string
  source_order_ids: string[]
  source_fill_ids: string[]
  risk_decision_key: string
  opened_at: string
  updated_at: string
  closed_at: string | null
  exit_rules: Record<string, unknown>
  broker_reference: null
}

export type SubmittedPaperOrder = PaperModePayload & {
  order: PaperOrder
  persisted_order_id: string
  position: PaperPosition | null
}

export type PaperOrdersResponse = PaperModePayload & {
  orders: PaperOrder[]
}

export type PaperPositionsResponse = PaperModePayload & {
  positions: PaperPosition[]
}

export type PaperRecoveryResponse = PaperModePayload & {
  open_approvals: PaperApproval[]
  working_orders: PaperOrder[]
  timed_out_orders: PaperOrder[]
  open_orders: PaperOrder[]
  open_positions: PaperPosition[]
}

export type ModifyPaperApprovalCardRequest = {
  quantity: number
  limit_price: string
}

export type SubmitPaperApprovalRequest = {
  preview_digest: string
  scenario?: PaperBrokerScenario
}

export type ReplacePaperOrderRequest = {
  limit_price: string
}
