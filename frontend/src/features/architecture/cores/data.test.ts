import { describe, expect, it } from 'vitest'

import { coreColor, shownNote, weeksOf, type GridDay } from './data'

const days = (n: number, from = '2026-10-01'): GridDay[] => {
  const start = new Date(`${from}T00:00:00`)
  return Array.from({ length: n }, (_, i) => {
    const d = new Date(start); d.setDate(start.getDate() + i)
    const day = `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`
    return { day, story: 0, nearby: 0 }
  })
}

describe('weeksOf', () => {
  it('lays 30 days out as weeks, Monday on top, blank before the first day', () => {
    // 2026-10-01 is a Thursday: three blank cells, then the days, padded to full weeks.
    const weeks = weeksOf(days(30))
    expect(weeks).toHaveLength(5)
    expect(weeks[0]!.slice(0, 3)).toEqual([null, null, null])
    expect(weeks[0]![3]!.day).toBe('2026-10-01')
    expect(weeks.flat().filter(Boolean)).toHaveLength(30)
    expect(weeks.every((w) => w.length === 7)).toBe(true)
  })
  it('is empty for no days', () => { expect(weeksOf([])).toEqual([]) })
})

describe('shownNote', () => {
  const notes = [
    { id: 'a', author: 'operator', approved: true },
    { id: 'b', author: 'cc-x', approved: false },
  ]
  it('shows the latest of all, or the latest the operator wrote or approved', () => {
    expect(shownNote(notes, false)?.id).toBe('b')
    expect(shownNote(notes, true)?.id).toBe('a')
    expect(shownNote([], true)).toBeNull()
  })
})

describe('coreColor', () => {
  it('names the type token, and falls back for a type it does not know', () => {
    expect(coreColor('feature')).toBe('var(--core-feature)')
    expect(coreColor('whatever')).toBe('var(--core-internals)')
  })
})
