import { describe, it, expect } from 'vitest'
import { routeLinks, sameColumn, type Box } from './linkRoutes'
import { glowOf, linkGraph, type LinkKind, type TaskLink } from './model'

const L = (from: string, to: string, kind: LinkKind = 'relates', id = `${from}-${to}-${kind}`): TaskLink => ({
  id, from_id: from, to_id: to, kind, from: { id: from }, to: { id: to },
})
// Two columns, 200 wide, 20 apart; cards 60 tall.
const box = (col: number, row: number): Box => ({ left: col * 220, right: col * 220 + 200, top: row * 80, bottom: row * 80 + 60 })
const bounds = { left: -40, right: 1000 }
const nums = (d: string) => d.match(/-?\d+(\.\d+)?/g)!.map(Number)

describe('routeLinks', () => {
  it('joins cards in different columns right side to left side', () => {
    const [r] = routeLinks([L('a', 'b')], new Map([['a', box(0, 0)], ['b', box(1, 2)]]), bounds)
    const p = nums(r!.d)
    expect(p[0]).toBe(200) // leaves a's right edge
    expect(p.at(-2)).toBe(220) // lands on b's left edge
  })

  it('keeps both ends on one side for cards in one column', () => {
    const boxes = new Map([['a', box(0, 0)], ['b', box(0, 3)]])
    expect(sameColumn(boxes.get('a')!, boxes.get('b')!)).toBe(true)
    const [r] = routeLinks([L('a', 'b')], boxes, bounds)
    const p = nums(r!.d)
    expect(p[0]).toBe(200)
    expect(p.at(-2)).toBe(200)
    expect(p[2]).toBeGreaterThan(200) // bulges out to the right, not through the cards
  })

  it('puts a one-column bracket on the emptier side, and on the left at the board edge', () => {
    // a already sends a line to the right (to c); the a–b bracket goes left.
    const boxes = new Map([['a', box(1, 0)], ['b', box(1, 2)], ['c', box(2, 0)]])
    const rs = routeLinks([L('a', 'c'), L('a', 'b')], boxes, bounds)
    expect(nums(rs.find((r) => r.to_id === 'b')!.d)[0]).toBe(220)
    // Rightmost column with no room to the right → left.
    const edge = routeLinks([L('a', 'b')], new Map([['a', box(0, 0)], ['b', box(0, 2)]]), { left: -40, right: 210 })
    expect(nums(edge[0]!.d)[0]).toBe(0)
  })

  it('gives each line on one side its own port, ordered by where it goes', () => {
    const boxes = new Map([['a', box(0, 1)], ['up', box(1, 0)], ['down', box(1, 2)]])
    const rs = routeLinks([L('a', 'down'), L('a', 'up')], boxes, bounds)
    const yUp = nums(rs.find((r) => r.to_id === 'up')!.d)[1]!
    const yDown = nums(rs.find((r) => r.to_id === 'down')!.d)[1]!
    expect(yUp).toBeLessThan(yDown)
    // Two links between one pair are two lines.
    const two = routeLinks([L('a', 'up', 'relates'), L('a', 'up', 'blocks')], boxes, bounds)
    expect(two[0]!.d).not.toBe(two[1]!.d)
  })

  it('keeps a stub when the other card is not on the board', () => {
    const rs = routeLinks([L('a', 'gone'), L('gone2', 'a'), L('x', 'y')], new Map([['a', box(0, 0)]]), bounds)
    expect(rs.map((r) => r.missing)).toEqual(['to', 'from'])
  })
})

describe('linkGraph and glowOf', () => {
  const links = [L('a', 'b', 'blocks'), L('b', 'c', 'parent'), L('d', 'c'), L('x', 'y')]
  it('walks the whole graph both ways with distances', () => {
    const g = linkGraph(links, 'a')
    expect(Object.fromEntries(g)).toEqual({ a: 0, b: 1, c: 2, d: 3 })
  })
  it('lights direct links strong, the rest of the graph lighter, fades the others', () => {
    const g = linkGraph(links, 'b')
    expect(['a', 'b', 'c', 'd', 'x'].map((id) => glowOf(g, 'b', id))).toEqual(['direct', undefined, 'direct', 'near', 'off'])
    expect(glowOf(null, null, 'a')).toBeUndefined()
  })
})
