import { describe, expect, it } from 'vitest'

import type { Row } from './data'
import { CHIPS, applyChips, chipCounts, keeps, toggleChip, type ChipId } from './outcome'

const chat = (id: string, p: Partial<Row> = {}): Row => ({
  id,
  created_date: '2609-21',
  start_time: '14:00',
  end_time: '14:20',
  duration_min: 20,
  turns_n: 2,
  l1: 'a chat',
  agent_id: `cc-${id}`,
  project: 'slightly-parallel',
  produced: {},
  marks: {},
  tasks: 0,
  matches: 0,
  git: { commits: 0, files: 0, add: 0, del: 0 },
  agent: null,
  ...p,
})

const rows: Row[] = [
  chat('a', { git: { commits: 2, files: 3, add: 10, del: 4 }, tasks: 1, turns_n: 12, duration_min: 90 }),
  chat('b', { git: { commits: 1, files: 1, add: 2, del: 0 }, tasks: 1 }),
  chat('c', { produced: { scans: 1, files: 2 }, turns_n: 11 }),
  chat('d', { produced: { visions: 1 } }),
  chat('e', { duration_min: 60, produced: { problems: 1, decisions: 1 } }),
  chat('f'),
]

const ids = (list: Row[]) => list.map((s) => s.id)
const count = (list: ReturnType<typeof chipCounts>, id: ChipId) => list.find((c) => c.id === id)!.count

describe('the chips', () => {
  it('names every cut once, in reading order', () => {
    const ids = CHIPS.map((c) => c.id)
    expect(new Set(ids).size).toBe(ids.length)
    expect(ids.slice(0, 4)).toEqual(['commits', 'task', 'scan', 'file'])
    expect(ids.slice(-2)).toEqual(['turns10', 'hour'])
  })

  it('reads what a chat left behind', () => {
    expect(ids(applyChips(rows, ['commits']))).toEqual(['a', 'b'])
    expect(ids(applyChips(rows, ['task']))).toEqual(['a', 'b'])
    expect(ids(applyChips(rows, ['scan']))).toEqual(['c'])
    expect(ids(applyChips(rows, ['file']))).toEqual(['c'])
    expect(ids(applyChips(rows, ['vision']))).toEqual(['d'])
    expect(ids(applyChips(rows, ['problem']))).toEqual(['e'])
    expect(ids(applyChips(rows, ['decision']))).toEqual(['e'])
  })

  it('reads the weight of a chat', () => {
    expect(ids(applyChips(rows, ['turns10']))).toEqual(['a', 'c'])
    expect(ids(applyChips(rows, ['hour']))).toEqual(['a', 'e'])
  })

  it('keeps every chat when nothing is picked', () => {
    expect(applyChips(rows, [])).toBe(rows)
  })
})

describe('combining chips', () => {
  it('asks for every chip at once', () => {
    expect(ids(applyChips(rows, ['commits', 'turns10']))).toEqual(['a'])
    expect(ids(applyChips(rows, ['scan', 'hour']))).toEqual([])
    expect(keeps(rows[0]!, ['commits', 'task', 'turns10', 'hour'])).toBe(true)
    expect(keeps(rows[1]!, ['commits', 'turns10'])).toBe(false)
  })

  it('clears one on a second click', () => {
    expect(toggleChip([], 'scan')).toEqual(['scan'])
    expect(toggleChip(['scan'], 'hour')).toEqual(['scan', 'hour'])
    expect(toggleChip(['scan', 'hour'], 'scan')).toEqual(['hour'])
  })
})

describe('the counts on the chips', () => {
  it('counts every chat when nothing is picked', () => {
    const counts = chipCounts(rows, [])
    expect(count(counts, 'commits')).toBe(2)
    expect(count(counts, 'turns10')).toBe(2)
    expect(count(counts, 'hour')).toBe(2)
    expect(count(counts, 'vision')).toBe(1)
  })

  it('counts over what the other chips allow', () => {
    const counts = chipCounts(rows, ['commits'])
    // Of a and b: both name a task, one has ten turns, one ran an hour.
    expect(count(counts, 'task')).toBe(2)
    expect(count(counts, 'turns10')).toBe(1)
    expect(count(counts, 'hour')).toBe(1)
    expect(count(counts, 'scan')).toBe(0)
  })

  it('gives a picked chip the number of chats on the page', () => {
    const picked: ChipId[] = ['commits', 'turns10']
    const counts = chipCounts(rows, picked)
    const left = applyChips(rows, picked).length
    expect(count(counts, 'commits')).toBe(left)
    expect(count(counts, 'turns10')).toBe(left)
    expect(counts.filter((c) => c.on).map((c) => c.id)).toEqual(['commits', 'turns10'])
  })

  it('keeps a chip in the set when its count is zero', () => {
    const counts = chipCounts(rows, ['scan'])
    expect(counts).toHaveLength(CHIPS.length)
    expect(count(counts, 'hour')).toBe(0)
  })
})

describe('the bands', () => {
  it('counts what an agent wrote, whatever kind it was', () => {
    const rows = [
      chat('a', { produced: { standups: 1 } }),
      chat('b', { produced: { skills: 2 } }),
      chat('d', { produced: { artifacts: 1 } }),
    ]
    for (const id of ['standup', 'skill', 'artifact'] as ChipId[]) {
      expect(applyChips(rows, [id]), id).toHaveLength(1)
    }
  })

  it('knows where a chat came from, not only what it left', () => {
    const rows = [
      chat('p', { marks: { prompt: 1 } }),
      chat('k', { marks: { 'kept-vision': 1 } }),
      chat('n'),
    ]
    expect(applyChips(rows, ['prompt']).map((r) => r.id)).toEqual(['p'])
    expect(applyChips(rows, ['kept']).map((r) => r.id)).toEqual(['k'])
  })

  it('puts every chip in a band', () => {
    expect(new Set(CHIPS.map((c) => c.band))).toEqual(new Set(['out', 'in', 'weight']))
  })
})
