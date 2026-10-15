import { describe, expect, it } from 'vitest'

import { blockKey, blockTimes, build, dayTotals, daysBack } from './model'
import type { TimeEntry } from '../project/timeEntry'

const now = new Date(2026, 9, 3, 18, 0, 0).getTime()
const e = (over: Partial<TimeEntry>): TimeEntry => ({ id: 'tm_1', project: 'alpha', ...over })

describe('the Timer page model', () => {
  it('counts a project today, in the last 7 days and in the period, by share', () => {
    const entries = [
      e({ id: 'a', started_at: '2026-10-03T10:00:00', ended_at: '2026-10-03T11:00:00' }),
      e({ id: 'b', started_at: '2026-09-30T10:00:00', ended_at: '2026-09-30T12:00:00', share_pct: 50 }),
      e({ id: 'c', started_at: '2026-09-10T10:00:00', ended_at: '2026-09-10T10:30:00' }),
      e({ id: 'd', started_at: '2026-06-01T10:00:00', ended_at: '2026-06-01T15:00:00' }),
    ]
    const m = build(entries, ['alpha', 'beta'], now, '30')
    const alpha = m.projects.find((p) => p.code === 'alpha')!
    expect([alpha.todaySec, alpha.weekSec, alpha.periodSec]).toEqual([3600, 7200, 9000])
    expect(m.projects.find((p) => p.code === 'beta')!.periodSec).toBe(0)
    expect(m.days).toHaveLength(30)
    expect(m.days[29]).toBe('2026-10-03')
    expect(m.perDay['2026-09-30'].alpha).toBe(3600)
    // The 26-week grid counts every day, the period or not.
    expect(dayTotals(entries, now)['2026-06-01']).toBe(18000)
  })

  it('tells a timer you started from the smart timer, and puts running projects first', () => {
    const m = build([
      e({ id: 'a', project: 'beta', started_at: '2026-10-03T17:00:00' }),
      e({ id: 'b', project: 'gamma', started_at: '2026-10-03T17:30:00', source: 'auto' }),
      e({ id: 'c', project: 'alpha', started_at: '2026-10-03T09:00:00', ended_at: '2026-10-03T16:00:00' }),
    ], ['alpha', 'beta', 'gamma'], now, '7')
    expect(m.projects.map((p) => p.code)).toEqual(['beta', 'gamma', 'alpha'])
    expect(m.projects[0].running).toHaveLength(1)
    expect(m.projects[1].auto?.id).toBe('b')
    expect(m.projects[0].todaySec).toBe(3600)
  })

  it('counts each block of a project by day, and holds its running timer', () => {
    const b = blockTimes([
      e({ id: 'a', started_at: '2026-10-03T10:00:00', ended_at: '2026-10-03T11:00:00', sprint_id: 'sp_1' }),
      e({ id: 'b', started_at: '2026-10-01T10:00:00', ended_at: '2026-10-01T10:30:00', sprint_id: 'sp_1' }),
      e({ id: 'c', started_at: '2026-10-03T17:00:00' }),
      e({ id: 'd', started_at: '2026-10-03T17:00:00', source: 'auto', sprint_id: 'sp_2' }),
    ], now, daysBack(now, 7))
    const one = b.get(blockKey('alpha', 'sp_1'))!
    expect([one.todaySec, one.weekSec, one.perDay['2026-10-01'], one.open]).toEqual([3600, 5400, 1800, null])
    expect(b.get(blockKey('alpha', ''))!.open?.id).toBe('c')
    // The smart timer's span is counted, and is not a timer you can stop.
    expect(b.get(blockKey('alpha', 'sp_2'))!.open).toBe(null)
  })
})
