import { afterEach, describe, expect, it, vi } from 'vitest'

import { cut, type TaskStat } from './data'

const row = (done_at: string) => ({ project: 'p', done: true, done_at } as unknown as TaskStat)

afterEach(() => { vi.useRealTimers(); vi.unstubAllEnvs() })

describe('cut', () => {
  it('counts the period in local days, not UTC ones', () => {
    // East of UTC, so a UTC day differs from the local one in the morning.
    vi.stubEnv('TZ', 'Australia/Sydney')
    expect(new Date(2026, 9, 5).getTimezoneOffset()).toBe(-660)
    vi.useFakeTimers()
    // 08:00 local on 5 October: east of UTC it is still 4 October there.
    vi.setSystemTime(new Date(2026, 9, 5, 8, 0))
    const rows = [row('2026-09-04T10:00:00'), row('2026-09-05T10:00:00')]
    expect(cut(rows, { project: '', period: '30' }).map((r) => r.done_at)).toEqual(['2026-09-05T10:00:00'])
  })
})
