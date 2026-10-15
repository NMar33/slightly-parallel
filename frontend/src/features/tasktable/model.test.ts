import { describe, expect, it } from 'vitest'

import { apply, EMPTY, facet, parseQuery, toQuery, type Row } from './model'

const row = (id: string, x: Partial<Row>): Row => ({
  id, title: id, project: 'p', status: 'todo', done: false, sprint_id: '', created: '2026-09-01T10:00', first: '',
  done_at: '', lead_hours: null, work_hours: null, messages: 0, chats: 0, minutes: 0, agents: [], commits: 0,
  files: 0, add: 0, del: 0, closed: '', stretch: 'none', reopened: 0, reports: 0, priority: '', assignee: '',
  impact: '', effort: '', tags: [], lane: '', due: '', starred: false, archived: false, age_days: 3,
  in_status_days: 1, status_since: '', moves: 0, edits: 0, named_in: 0, activity: [], ...x,
})

const rows = [
  row('a', { status: 'doing', messages: 7, stretch: 'estimated', in_status_days: 9 }),
  row('b', { status: 'done', messages: 2, stretch: 'done', closed: '#done' }),
  row('c', { status: 'todo', tags: ['ui', 'fast'], title: 'Polish the header' }),
]

describe('the task table query', () => {
  it('reads lists, numbers, flags, periods and free words', () => {
    const { filter, unknown } = parseQuery('status:doing,todo messages>5 is:stuck done:30d "the header" nope:1')
    expect(filter.status).toEqual(['doing', 'todo'])
    expect(filter.ranges.messages).toEqual([6, null])
    expect(filter.is).toEqual(['stuck'])
    expect(filter.done).toBe(30)
    expect(filter.q).toBe('the header')
    expect(unknown).toEqual(['nope:1'])
  })
  it('writes back what it reads', () => {
    const q = 'status:doing,todo messages>=6 is:stuck done:30d header'
    expect(toQuery(parseQuery(q).filter)).toBe(q)
    expect(toQuery(EMPTY)).toBe('')
  })
  it('cuts the rows, and counts each facet with its own cut left out', () => {
    expect(apply(rows, parseQuery('is:stuck').filter).map((r) => r.id)).toEqual(['a'])
    expect(apply(rows, parseQuery('tag:ui header').filter).map((r) => r.id)).toEqual(['c'])
    const f = parseQuery('status:done').filter
    expect(facet(rows, f, 'status').find((x) => x.value === 'doing')?.n).toBe(1)
  })
})

describe('strict signs on measures', () => {
  it('keep a task at 5.5 hours for lead>5, and read a count as the next count', () => {
    expect(parseQuery('lead>5').filter.ranges.lead).toEqual([5.01, null])
    expect(parseQuery('messages>5').filter.ranges.messages).toEqual([6, null])
  })
})
