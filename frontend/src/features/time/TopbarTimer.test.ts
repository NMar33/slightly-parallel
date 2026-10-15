import { describe, expect, it } from 'vitest'

import { awayLine, timerLine } from './TopbarTimer'
import type { TimeAuto } from '../../lib/timer'
import type { TimeEntry } from '../project/timeEntry'

const e = (over: Partial<TimeEntry>): TimeEntry => ({ id: 'tm_1', project: 'alpha', started_at: '2026-10-03T10:00:00', ...over })

describe('the timer in the top bar', () => {
  it('shows nothing running as idle', () => {
    expect(timerLine([])).toEqual({ state: 'idle', entry: null, more: 0 })
  })

  it('shows your running timer before the smart timer and before a paused one', () => {
    const line = timerLine([
      e({ id: 'p', paused_at: '2026-10-03T10:30:00' }),
      e({ id: 'a', source: 'auto' }),
      e({ id: 'm', project: 'beta' }),
    ])
    expect([line.state, line.entry?.id, line.more]).toEqual(['running', 'm', 2])
  })

  it('is paused only when every timer is paused', () => {
    expect(timerLine([e({ id: 'p', paused_at: '2026-10-03T10:30:00' })]).state).toBe('paused')
    expect(timerLine([e({ id: 'p', paused_at: '2026-10-03T10:30:00' }), e({ id: 'a', source: 'auto' })]).entry?.id).toBe('a')
  })

  it('says when the timer pauses by itself, or why it does not', () => {
    const st = { idle_pause: true, idle_source: 'gnome', idle_minutes: 10 } as TimeAuto
    expect(awayLine(st)).toBe('pauses after 10 min away (read from GNOME)')
    expect(awayLine({ ...st, idle_source: '' })).toMatch(/does not pause automatically/)
    expect(awayLine({ ...st, idle_pause: false })).toMatch(/is off/)
  })
})
