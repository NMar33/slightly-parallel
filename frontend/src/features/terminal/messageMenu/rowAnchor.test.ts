import { act, renderHook } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import type { Terminal } from 'xterm'

import { Scroller } from '../smoothScroll'
import { rowTop, useView, type View } from './rowAnchor'

/**
 * A mark (a pin's, a command's copy icon) on buffer line `abs` sits inside
 * `.xterm-screen`, which the smooth scroll shifts up by `frac` pixels while
 * xterm stands on whole row `line` (scrollLayer.ts). On the screen it is at
 * rowTop − frac; its text is at abs·h − pos. They must be the same on every
 * frame of a glide (tk_49c10a34: the pin mark lagged behind its row).
 */
describe('a mark on a row during a smooth scroll', () => {
  const h = 16.8, rows = 30, abs = 120

  function glide(placeBy: (line: number, first: number) => number) {
    const s = new Scroller()
    s.set(100 * h, 1000 * h)
    const first = s.split(h).line
    s.push(5.5 * h, true)
    const off: number[] = []
    for (let now = 0, more = true; more; now += 1000 / 60) {
      more = s.step(now)
      const { line, frac } = s.split(h)
      const top = rowTop(abs, { viewportY: placeBy(line, first), rows, cell: h })
      if (top == null) continue
      off.push(Math.abs(top - frac - (abs * h - s.pos)))
    }
    return off
  }

  it('placed by its line in the buffer and xterm\'s row now: on its text on every frame', () => {
    const off = glide((line) => line)
    expect(off.length).toBeGreaterThan(5)
    expect(Math.max(...off)).toBeLessThan(1e-6)
  })

  it('placed by the row it had when it was last read (the old way): a whole row off once xterm moved', () => {
    const off = glide((_line, first) => first)
    expect(Math.max(...off)).toBeGreaterThan(h - 0.01)
  })

  it('off the screen: no place', () => {
    const v: View = { viewportY: 10, rows: 5, cell: 20 }
    expect(rowTop(9, v)).toBeNull()
    expect(rowTop(15, v)).toBeNull()
    expect(rowTop(12, v)).toBe(40)
  })
})

/** A terminal with the events the hook listens to, scrolled by hand. */
function fakeTerm() {
  const fire: Array<() => void> = []
  const ev = () => (cb: () => void) => { fire.push(cb); return { dispose: () => { fire.splice(fire.indexOf(cb), 1) } } }
  const screen = document.createElement('div')
  screen.className = 'xterm-screen'
  Object.defineProperty(screen, 'clientHeight', { value: 300 })
  const element = document.createElement('div')
  element.appendChild(screen)
  const t = {
    element, rows: 20,
    buffer: { active: { viewportY: 0 }, onBufferChange: ev() },
    onScroll: ev(), onResize: ev(), onRender: ev(),
  }
  return { term: t as unknown as Terminal, scroll: (y: number) => { t.buffer.active.viewportY = y; for (const f of [...fire]) f() }, listeners: () => fire.length }
}

describe('useView', () => {
  it('follows xterm\'s row the moment xterm moves, rendered at once (not in a later task, after the frame)', () => {
    const f = fakeTerm()
    const { result, unmount } = renderHook(() => useView(f.term))
    expect(result.current).toEqual({ viewportY: 0, rows: 20, cell: 15 })
    // Outside act, as in the browser: what xterm's own event set must already be rendered when it returns.
    const g = globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }
    const was = g.IS_REACT_ACT_ENVIRONMENT
    g.IS_REACT_ACT_ENVIRONMENT = false
    try { f.scroll(7) } finally { g.IS_REACT_ACT_ENVIRONMENT = was }
    expect(result.current?.viewportY).toBe(7)
    act(() => f.scroll(9))
    expect(result.current?.viewportY).toBe(9)
    unmount()
    expect(f.listeners()).toBe(0)
  })
})
