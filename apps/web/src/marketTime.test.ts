import { describe, expect, test } from 'vitest'

import type { MarketStateResponse } from './api'
import { formatMarketTime, isSnapshotFresh } from './marketTime'

describe('formatMarketTime', () => {
  test('formats summer values in both ET and CT', () => {
    const value = '2026-07-20T13:30:00Z'

    expect(formatMarketTime(value, 'America/New_York', 'ET')).toContain('9:30 AM ET')
    expect(formatMarketTime(value, 'America/Chicago', 'CT')).toContain('8:30 AM CT')
  })

  test('formats winter offsets from IANA zones', () => {
    const value = '2026-11-27T14:30:00Z'

    expect(formatMarketTime(value, 'America/New_York', 'ET')).toContain('9:30 AM ET')
    expect(formatMarketTime(value, 'America/Chicago', 'CT')).toContain('8:30 AM CT')
  })
})

test('snapshot freshness includes the validity boundary', () => {
  const snapshot = {
    observed_at: '2026-07-20T15:30:00Z',
    valid_until: '2026-07-20T15:31:00Z',
  } as MarketStateResponse

  expect(isSnapshotFresh(snapshot, new Date('2026-07-20T15:31:00Z'))).toBe(true)
  expect(isSnapshotFresh(snapshot, new Date('2026-07-20T15:31:00.001Z'))).toBe(false)
})
