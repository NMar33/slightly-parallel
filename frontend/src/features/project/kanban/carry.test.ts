import { beforeEach, describe, expect, it } from 'vitest'

import { carrySeenToday, dayWord, fromWhen, leftovers, markCarrySeen } from './carry'
import type { TaskRow } from './model'

const t = (id: string, over: Partial<TaskRow> = {}): TaskRow =>
  ({ id, title: id, status: 'doing', ...over }) as TaskRow

describe('leftovers', () => {
  it('keeps open cards planned before today, newest day first', () => {
    const rows = [
      t('a', { today_on: '2026-09-08' }),
      t('b', { today_on: '2026-09-09' }),
      t('c', { today_on: '2026-09-10' }),
      t('d', { today_on: '2026-09-09', status: 'done' }),
      t('e', { today_on: '2026-09-09', archived_at: '2026-09-09T10:00' }),
      t('f'),
      t('g', { today_on: '2026-09-09', status: 'Done-Archived' }),
    ]
    expect(leftovers(rows, '2026-09-10').map((r) => r.id)).toEqual(['b', 'a'])
  })
})

describe('the words for when', () => {
  it('names the day the way a person would', () => {
    expect(dayWord('2026-09-09', '2026-09-10')).toBe('yesterday')
    expect(dayWord('2026-09-07', '2026-09-10')).toBe('Monday')
    expect(dayWord('2026-09-04', '2026-09-10')).toBe('Friday')
    // seven days back the weekday is today's own name: a date instead
    expect(dayWord('2026-09-03', '2026-09-10')).toBe('3 Sep')
    expect(dayWord('2026-08-01', '2026-09-10')).toBe('1 Aug')
    expect(fromWhen([t('a', { today_on: '2026-09-09' })], '2026-09-10')).toBe('yesterday')
    expect(fromWhen([t('a', { today_on: '2026-09-09' }), t('b', { today_on: '2026-09-01' })], '2026-09-10')).toBe('yesterday and earlier')
    expect(fromWhen([], '2026-09-10')).toBe('')
  })
})

describe('asked once a day', () => {
  beforeEach(() => localStorage.clear())
  it('remembers the day the operator was asked', () => {
    expect(carrySeenToday('2026-09-10')).toBe(false)
    markCarrySeen('2026-09-10')
    expect(carrySeenToday('2026-09-10')).toBe(true)
    expect(carrySeenToday('2026-09-11')).toBe(false)
  })
})
