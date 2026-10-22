import { afterEach, describe, expect, it } from 'vitest'

import { isoOf, readings, windowDays } from './week'
import type { Block } from './deck'

// The owner's clock is east of Greenwich; the bugs only show there and at a
// clock change. Node reads TZ again when it is set.
const env = (globalThis as unknown as { process: { env: Record<string, string | undefined> } }).process.env
const zone = env.TZ
afterEach(() => { env.TZ = zone })

const block = (started: string): Block => ({
  id: 'sp_1', name: 'b', project: 'p', started_date: started, days_left: 3, ran_days: 2,
  tasks_total: 2, tasks_done: 0, tasks_doing: 0, today_n: 0, human_min: 0, agent_min: 0, tasks: [], timer: null,
})
const day = (date: string, human_min = 0) => ({ date, done: 0, human_min, agent_min: 0, events: 0 })

describe('the sprint week window', () => {
  for (const tz of ['Australia/Sydney', 'America/Los_Angeles', 'UTC']) {
    it(`names each local day by itself (${tz})`, () => {
      env.TZ = tz
      const days = windowDays('2026-10-06', 7)
      expect(days.map(isoOf)).toEqual(['2026-09-30', '2026-10-01', '2026-10-02', '2026-10-03', '2026-10-04', '2026-10-05', '2026-10-06'])
    })
  }

  it('reads a local midnight as its own day, not the UTC one', () => {
    env.TZ = 'Australia/Sydney'
    expect(isoOf(new Date(2026, 9, 6).getTime())).toBe('2026-10-06')
  })

  it('steps by the calendar across a clock change', () => {
    // Sydney moved its clocks forward on 2026-10-04.
    env.TZ = 'Australia/Sydney'
    const days = windowDays('2026-10-10', 30)
    expect(new Set(days.map(isoOf)).size).toBe(30)
    expect(days.every((ms) => new Date(ms).getHours() === 0)).toBe(true)
  })

  it("counts a block's first day as a day it was alive", () => {
    env.TZ = 'Australia/Sydney'
    const r = readings(block('2026-10-01'), [day('2026-09-30'), day('2026-10-01', 60), day('2026-10-02')])
    expect(r.span).toBe(2)
    expect(r.worked).toBe(1)
  })
})
