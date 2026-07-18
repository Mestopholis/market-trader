import type { MarketStateResponse } from './api'

export function formatMarketTime(value: string, timeZone: string, label: 'ET' | 'CT'): string {
  const formatted = new Intl.DateTimeFormat('en-US', {
    timeZone,
    month: 'short',
    day: 'numeric',
    hour: 'numeric',
    minute: '2-digit',
  }).format(new Date(value))
  return `${formatted} ${label}`
}

export function isSnapshotFresh(
  snapshot: Pick<MarketStateResponse, 'valid_until'>,
  now: Date,
): boolean {
  const validUntil = new Date(snapshot.valid_until).getTime()
  const reference = now.getTime()
  return reference <= validUntil
}
