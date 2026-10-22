import { describe, expect, it } from 'vitest'

import { PRESETS, SECTIONS } from './library'
import { bySection } from './sections'
import type { Script } from './script'

describe('the presets by section', () => {
  it('files every preset once, under its own section', () => {
    const groups = bySection(PRESETS)
    expect(groups.flatMap((g) => g.scripts.map((s) => s.id)).sort()).toEqual(PRESETS.map((s) => s.id).sort())
    for (const g of groups) for (const s of g.scripts) expect(s.section).toBe(g.name)
  })

  it('keeps the sections in reading order, each named once', () => {
    const names = bySection(PRESETS).map((g) => g.name)
    expect(names).toEqual(Object.values(SECTIONS).filter((n) => names.includes(n)))
    expect(new Set(names).size).toBe(names.length)
  })

  it('keeps the library order inside a section and joins a section that comes back', () => {
    const s = (id: string, section?: string) => ({ id, section }) as Script
    const groups = bySection([s('a', 'One'), s('b', 'Two'), s('c', 'One'), s('d')])
    expect(groups.map((g) => [g.name, g.scripts.map((x) => x.id)])).toEqual([
      ['One', ['a', 'c']], ['Two', ['b']], ['', ['d']],
    ])
  })
})
