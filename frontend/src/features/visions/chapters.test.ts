import { describe, expect, it } from 'vitest'

import { chaptersOf, matches, members, monthOf, shortDate } from './chapters'
import type { KeptSet, Vision } from './data'

const v = (id: string, tags: string | null, project = 'p', date = '2609-16'): Vision => ({
  row: { id, created_date: date, created_time: '10:00', project, agent_id: 'a', l1: `title ${id}`, source: 'captured', session_id: null, source_turn: 1, versions_n: 1, tags },
  l2: `text ${id}`,
  kept: null,
})

describe('chapters', () => {
  const shown = [v('a', 'ui,backend'), v('b', 'backend'), v('c', null, 'q', '2608-02')]
  const sets: KeptSet[] = [
    { id: 's1', name: 'First', kind: 'vision', items: ['a', 'c', 'missing'], created_at: '', updated_at: '' },
    { id: 's2', name: 'Second', kind: 'vision', items: ['a'], created_at: '', updated_at: '' },
  ]

  it('by tag: the first tag is home, the others are references, untagged last', () => {
    const out = chaptersOf(shown, 'tag', sets)
    expect(out.map((c) => c.title)).toEqual(['backend', 'ui', 'No tag'])
    expect(out[0]!.full.map((x) => x.row.id)).toEqual(['b'])
    expect(out[0]!.refs.map((r) => [r.v.row.id, r.home])).toEqual([['a', 'ui']])
    expect(out[1]!.tag).toBe('ui')
    expect(out[2]!.tag).toBeUndefined()
    expect(members(out[0]!).length).toBe(2)
  })

  it('by set: written out in the first set, referenced in the rest, loose ones last', () => {
    const out = chaptersOf(shown, 'set', sets)
    expect(out.map((c) => c.title)).toEqual(['First', 'Second', 'Not in a set'])
    expect(out[0]!.full.map((x) => x.row.id)).toEqual(['a', 'c'])
    expect(out[1]!.refs.map((r) => [r.v.row.id, r.home])).toEqual([['a', 'First']])
    expect(out[2]!.full.map((x) => x.row.id)).toEqual(['b'])
    expect(out[2]!.setId).toBeUndefined()
  })

  it('by project: biggest first; by month: in the order given', () => {
    expect(chaptersOf(shown, 'project', sets).map((c) => [c.title, c.full.length])).toEqual([['p', 2], ['q', 1]])
    expect(chaptersOf(shown, 'month', sets).map((c) => c.title)).toEqual(['September 2026', 'August 2026'])
  })

  it("names dates the page's way", () => {
    expect(monthOf(v('x', null))).toBe('September 2026')
    expect(shortDate(v('x', null, 'p', '2608-02'))).toBe('2 Aug')
    expect(monthOf(v('x', null, 'p', 'bad'))).toBe('Undated')
  })

  it('matches every word of the query somewhere in the entry', () => {
    const a = v('a', 'ui')
    expect(matches(a, '')).toBe(true)
    expect(matches(a, 'TITLE a')).toBe(true)
    expect(matches(a, 'text ui')).toBe(true)
    expect(matches(a, 'text nowhere')).toBe(false)
  })
})
