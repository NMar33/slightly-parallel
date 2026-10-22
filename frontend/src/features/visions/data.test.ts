import { describe, expect, it, vi } from 'vitest'

import { cleanTitle, dateOf, firstLoad, normaliseTags, settled, taskIds, visionText, type Vision } from './data'
import { stamp, whoOf } from './time'

describe('tags', () => {
  it('trims, lowercases, hyphenates and dedupes', () => {
    expect(normaliseTags('UI, backend ,ui, Design rounds,,')).toEqual(['ui', 'backend', 'design-rounds'])
    expect(normaliseTags('')).toEqual([])
  })
})

describe('dates', () => {
  it('reads YYMM-DD and HH:MM', () => {
    const d = dateOf({ created_date: '2609-16', created_time: '19:50' })
    expect([d.getFullYear(), d.getMonth(), d.getDate(), d.getHours(), d.getMinutes()]).toEqual([2026, 8, 16, 19, 50])
    expect(dateOf({ created_date: '2609-16', created_time: '' }).getHours()).toBe(0)
  })
  it("prints a stamp the page's way", () => {
    expect(stamp('2609-14 13:40')).toBe('14 Sep, 13:40')
    expect(stamp('2609-14')).toBe('14 Sep')
    expect(stamp('2026-09-14T13:40:00')).toBe('14 Sep, 13:40')
    expect(stamp('later')).toBe('later')
  })
  it('reads a zoned stamp in local time, day and hour together', () => {
    vi.stubEnv('TZ', 'Australia/Sydney')
    try {
      // 23:30 UTC on 30 Sep is 09:30 on 1 Oct in Sydney (UTC+10 until 4 Oct).
      expect(stamp('2026-09-30T23:30:00Z')).toBe('1 Oct, 09:30')
      expect(stamp('2026-09-30T23:30:00+00:00')).toBe('1 Oct, 09:30')
      // Without a zone the stamp is local already.
      expect(stamp('2026-09-30T23:30:00.250')).toBe('30 Sep, 23:30')
    } finally {
      vi.unstubAllEnvs()
    }
  })
  it('names who wrote a version', () => {
    expect(whoOf({ how: 'edited' })).toBe('you')
    expect(whoOf({ how: 'interpreted' })).toBe('agent')
  })
})

describe('titles and tasks', () => {
  it('drops the list number and the task id a message opens with', () => {
    expect(cleanTitle('3. tk_28b1b490.2 · Make the sidebar narrower')).toBe('Make the sidebar narrower')
    expect(cleanTitle('')).toBe('')
  })
  it('finds task ids with or without a round', () => {
    expect(taskIds('see tk_28b1b490.2 and tk_abc123, tk_abc123 again')).toEqual(['tk_28b1b490', 'tk_abc123'])
  })
  it('copies the interpretation, then the words it came from', () => {
    const v: Vision = {
      row: { id: 'vs_1', created_date: '2609-16', created_time: '10:00', project: 'p', agent_id: 'a', l1: 'One thing', source: 'captured', session_id: null, source_turn: 1, versions_n: 1, tags: null },
      l2: 'What it means.',
      kept: { kind: 'vision', message: 'line one\nline two', turn: null, before: [], after: [], versions: [], current: null },
    }
    expect(visionText(v)).toBe("## One thing\n\nWhat it means.\n\nIn the operator's words:\n\n> line one\n> line two\n")
  })
})

describe('first load — the only time a page shows a skeleton', () => {
  const q = (data: unknown, isError = false) => ({ data, isError })
  it('is loading while the list loads, or while no detail has arrived', () => {
    expect(firstLoad(true, [])).toBe(true)
    expect(firstLoad(false, [q(undefined), q(undefined)])).toBe(true)
  })
  it('stays up once one detail is here, whatever the others do', () => {
    expect(firstLoad(false, [q({ id: 1 }), q(undefined)])).toBe(false)
    expect(firstLoad(false, [q(undefined, true), q(undefined)])).toBe(false)
    expect(firstLoad(false, [])).toBe(false)
  })
  it('draws a detail that arrived or failed, and waits for one still on its way', () => {
    expect(settled(q({ id: 1 }))).toBe(true)
    expect(settled(q(undefined, true))).toBe(true)
    expect(settled(q(undefined))).toBe(false)
  })
})
