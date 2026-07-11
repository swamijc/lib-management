import { describe, expect, it } from 'vitest'

import { pickLatestLifecycleByLibrary, type LifecycleRow } from '../src/utils/lifecycleSelection'

describe('pickLatestLifecycleByLibrary', () => {
  it('picks newest row by updated_at when timestamps are valid', () => {
    const rows: LifecycleRow[] = [
      {
        library_id: 101,
        status: 'Completed',
        target_version: '1.0.0',
        updated_at: '2026-07-01T08:00:00Z',
      },
      {
        library_id: 101,
        status: 'In Progress',
        target_version: '1.1.0',
        updated_at: '2026-07-01T09:00:00Z',
      },
    ]

    const result = pickLatestLifecycleByLibrary(rows)
    expect(result['101']?.status).toBe('In Progress')
    expect(result['101']?.target_version).toBe('1.1.0')
  })

  it('prefers row with valid timestamp over invalid/missing timestamp', () => {
    const rows: LifecycleRow[] = [
      {
        library_id: 202,
        status: 'In Progress',
        target_version: '2.1.0',
        updated_at: 'not-a-date',
      },
      {
        library_id: 202,
        status: 'Acknowledged',
        target_version: '2.0.0',
        updated_at: '2026-07-01T10:00:00Z',
      },
    ]

    const result = pickLatestLifecycleByLibrary(rows)
    expect(result['202']?.status).toBe('Acknowledged')
    expect(result['202']?.target_version).toBe('2.0.0')
  })

  it('uses status precedence fallback when timestamps are missing/invalid', () => {
    const rows: LifecycleRow[] = [
      {
        library_id: 303,
        status: 'Completed',
        target_version: '3.0.0',
        updated_at: null,
      },
      {
        library_id: 303,
        status: 'In Progress',
        target_version: '3.1.0',
        updated_at: undefined,
      },
    ]

    const result = pickLatestLifecycleByLibrary(rows)
    expect(result['303']?.status).toBe('In Progress')
    expect(result['303']?.target_version).toBe('3.1.0')
  })

  it('uses higher lifecycle id as tie-breaker when timestamps are equal', () => {
    const rows: LifecycleRow[] = [
      {
        id: 40,
        library_id: 404,
        status: 'In Progress',
        target_version: '4.0.0',
        updated_at: '2026-07-01T12:00:00Z',
      },
      {
        id: 41,
        library_id: 404,
        status: 'Completed',
        target_version: '4.1.0',
        updated_at: '2026-07-01T12:00:00Z',
      },
    ]

    const result = pickLatestLifecycleByLibrary(rows)
    expect(result['404']?.status).toBe('Completed')
    expect(result['404']?.target_version).toBe('4.1.0')
  })
})
