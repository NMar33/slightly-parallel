import { afterEach, describe, expect, it, vi } from 'vitest'
import type { Terminal } from 'xterm'
import { disposeTerminal } from './scrollLayer'

/**
 * xterm 5.3's Viewport asks for an animation frame after a scroll and does
 * not cancel it on dispose: the frame then read the disposed renderer's
 * dimensions and threw (tk_988aeb37). A stand-in with xterm's own shape: a
 * frame queued by `_refresh`, a renderer gone after dispose.
 */
function fakeTerm() {
  const frames: Array<() => void> = []
  vi.stubGlobal('requestAnimationFrame', (f: () => void) => frames.push(f))
  vi.stubGlobal('cancelAnimationFrame', (id: number) => { frames[id - 1] = () => {} })
  const renderer: { value?: { dimensions: { css: { cell: { height: number } } } } } = { value: { dimensions: { css: { cell: { height: 17 } } } } }
  const viewport = {
    _refreshAnimationFrame: null as number | null,
    _innerRefresh() { void renderer.value!.dimensions.css.cell.height; this._refreshAnimationFrame = null },
    syncScrollArea() { if (this._refreshAnimationFrame === null) this._refreshAnimationFrame = requestAnimationFrame(() => this._innerRefresh()) },
  }
  const t = { _core: { viewport }, dispose: vi.fn(() => { renderer.value = undefined }) }
  return { t: t as unknown as Terminal & typeof t, viewport, frames, run: () => { for (const f of frames.splice(0)) f() } }
}

describe('disposeTerminal', () => {
  afterEach(() => vi.unstubAllGlobals())

  it('a frame xterm queued before the dispose finds nothing to do', () => {
    const { t, viewport, run } = fakeTerm()
    viewport.syncScrollArea()                 // a scroll: one frame queued
    t.dispose()
    expect(run).toThrow(/dimensions/)         // what plain dispose left behind

    const b = fakeTerm()
    b.viewport.syncScrollArea()
    const queued = [...b.frames]
    disposeTerminal(b.t)
    expect(b.t.dispose).toHaveBeenCalledOnce()
    expect(() => { for (const f of queued) f() }).not.toThrow()
    expect(() => b.viewport.syncScrollArea()).not.toThrow()
  })

  it('a terminal without those internals is still disposed, once', () => {
    const t = { dispose: vi.fn() }
    disposeTerminal(t as unknown as Terminal)
    expect(t.dispose).toHaveBeenCalledOnce()
  })
})
