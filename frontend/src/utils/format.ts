export function formatPercent(value: number): string {
  return `${value}%`
}

export function formatTimeAgo(isoDate: string): string {
  const created = new Date(isoDate).getTime()
  const now = Date.now()
  const diffMs = Math.max(0, now - created)

  const minutes = Math.floor(diffMs / 60000)
  if (minutes < 1) {
    return "just now"
  }

  if (minutes < 60) {
    return `${minutes}m ago`
  }

  const hours = Math.floor(minutes / 60)
  if (hours < 24) {
    return `${hours}h ago`
  }

  const days = Math.floor(hours / 24)
  return `${days}d ago`
}
