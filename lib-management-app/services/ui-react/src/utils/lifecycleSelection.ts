export type LifecycleRow = {
  id?: number | null
  library_id: number
  status: string
  target_version?: string | null
  updated_at?: string | null
}

const STATUS_PRECEDENCE: Record<string, number> = {
  'In Progress': 6,
  Acknowledged: 5,
  awaiting_review: 4,
  Pending: 4,
  Scheduled: 3,
  Completed: 2,
  Skipped: 1,
}

function toEpoch(value?: string | null): number | null {
  if (!value) return null
  const parsed = new Date(value).getTime()
  return Number.isFinite(parsed) ? parsed : null
}

export function pickLatestLifecycleByLibrary(rows: LifecycleRow[]): Record<string, LifecycleRow> {
  const latestByLibrary = new Map<string, LifecycleRow>()

  for (const row of rows) {
    const key = String(row.library_id)
    const existing = latestByLibrary.get(key)

    if (!existing) {
      latestByLibrary.set(key, row)
      continue
    }

    const rowRank     = STATUS_PRECEDENCE[row.status]      ?? 0
    const existingRank = STATUS_PRECEDENCE[existing.status] ?? 0

    // Higher-precedence status always wins (In Progress > Acknowledged > awaiting_review etc.)
    if (rowRank > existingRank) {
      latestByLibrary.set(key, row)
      continue
    }
    if (rowRank < existingRank) {
      continue
    }

    // Same precedence — fall back to most recent updated_at, then highest id
    const rowTs      = toEpoch(row.updated_at)
    const existingTs = toEpoch(existing.updated_at)
    const rowId      = typeof row.id === 'number' ? row.id : null
    const existingId = typeof existing.id === 'number' ? existing.id : null

    if (rowTs !== null && existingTs !== null) {
      if (rowTs > existingTs) latestByLibrary.set(key, row)
      else if (rowTs === existingTs && rowId !== null && existingId !== null && rowId > existingId)
        latestByLibrary.set(key, row)
      continue
    }
    if (rowTs !== null) { latestByLibrary.set(key, row); continue }
    if (existingTs !== null) continue
    if (rowId !== null && existingId !== null && rowId > existingId) latestByLibrary.set(key, row)
  }

  return Object.fromEntries(latestByLibrary.entries())
}
