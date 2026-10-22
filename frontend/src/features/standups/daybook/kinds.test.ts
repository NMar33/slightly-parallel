import { describe, expect, it } from 'vitest'
import { groupByKind, splitKind } from './kinds'

describe('kinds', () => {
  it('takes the capitalised word before a colon as the kind', () => {
    expect(splitKind('New: a page for scans')).toEqual({ kind: 'New', text: 'a page for scans' })
    expect(splitKind('Docs: the guide')).toEqual({ kind: 'Docs', text: 'the guide' })
  })
  it('leaves an item without a kind as it is', () => {
    expect(splitKind('tk_12345678 moved to review')).toEqual({ kind: '', text: 'tk_12345678 moved to review' })
    expect(splitKind('At 10:00 it broke')).toEqual({ kind: '', text: 'At 10:00 it broke' })
  })
  it('groups in the prompt order, unknown kinds after, kindless last', () => {
    const g = groupByKind(['old item', 'Fixed: b', 'Docs: d', 'New: a', 'Fixed: c'])
    expect(g.map((x) => x.kind)).toEqual(['New', 'Fixed', 'Docs', ''])
    expect(g[1]!.items).toEqual(['b', 'c'])
  })
})
