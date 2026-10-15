import { describe, expect, it } from 'vitest'

import type { CalTask, Milestone } from '../calendar/model'
import { LADDERS, distanceWord, readLadder } from './data'

const task = (id: string, over: Partial<CalTask> = {}): CalTask => ({
  id, title: id, project: 'p', status: 'todo', priority: '', assignee: '', created: '2026-09-01', due: '', planned: '',
  resurface: '', done: '', archived: false, sprint_id: '', milestone_id: '', tags: '', ...over,
})
const ms = (id: string, over: Partial<Milestone> = {}): Milestone => ({
  id, project: 'p', title: id, outcome: '', check: '', target_date: '', reached_date: '', status: 'planned', position: 0, proof: '',
  tasks: [], tasks_n: 0, done_n: 0, first_task: '', last_done: '', ...over,
})

describe('reading the ladder', () => {
  it('finds the current step, the open tasks, the distance and the slip', () => {
    const tasks = [task('a', { status: 'done' }), task('b', { due: '2026-09-01' }), task('c', { planned: '2026-09-20' }), task('d'), task('e', { archived: true })]
    const steps = readLadder([
      ms('m1', { position: 1, status: 'reached', tasks: ['a'] }),
      ms('m2', { position: 2, target_date: '2026-09-22', tasks: ['b', 'c', 'e'] }),
      ms('m3', { position: 3, tasks: ['d'], status: 'dropped' }),
      ms('m4', { position: 4 }),
    ], tasks, '2026-09-10')
    expect(steps.map((s) => s.milestone.id)).toEqual(['m1', 'm2', 'm3', 'm4'])
    expect(steps.map((s) => s.current)).toEqual([false, true, false, false])
    expect(steps[1]!.open.map((t) => t.id)).toEqual(['b', 'c'])
    expect(steps[1]!.doneN).toBe(0)
    expect(steps[1]!.daysLeft).toBe(12)
    expect(steps[1]!.slipping).toBe(1)
    expect(steps[0]!.reached && steps[2]!.dropped).toBe(true)
    expect(steps[3]!.daysLeft).toBeNull()
  })
  it('says the distance in words', () => {
    expect(distanceWord(null)).toBe('no date')
    expect(distanceWord(0)).toBe('today')
    expect(distanceWord(1)).toBe('in 1 day')
    expect(distanceWord(-3)).toBe('3 days late')
  })
  it('ships a ladder for every reason', () => {
    for (const steps of Object.values(LADDERS)) expect(steps.length).toBeGreaterThan(1)
  })
})
