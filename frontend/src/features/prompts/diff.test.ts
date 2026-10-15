import { describe, expect, it } from 'vitest'
import { diffStats, hunks, lineDiff } from './diff'

describe('lineDiff', () => {
  it('marks added and removed lines and keeps the rest', () => {
    const d = lineDiff('a\nb\nc\nd', 'a\nB\nc\nd\ne')
    expect(d.map((x) => `${x.type}:${x.text}`)).toEqual(['same:a', 'del:b', 'add:B', 'same:c', 'same:d', 'add:e'])
    expect(diffStats(d)).toEqual({ add: 2, del: 1 })
  })
  it('identical input is all same, and hunks are empty', () => {
    const d = lineDiff('x\ny', 'x\ny')
    expect(d.every((x) => x.type === 'same')).toBe(true)
    expect(hunks(d)).toEqual([])
  })
  it('hunks keep two lines of context around a change', () => {
    const before = Array.from({ length: 12 }, (_, i) => `l${i}`).join('\n')
    const after = before.replace('l6', 'L6')
    const h = hunks(lineDiff(before, after))
    expect(h).toHaveLength(1)
    expect(h[0].map((x) => x.text)).toEqual(['l4', 'l5', 'l6', 'L6', 'l7', 'l8'])
  })
})
