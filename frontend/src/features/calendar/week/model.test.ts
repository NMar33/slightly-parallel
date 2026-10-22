import { describe, expect, it } from 'vitest'

import type { CalEntry, CalTask, DayItem } from '../model'
import { factRows, orderDayItems, pickInWeek, stripRange, weekTally } from './model'

const entry = (id: string, time: string): CalEntry => ({
  id, project: 'p', kind: 'meeting', date: '2026-09-10', time, end_date: '', end_time: '', title: id, body: '', task_id: '',
  milestone_id: '', people: '', link: '', status: 'open', created_at: '', updated_at: '', actor: '', source: 'calendar',
})
const task = (id: string, over: Partial<CalTask> = {}): CalTask => ({
  id, title: id, project: 'p', status: 'todo', priority: '', assignee: '', created: '', due: '', planned: '', resurface: '', done: '',
  archived: false, sprint_id: '', milestone_id: '', tags: '', ...over,
})

describe('the strip', () => {
  it('covers six weeks before, the week, and the next', () => {
    const s = stripRange('2026-09-07')
    expect(s.from).toBe('2026-07-27')
    expect(s.to).toBe('2026-09-20')
    expect(s.weeks.length).toBe(8)
    expect(s.weeks[6]).toBe('2026-09-07')
  })
})

describe('a day column', () => {
  it('puts timed entries by the clock, untimed after, tasks last', () => {
    const items: DayItem[] = [
      { kind: 'task', why: 'due', task: task('t1'), id: 't1', title: 't1' },
      { kind: 'entry', entry: entry('late', '16:00'), id: 'late', title: 'late' },
      { kind: 'entry', entry: entry('untimed', ''), id: 'untimed', title: 'untimed' },
      { kind: 'entry', entry: entry('early', '09:30'), id: 'early', title: 'early' },
      { kind: 'task', why: 'planned', task: task('t2'), id: 't2', title: 't2' },
    ]
    expect(orderDayItems(items).map((i) => i.id)).toEqual(['early', 'late', 'untimed', 't1', 't2'])
  })
})

describe('the tally and the numbers', () => {
  it('counts the week from the payload', () => {
    const p = {
      days: { '2026-09-07': { sessions: 3 }, '2026-09-09': { sessions: 4 } } as never,
      tasks: [task('a', { due: '2026-09-08' }), task('b', { due: '2026-09-08', status: 'done' }), task('c', { due: '2026-09-20' })],
      entries: [{ ...entry('e', ''), date: '2026-09-05', end_date: '2026-09-07' }, entry('f', '')],
    }
    expect(weekTally(p, '2026-09-07', '2026-09-10')).toBe('this week · 1 due · 2 entries · 1 chats/day')
    expect(weekTally(p, '2026-09-14', '2026-09-10')).toBe('a week ahead · 1 due · 0 entries')
    expect(weekTally(undefined, '2026-09-07', '2026-09-10')).toBe('')
  })
  it('lists only the numbers that are there', () => {
    expect(factRows()).toEqual([])
    expect(factRows({ tasks_created: 0, tasks_done: 2, sessions: 1, turns: 0, minutes: 0, commits: 3, files: 0, add: 10, del: 2, hours_min: 90, standups: 1, decisions: 0, scans: 0, problems: 0, entries: 0 }))
      .toEqual([['chats', '1'], ['commits', '3'], ['lines', '+10 −2'], ['hours logged', '1.5h'], ['done', '2'], ['checkpoints', '1']])
  })
})

describe('the pick when the week moves', () => {
  it('keeps the weekday, in the new week', () => {
    expect(pickInWeek('2026-10-07', '2026-09-28')).toBe('2026-09-30')
    // Across the October clock change (Europe, Australia) the weekday holds.
    expect(pickInWeek('2026-10-04', '2026-10-26')).toBe('2026-11-01')
  })
})
