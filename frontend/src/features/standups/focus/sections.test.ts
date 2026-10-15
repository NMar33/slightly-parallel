import { describe, expect, it } from 'vitest'

import type { DayRecord, Standup } from '../data'
import { bulletsOf, needsOf, sectionsOf } from './sections'

const standup = (x: Partial<Standup>): Standup => ({
  row: { id: 'st_1', created_date: '2610-08', created_time: '10:00', project: 'p', agent_id: 'a', l1: '' },
  at: 0, day: '2610-08', summary: 's', deviation: '', movement: [], detail: '', story: '', decisions: [], forgotten: [],
  covers: '2610-07', who: 'a', loaded: true, ...x,
})

describe('standup focus sections', () => {
  it('takes what needs an answer out of the detail, skipping "none"', () => {
    const d = needsOf('**Needs an answer:** push or wait? **Needs an answer:** none left open.\n**Next:** the map.\n**State:** green.')
    expect(d.needs).toEqual(['push or wait?'])
    expect(d.rest).toBe('**Next:** the map.\n**State:** green.')
    expect(needsOf('**Needs an answer:** none.').needs).toEqual([])
  })

  it('reads a markdown list as its items, a wrapped line joined to its item', () => {
    expect(bulletsOf('- one\n- two\n  more')).toEqual(['one', 'two more'])
    expect(bulletsOf('plain text')).toEqual(['plain text'])
    expect(bulletsOf('')).toEqual([])
  })

  it('lists the sections in reading order, the empty ones left out', () => {
    const rec: DayRecord = { tasks: [{ id: 'tk_1', title: 't', status: 'done', moves: [], agents: [] }], agents: [], created: [] }
    const s = standup({ deviation: '- broke\n- redone', movement: ['New: a'], detail: '**Needs an answer:** which?', forgotten: ['x'] })
    expect(sectionsOf(s, rec)).toEqual([
      { kind: 'day', count: 1 }, { kind: 'needs', count: 1 }, { kind: 'wrong', count: 2 },
      { kind: 'moved', count: 1 }, { kind: 'tasks', count: 1 }, { kind: 'forgotten', count: 1 },
    ])
    expect(sectionsOf(standup({})).map((x) => x.kind)).toEqual(['day'])
  })
})
