import { describe, expect, it } from 'vitest'
import type { SearchHit } from '../../lib/searchHits'
import {
  applyClauses,
  buildFacets,
  buildResults,
  facetValue,
  markParts,
  monthOf,
  narrowingChain,
  popClause,
  toggleClause,
  type Clause,
} from './filter'

const hit = (h: Partial<SearchHit> & { kind: string; id: string }): SearchHit => ({
  title: 'a title',
  project: 'slightly-parallel',
  date: '2609-21',
  snippet: 'a snippet',
  where: 'text',
  ...h,
})

const turn = (id: string, extra: Partial<SearchHit> = {}): SearchHit =>
  hit({ kind: 'turn', id, role: 'agent', turn: 1, at: '10:00', agent_id: id.split('#')[0], ...extra })

const corpus: SearchHit[] = [
  hit({ kind: 'scan', id: 'sn_1', where: 'title' }),
  hit({ kind: 'scan', id: 'sn_2', date: '2608-14' }),
  hit({ kind: 'architecture', id: 'ar_1', where: 'title' }),
  hit({ kind: 'architecture', id: 'ar_2', project: 'atlas' }),
  turn('cc-a#1.user', { role: 'user', turn: 1, count: 2 }),
  turn('cc-a#3.agent', { turn: 3 }),
  turn('cc-b#2.agent', { turn: 2, date: '2609-23', agent_id: 'cc-b', title: 'night-up' }),
]

describe('the month of a hit', () => {
  it('writes both date formats the same way', () => {
    expect(monthOf('2609-21')).toBe('2026-09')
    expect(monthOf('2026-09')).toBe('2026-09')
    expect(monthOf('')).toBe('')
  })
})

describe('facet values', () => {
  it('names the group a hit belongs to', () => {
    expect(facetValue(corpus[0], 'kind')).toBe('scan')
    expect(facetValue(corpus[0], 'project')).toBe('slightly-parallel')
    expect(facetValue(corpus[1], 'month')).toBe('2026-08')
    expect(facetValue(corpus[0], 'where')).toBe('title')
  })
  it('gives a role only to a turn', () => {
    expect(facetValue(corpus[4], 'role')).toBe('user')
    expect(facetValue(corpus[0], 'role')).toBe('')
  })
  it('names a hit with no project and no date', () => {
    expect(facetValue(hit({ kind: 'task', id: 't', project: '' }), 'project')).toBe('(no project)')
    expect(facetValue(hit({ kind: 'task', id: 't', date: '' }), 'month')).toBe('(no date)')
  })
})

describe('narrowing by clauses', () => {
  it('keeps everything when there is no clause', () => {
    expect(applyClauses(corpus, []).length).toBe(7)
  })
  it('takes one group as an or', () => {
    const clauses: Clause[] = [
      { group: 'kind', value: 'scan' },
      { group: 'kind', value: 'architecture' },
    ]
    expect(applyClauses(corpus, clauses).map((h) => h.id)).toEqual(['sn_1', 'sn_2', 'ar_1', 'ar_2'])
  })
  it('takes two groups as an and', () => {
    const clauses: Clause[] = [
      { group: 'kind', value: 'scan' },
      { group: 'where', value: 'title' },
    ]
    expect(applyClauses(corpus, clauses).map((h) => h.id)).toEqual(['sn_1'])
  })
  it('drops a hit the group does not apply to', () => {
    const kept = applyClauses(corpus, [{ group: 'role', value: 'agent' }])
    expect(kept.map((h) => h.id)).toEqual(['cc-a#3.agent', 'cc-b#2.agent'])
  })
  it('counts the matches left after each clause', () => {
    const clauses: Clause[] = [
      { group: 'kind', value: 'scan' },
      { group: 'where', value: 'title' },
    ]
    expect(narrowingChain(corpus, clauses)).toEqual([7, 2, 1])
  })
})

describe('the counted rail', () => {
  it('counts every value of every group that applies', () => {
    const facets = buildFacets(corpus, [])
    const kind = facets.find((f) => f.group === 'kind')!
    expect(kind.base).toBe(7)
    expect(kind.values.map((v) => `${v.value}:${v.count}`)).toEqual([
      'turn:3',
      'architecture:2',
      'scan:2',
    ])
    const role = facets.find((f) => f.group === 'role')!
    expect(role.values.map((v) => `${v.value}:${v.count}`)).toEqual(['agent:2', 'user:1'])
  })
  it('counts a group over what the other clauses already keep', () => {
    const facets = buildFacets(corpus, [{ group: 'kind', value: 'scan' }])
    const where = facets.find((f) => f.group === 'where')!
    expect(where.base).toBe(2)
    expect(where.values.map((v) => `${v.value}:${v.count}`)).toEqual(['text:1', 'title:1'])
  })
  it('leaves its own group whole, so the other values still show what they buy', () => {
    const facets = buildFacets(corpus, [{ group: 'kind', value: 'scan' }])
    const kind = facets.find((f) => f.group === 'kind')!
    expect(kind.base).toBe(7)
    expect(kind.values.find((v) => v.value === 'scan')?.active).toBe(true)
    expect(kind.values.find((v) => v.value === 'turn')?.count).toBe(3)
  })
  it('drops a group no hit answers', () => {
    const facets = buildFacets([corpus[0]], [])
    expect(facets.some((f) => f.group === 'role')).toBe(false)
  })
})

describe('pushing and popping clauses', () => {
  it('adds a clause, then takes the same one off', () => {
    const one = toggleClause([], { group: 'kind', value: 'scan' })
    expect(one).toEqual([{ group: 'kind', value: 'scan' }])
    expect(toggleClause(one, { group: 'kind', value: 'scan' })).toEqual([])
  })
  it('pops the last clause only', () => {
    const two: Clause[] = [
      { group: 'kind', value: 'scan' },
      { group: 'where', value: 'title' },
    ]
    expect(popClause(two)).toEqual([{ group: 'kind', value: 'scan' }])
    expect(popClause([])).toEqual([])
  })
})

describe('the results', () => {
  it('keeps entries apart and gathers turns under their chat, newest chat first', () => {
    const r = buildResults(corpus)
    expect(r.entries.map((h) => h.id)).toEqual(['sn_1', 'sn_2', 'ar_1', 'ar_2'])
    expect(r.chats.map((c) => c.agentId)).toEqual(['cc-b', 'cc-a'])
    expect(r.chats[1].turns.map((t) => t.turn)).toEqual([1, 3])
    expect(r.chats[1].occurrences).toBe(3)
    expect(r.rows.map((h) => h.id)).toEqual([
      'sn_1', 'sn_2', 'ar_1', 'ar_2', 'cc-b#2.agent', 'cc-a#1.user', 'cc-a#3.agent',
    ])
  })
})

describe('marking the word', () => {
  it('marks every occurrence, whatever the case', () => {
    expect(markParts('Map the map', 'map')).toEqual([
      { text: 'Map', hit: true },
      { text: ' the ', hit: false },
      { text: 'map', hit: true },
    ])
  })
  it('leaves text alone when the word is not in it', () => {
    expect(markParts('a snippet', 'map')).toEqual([{ text: 'a snippet', hit: false }])
    expect(markParts('a snippet', '  ')).toEqual([{ text: 'a snippet', hit: false }])
    expect(markParts('', 'map')).toEqual([])
  })
})
