import { describe, expect, it } from 'vitest'
import { NOTCH_PX, RowAccumulator, Scroller, sgrWheel, wheelPx } from './smoothScroll'

const H = 16.8

/** Run frames 16.7 ms apart until the glide stops (or `max` frames); the positions seen. */
function frames(s: Scroller, max = 60, t0 = 1000): number[] {
  const out: number[] = []
  for (let i = 0; i < max; i++) { const more = s.step(t0 + i * 16.7); out.push(s.pos); if (!more) break }
  return out
}

describe('wheelPx', () => {
  it('a touchpad delta is pixels and moves at once; a big pixel delta or a line delta is a notch', () => {
    expect(wheelPx({ deltaY: -3, deltaMode: 0 }, H, 34)).toEqual({ px: -3, notch: false })
    expect(wheelPx({ deltaY: NOTCH_PX - 1, deltaMode: 0 }, H, 34).notch).toBe(false)
    expect(wheelPx({ deltaY: -100, deltaMode: 0 }, H, 34)).toEqual({ px: -100, notch: true })
    expect(wheelPx({ deltaY: 3, deltaMode: 1 }, H, 34)).toEqual({ px: 3 * H, notch: true })
    expect(wheelPx({ deltaY: -1, deltaMode: 2 }, H, 34)).toEqual({ px: -H * 34, notch: true })
  })
})

describe('Scroller', () => {
  it('small deltas are never lost: the sum of the movement is the sum of the input, to the pixel', () => {
    const s = new Scroller()
    s.set(10_000, 50_000)
    const deltas = Array.from({ length: 500 }, (_, i) => -[2, 3, 5, 8, 4, 6, 0.5, 1.25][i % 8])
    for (const d of deltas) s.push(d, false)
    expect(s.pos).toBeCloseTo(10_000 + deltas.reduce((a, b) => a + b, 0), 6)
    expect(s.moving).toBe(false)
  })

  it('a finger moves the view in the same frame (no glide, no lag)', () => {
    const s = new Scroller()
    s.set(1000, 5000)
    s.push(-4, false)
    expect(s.pos).toBe(996)
    expect(s.step(0)).toBe(false)
  })

  it('a notch glides: it moves on every frame, never more than 40% of the notch in one, and arrives within 200 ms', () => {
    const s = new Scroller()
    s.set(1000, 5000)
    s.push(-100, true)
    const seen = frames(s)
    const steps = seen.map((p, i) => Math.abs(p - (i ? seen[i - 1] : 1000)))
    expect(seen[seen.length - 1]).toBe(900)
    expect(steps.every((d) => d > 0)).toBe(true)
    expect(Math.max(...steps)).toBeLessThanOrEqual(40)
    expect(seen.length).toBeGreaterThanOrEqual(4)
    expect(seen.length).toBeLessThanOrEqual(12)
  })

  it('notches in a row add up: the glide goes to the sum', () => {
    const s = new Scroller()
    s.set(2000, 5000)
    s.push(-100, true); s.step(0); s.push(-100, true)
    frames(s, 120, 20)
    expect(s.pos).toBe(1800)
  })

  it('the glide is the same on a 120 Hz screen: time, not frames', () => {
    const a = new Scroller(); a.set(1000, 5000); a.push(100, true)
    const b = new Scroller(); b.set(1000, 5000); b.push(100, true)
    for (let t = 0; t <= 50; t += 16.7) a.step(t)
    for (let t = 0; t <= 50; t += 8.35) b.step(t)
    expect(Math.abs(a.pos - b.pos)).toBeLessThan(8)
  })

  it('stops at the top and at the bottom, and a finger during a glide carries it', () => {
    const s = new Scroller()
    s.set(10, 100)
    s.push(-50, false)
    expect(s.pos).toBe(0)
    s.push(500, true)
    expect(s.target).toBe(100)
    s.step(0)
    const before = s.target
    s.push(-5, false)
    expect(s.target).toBeCloseTo(before - 5, 6)
  })

  it('splits the position into whole rows and the pixels into the next one, without float drift', () => {
    const s = new Scroller()
    s.set(3 * H, 1000)
    expect(s.split(H)).toEqual({ line: 3, frac: 0 })
    s.set(3 * H + 5, 1000)
    const { line, frac } = s.split(H)
    expect(line).toBe(3)
    expect(frac).toBeCloseTo(5, 6)
  })
})

describe('RowAccumulator', () => {
  it('adds small deltas into whole rows and keeps the rest', () => {
    const a = new RowAccumulator()
    const got = [-2, -3, -5, -8, -4, -6].map((d) => a.add(d, H))
    expect(got.reduce((x, y) => x + y, 0)).toBe(-1) // 28 px = 1 row and 11.2 px kept
    expect(a.add(-6, H)).toBe(-1)
  })

  it('a notch of six rows is six rows, not one', () => {
    expect(new RowAccumulator().add(100, H)).toBe(5)
    expect(new RowAccumulator().add(6 * H, H)).toBe(6)
  })

  it('a change of direction drops the rest', () => {
    const a = new RowAccumulator()
    expect(a.add(-10, H)).toBe(0)
    expect(a.add(10, H)).toBe(0)
    expect(a.add(7, H)).toBe(1)
  })
})

describe('sgrWheel', () => {
  it('writes the SGR wheel report xterm writes', () => {
    expect(sgrWheel(true, 3, 7)).toBe('\x1b[<64;3;7M')
    expect(sgrWheel(false, 0, 0)).toBe('\x1b[<65;1;1M')
  })
})
