import type { SchwabBrokerStatus } from './types'

type BrokerStatusPanelProps = {
  correlationId?: string
  status: SchwabBrokerStatus
  onRefresh: () => void
  onRevoke: () => void
  onQuoteRefresh: () => void
  onLiveScan: () => void
  onAccountsRefresh: () => void
  onAccountsRevoke: () => void
}

export default function BrokerStatusPanel({
  correlationId,
  status,
  onRefresh,
  onRevoke,
  onQuoteRefresh,
  onLiveScan,
  onAccountsRefresh,
  onAccountsRevoke,
}: BrokerStatusPanelProps) {
  return (
    <>
      <section className="dashboard-panel" aria-labelledby="schwab-market-data-title">
        <div className="dashboard-panel-heading">
          <div>
            <h2 id="schwab-market-data-title">Schwab Market Data</h2>
            <p className="muted">Read-only provider status</p>
          </div>
          <div className="operations-actions">
            {correlationId ? <span className="state-chip">{correlationId}</span> : null}
            <button
              type="button"
              className="paper-action-button"
              onClick={onQuoteRefresh}
              disabled={status.connection_state !== 'connected'}
            >
              Refresh SPY quote
            </button>
            <button
              type="button"
              className="paper-action-button"
              onClick={onLiveScan}
              disabled={status.connection_state !== 'connected'}
            >
              Run live scanner
            </button>
            <button
              type="button"
              className="paper-action-button"
              onClick={onRefresh}
              disabled={!status.actions.refresh}
            >
              Refresh Schwab token
            </button>
            <button
              type="button"
              className="paper-action-button"
              onClick={onRevoke}
              disabled={!status.actions.revoke}
            >
              Revoke Schwab token
            </button>
          </div>
        </div>

        <dl className="dashboard-facts">
          <dt>Connection</dt>
          <dd><span className={`state-chip state-${stateClass(status.connection_state)}`}>{status.connection_state}</span></dd>
          <dt>Market data</dt>
          <dd><span className={`state-chip state-${stateClass(status.market_data_state)}`}>{status.market_data_state}</span></dd>
          <dt>Callback</dt>
          <dd>{status.callback_url}</dd>
          <dt>Token expiry</dt>
          <dd>{status.token ? centralTime(status.token.access_token_expires_at) : 'Not connected'}</dd>
          <dt>Data kind</dt>
          <dd>{status.last_market_data_refresh?.data_kind ?? 'Not recorded'}</dd>
          <dt>Last refresh</dt>
          <dd>{status.last_market_data_refresh ? refreshSummary(status) : 'No market data refresh recorded'}</dd>
        </dl>

        {status.connection_state === 'disconnected' ? (
          <p className="muted">Use the local OAuth helper on https://127.0.0.1:8182.</p>
        ) : null}
      </section>

      <section className="dashboard-panel" aria-labelledby="schwab-accounts-title">
        <div className="dashboard-panel-heading">
          <div>
            <h2 id="schwab-accounts-title">Schwab Accounts and Trading</h2>
            <p className="muted">Validation-only order-contract dependency</p>
          </div>
          <div className="operations-actions">
            <button
              type="button"
              className="paper-action-button"
              onClick={onAccountsRefresh}
              disabled={!status.actions.accounts_refresh}
            >
              Refresh Accounts token
            </button>
            <button
              type="button"
              className="paper-action-button"
              onClick={onAccountsRevoke}
              disabled={!status.actions.accounts_revoke}
            >
              Revoke Accounts token
            </button>
          </div>
        </div>

        <dl className="dashboard-facts">
          <dt>Configured</dt>
          <dd>{status.accounts_trading_configured ? 'Yes' : 'No'}</dd>
          <dt>Connection</dt>
          <dd>
            <span className={`state-chip state-${stateClass(status.accounts_trading_state)}`}>
              {status.accounts_trading_state}
            </span>
          </dd>
          <dt>Callback</dt>
          <dd>{status.callback_url}</dd>
          <dt>Token expiry</dt>
          <dd>
            {status.accounts_trading_token
              ? centralTime(status.accounts_trading_token.access_token_expires_at)
              : 'Not connected'}
          </dd>
        </dl>

        {status.accounts_trading_state === 'disconnected' || status.accounts_trading_state === 'unconfigured' ? (
          <p className="muted">Use the local OAuth helper on https://127.0.0.1:8182 and choose Accounts and Trading.</p>
        ) : null}
      </section>
    </>
  )
}

function refreshSummary(status: SchwabBrokerStatus): string {
  const refresh = status.last_market_data_refresh
  if (!refresh) return 'No market data refresh recorded'
  const observed = refresh.observed_at ? centralTime(refresh.observed_at) : 'unknown time'
  const stale = refresh.is_stale ? ', stale' : ''
  return `${refresh.data_kind} ${refresh.provider_state} at ${observed}${stale}`
}

function stateClass(state: string): string {
  if (state === 'connected' || state === 'available') return 'ready'
  if (state === 'expired' || state === 'stale' || state === 'rate_limited' || state === 'unknown') {
    return 'stale'
  }
  return 'unavailable'
}

function centralTime(value: string): string {
  const parts = new Intl.DateTimeFormat('en-US', {
    timeZone: 'America/Chicago',
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
    hourCycle: 'h23',
  }).formatToParts(new Date(value))
  const part = (type: string) => parts.find((item) => item.type === type)?.value ?? ''
  return `${part('year')}-${part('month')}-${part('day')} ${part('hour')}:${part('minute')} CT`
}
