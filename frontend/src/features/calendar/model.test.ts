import { describe, expect, it } from 'vitest'

import {
  addDays, applyLens, dayLabel, daysBetween, factLine, itemsOn, monthGrid, parseLayers,
  parseQuick, relativeDay, serializeLayers, sprintSpans, startOfWeek, toSpDate, type CalEntry, type CalTask, type Milestone,
} from './model'

const task = (id: string, over: Partial<CalTask> = {}): CalTask => ({
  id, title: id, project: 'p', status: 'todo', priority: '', assignee: '', created: '2026-09-01', due: '', planned: '',
  resurface: '', done: '', archived: false, sprint_id: '', milestone_id: '', tags: '', ...over,
})

describe('dates', () => {
  it('walks days and weeks in local time', () => {
    expect(addDays('2026-09-30', 1)).toBe('2026-10-01')
    expect(daysBetween('2026-09-01', '2026-09-10')).toBe(9)
    expect(startOfWeek('2026-09-10')).toBe('2026-09-07')
    expect(startOfWeek('2026-09-07')).toBe('2026-09-07')
    expect(startOfWeek('2026-09-13')).toBe('2026-09-07')
    expect(dayLabel('2026-09-10')).toBe('Thu 10 Sep')
    expect(toSpDate('2026-09-10')).toBe('2609-10')
    expect(toSpDate('2609-10')).toBe('2609-10')
    expect(toSpDate('')).toBe('')
  })
  it('lays a month out in Monday weeks and drops an empty sixth', () => {
    const g = monthGrid('2026-09')
    expect(g.length).toBe(5)
    expect(g[0]![0]).toBe('2026-08-31')
    expect(g[4]![6]).toBe('2026-10-04')
    expect(monthGrid('2026-11').length).toBe(6)
    expect(monthGrid('2027-02').length).toBe(4)
    expect(monthGrid('2027-02')[3]![6]).toBe('2027-02-28')
  })
  it('says when in a person\'s words', () => {
    expect(relativeDay('2026-09-10', '2026-09-10')).toBe('today')
    expect(relativeDay('2026-09-11', '2026-09-10')).toBe('tomorrow')
    expect(relativeDay('2026-09-13', '2026-09-10')).toBe('in 3 days')
    expect(relativeDay('2026-09-01', '2026-09-10')).toBe('9 days ago')
    expect(relativeDay('2026-11-01', '2026-09-10')).toBe('1 Nov')
  })
})

describe('layers and lenses', () => {
  it('round-trips layers and ignores unknown ones', () => {
    expect(parseLayers(undefined).length).toBe(7)
    expect(parseLayers('due,nope,facts')).toEqual(['due', 'facts'])
    expect(serializeLayers(parseLayers(undefined))).toBe('')
    expect(serializeLayers(['due'])).toBe('due')
  })
  it('narrows tasks the way the pill says', () => {
    const rows = [
      task('a', { due: '2026-09-01' }),
      task('b', { due: '2026-09-20' }),
      task('c', { status: 'done', done: '2026-09-05' }),
      task('d', { planned: '2026-09-08' }),
      task('e', { created: '2026-07-01' }),
      task('f', { status: 'agent' }),
    ]
    const ids = (lens: Parameters<typeof applyLens>[1], q = '') => applyLens(rows, lens, '2026-09-10', q).map((t) => t.id)
    expect(ids('overdue')).toEqual(['a'])
    expect(ids('slipped')).toEqual(['d'])
    expect(ids('done')).toEqual(['c'])
    expect(ids('old')).toEqual(['e'])
    expect(ids('agent')).toEqual(['f'])
    expect(ids('undated')).toEqual(['d', 'e', 'f'])
    expect(ids('all', 'F')).toEqual(['f'])
  })
})

