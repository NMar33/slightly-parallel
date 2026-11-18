import { describe, expect, it } from 'vitest'

import { chipState, chipText } from './timer'
import type { TimeEntry } from '../../project/timeEntry'

const e = (over: Partial<TimeEntry>): TimeEntry => ({ id: 'tm_1', project: 'harbor', started_at: '2026-11-18T10:00:00+11:00', ...over })
const auto = (working: string[] = [], away: string[] = []) => ({
  working: working.map((project) => ({ project, entry_id: 'tm_a', task_id: '', top: 100 })),
  away: away.map((project) => ({ entry_id: 'tm_1', project, from: '', to: '', sec: 600, long: false })),
})

describe('the timer in the terminal window', () => {
  it('counts when a timer of the project runs or the smart timer counts it', () => {
    expect(chipState('harbor', [e({})], auto())).toBe('counting')
    expect(chipState('harbor', [], auto(['harbor']))).toBe('counting')
    expect(chipState('harbor', [e({ project: 'kelp' })], auto(['kelp']))).toBe('off')
  })

  it('is paused when every open timer of the project is paused, and away while a notice waits', () => {
    expect(chipState('harbor', [e({ paused_at: '2026-11-18T10:30:00+11:00' })], auto())).toBe('paused')
    expect(chipState('harbor', [e({})], auto([], ['harbor']))).toBe('away')
  })

  it('says the project\'s time and the day\'s, with 0m for none', () => {
    expect(chipText('harbor', 80, 185)).toBe('harbor 1h 20m · today 3h 05m')
    expect(chipText('harbor', 0, 0)).toBe('harbor 0m · today 0m')
  })
})
