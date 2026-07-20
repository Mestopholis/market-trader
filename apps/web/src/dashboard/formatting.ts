export function formatDashboardTime(value: string | null | undefined): string {
  if (!value) return 'Unavailable'
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return 'Unavailable'
  const eastern = formatInZone(date, 'America/New_York')
  const central = formatInZone(date, 'America/Chicago')
  return `${eastern} ET / ${central} CT`
}

export function labelize(value: string): string {
  return value.replaceAll('_', ' ')
}

function formatInZone(date: Date, timeZone: string): string {
  return new Intl.DateTimeFormat('en-US', {
    timeZone,
    month: 'short',
    day: 'numeric',
    hour: 'numeric',
    minute: '2-digit',
  }).format(date)
}