describe('what a day holds', () => {
  const entry = (id: string, date: string, end = ''): CalEntry => ({
    id, project: 'p', kind: 'meeting', date, time: '', end_date: end, end_time: '', title: id, body: '', task_id: '',
    milestone_id: '', people: '', link: '', status: 'open', created_at: '', updated_at: '', actor: '', source: 'calendar',
  })
  const ms: Milestone = {
    id: 'ms_1', project: 'p', title: 'Article out', outcome: '', check: '', target_date: '2026-09-10', reached_date: '',
    status: 'planned', position: 1, proof: '', tasks: [], tasks_n: 0, done_n: 0, first_task: '', last_done: '',
  }
  it('orders milestone, entries, then tasks by why, and shows a task once', () => {
    const p = {
      tasks: [task('t1', { due: '2026-09-10', planned: '2026-09-10' }), task('t2', { done: '2026-09-10', status: 'done' }), task('t3', { created: '2026-09-10' })],
      entries: [entry('e1', '2026-09-10'), entry('e2', '2026-09-08', '2026-09-12'), entry('e3', '2026-09-11')],
      milestones: [ms],
    }
    const items = itemsOn(p, '2026-09-10', ['due', 'planned', 'done', 'entries', 'milestones'])
    expect(items.map((i) => i.id)).toEqual(['ms_1', 'e1', 'e2', 't1', 't2'])
    expect(items.filter((i) => i.kind === 'task').map((i) => (i as { why: string }).why)).toEqual(['due', 'done'])
    expect(itemsOn(p, '2026-09-10', ['created']).map((i) => i.id)).toEqual(['t3'])
  })
  it('clips sprint spans to the range and keeps an open one running', () => {
    const spans = sprintSpans([
      { id: 's1', name: 'A', status: 'active', started: '2026-08-20', ended: '', bet_days: 21 },
      { id: 's2', name: 'B', status: 'done', started: '2026-07-01', ended: '2026-07-20', bet_days: null },
    ], '2026-09-01', '2026-09-30')
    expect(spans).toEqual([{ sprint: expect.objectContaining({ id: 's1' }), from: '2026-09-01', to: '2026-09-30', open: true }])
  })
  it('writes the fact line from what is there', () => {
    const f = { tasks_created: 1, tasks_done: 2, sessions: 3, turns: 41, minutes: 120, commits: 12, files: 9, add: 812, del: 40, hours_min: 150, standups: 1, decisions: 0, scans: 1, problems: 0, entries: 0 }
    expect(factLine(f)).toBe('3 chats · 41 turns · 12 commits · +812 −40 · 2.5h logged · 2 done · 1 written · 2 checkpoints')
    expect(factLine({ ...f, sessions: 0, turns: 0, commits: 0, add: 0, del: 0, hours_min: 0, tasks_done: 0, tasks_created: 0, standups: 0, scans: 0 })).toBe('')
  })
})

describe('quick add', () => {
  const base = '2026-09-10' // a Thursday
  it('reads kind, date and time out of a line and keeps the rest as the title', () => {
    expect(parseQuick('call with Anna tomorrow 14:00', base)).toEqual({ kind: 'meeting', title: 'call with Anna', date: '2026-09-11', time: '14:00', end_time: '' })
    expect(parseQuick('meeting with Anna tomorrow 14:00-15:30', base)).toEqual({ kind: 'meeting', title: 'meeting with Anna', date: '2026-09-11', time: '14:00', end_time: '15:30' })
    expect(parseQuick('deadline: grant form fri', base)).toEqual({ kind: 'deadline', title: 'grant form', date: '2026-09-11', time: '', end_time: '' })
    expect(parseQuick('grant form due next mon', base).date).toBe('2026-09-21')
    expect(parseQuick('/task fix the login', base)).toEqual({ kind: 'task', title: 'fix the login', date: base, time: '', end_time: '' })
    expect(parseQuick('note 2026-09-20 the client renamed the product', base)).toEqual({ kind: 'note', title: 'the client renamed the product', date: '2026-09-20', time: '', end_time: '' })
    expect(parseQuick('remind me to follow up in 3 days', base)).toEqual({ kind: 'reminder', title: 'me to follow up', date: '2026-09-13', time: '', end_time: '' })
    expect(parseQuick('conference talk 24.09', base)).toEqual({ kind: 'event', title: 'conference talk', date: '2026-09-24', time: '', end_time: '' })
    expect(parseQuick('the client renamed the product', base).kind).toBe('note')
    // words and version numbers are not dates
    expect(parseQuick('/task release 1.2', base)).toEqual({ kind: 'task', title: 'release 1.2', date: base, time: '', end_time: '' })
    expect(parseQuick('deadline 31.02 the form', base).date).toBe(base)
    expect(parseQuick('sat with the team about pricing', base).date).toBe(base)
    expect(parseQuick('renamed the product to Sun', base).date).toBe(base)
    expect(parseQuick('call on sat', base).date).toBe('2026-09-12')
    expect(parseQuick('meeting friday 09:30', base)).toEqual({ kind: 'meeting', title: 'meeting', date: '2026-09-11', time: '09:30', end_time: '' })
    expect(parseQuick('meeting 12.09 at 9:30', base)).toEqual({ kind: 'meeting', title: 'meeting at', date: '2026-09-12', time: '09:30', end_time: '' })
    expect(parseQuick('meeting: board review 09:00', base).title).toBe('board review')
  })
})
