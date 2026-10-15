import { describe, expect, it } from 'vitest'

import { leaves, parse, prune, remove, replace, splitAt, type Node } from './split'

describe('the split tree', () => {
  it('splits only the pane in focus: right, then that one down', () => {
    let t: Node = { id: 'a' }
    t = splitAt(t, 'a', 'b', 'row')
    t = splitAt(t, 'b', 'c', 'col')
    expect(t).toEqual({ dir: 'row', sizes: [0.5, 0.5], kids: [{ id: 'a' }, { dir: 'col', sizes: [0.5, 0.5], kids: [{ id: 'b' }, { id: 'c' }] }] })
    expect(leaves(t)).toEqual(['a', 'b', 'c'])
  })
  it('a split the same way is a sibling with half the share', () => {
    const t = splitAt(splitAt({ id: 'a' }, 'a', 'b', 'row'), 'b', 'c', 'row')
    expect(t).toEqual({ dir: 'row', kids: [{ id: 'a' }, { id: 'b' }, { id: 'c' }], sizes: [0.5, 0.25, 0.25] })
  })
  it('a closed terminal leaves, and a split of one becomes that one', () => {
    const t = splitAt(splitAt({ id: 'a' }, 'a', 'b', 'row'), 'b', 'c', 'col')
    expect(remove(t, 'c')).toEqual({ dir: 'row', sizes: [0.5, 0.5], kids: [{ id: 'a' }, { id: 'b' }] })
    expect(prune(t, new Set(['a']))).toEqual({ id: 'a' })
    expect(replace(t, 'b', 'z')).toMatchObject({ kids: [{ id: 'a' }, { kids: [{ id: 'z' }, { id: 'c' }] }] })
  })
  it('reads back what it wrote, and nothing else', () => {
    const t = splitAt({ id: 'a' }, 'a', 'b', 'col')
    expect(parse(JSON.parse(JSON.stringify(t)))).toEqual(t)
    expect(parse({ nonsense: 1 })).toBeNull()
  })
})
