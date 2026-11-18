/**
 * Smooth scrolling: the arithmetic, no DOM (unit-tested in smoothScroll.test.ts).
 *
 * xterm.js moves its view in whole rows (every version, 6.x too:
 * `Math.round(scrollTop / rowHeight)`). A touchpad sends many small deltas
 * (2–8 px), so the text stood still for several frames and then jumped a
 * row. Here the view has a position in pixels: a touchpad's delta moves it
 * by exactly that many pixels at once (no lag, nothing lost), a mouse notch
 * (a line or page delta, or a big pixel one) glides there in about 100 ms.
 * scrollLayer.ts shows the position: xterm's rows for the whole part, a CSS
 * shift for the rest.
 */

export const DOM_DELTA_PIXEL = 0
export const DOM_DELTA_LINE = 1
export const DOM_DELTA_PAGE = 2

/** A pixel delta this big in one event is a notch of a mouse wheel, not a finger. */
export const NOTCH_PX = 50
/** A notch glides: the distance left shrinks by e every TAU ms (most of the way in 100 ms, all of it in under 200). */
export const TAU_MS = 36

export interface WheelLike { deltaY: number; deltaMode: number }

/** The wheel event in pixels, and whether it is a notch (glides) or a finger (moves at once). */
export function wheelPx(e: WheelLike, rowH: number, rows: number): { px: number; notch: boolean } {
  if (e.deltaMode === DOM_DELTA_LINE) return { px: e.deltaY * rowH, notch: true }
  if (e.deltaMode === DOM_DELTA_PAGE) return { px: e.deltaY * rowH * rows, notch: true }
  return { px: e.deltaY, notch: Math.abs(e.deltaY) >= NOTCH_PX }
}

/**
 * The view's position in pixels from the top of the history, 0..max.
 * `pos` is what is shown, `target` where a gliding notch is going.
 */
export class Scroller {
  pos = 0
  target = 0
  max = 0
  private last = -1

  /** Put the view somewhere (a resync after xterm moved it itself): no glide. */
  set(pos: number, max: number): void {
    this.max = Math.max(0, max)
    this.pos = this.target = clamp(pos, 0, this.max)
    this.last = -1
  }

  /** A wheel event, in pixels. A finger moves the view now; a notch moves the target. */
  push(px: number, notch: boolean): void {
    if (notch) {
      this.target = clamp(this.target + px, 0, this.max)
      return
    }
    // A finger during a glide carries the glide along: both move by the delta.
    const next = clamp(this.pos + px, 0, this.max)
    const moved = next - this.pos
    this.pos = next
    this.target = clamp(this.target + moved, 0, this.max)
  }

  get moving(): boolean { return Math.abs(this.target - this.pos) > 0.01 }

  /** One animation frame at time `now` (ms): the glide's next step. True while still gliding. */
  step(now: number): boolean {
    if (!this.moving) { this.pos = this.target; this.last = -1; return false }
    const dt = this.last < 0 ? 1000 / 60 : Math.min(100, Math.max(0, now - this.last))
    this.last = now
    const left = this.target - this.pos
    const next = left * Math.exp(-dt / TAU_MS)
    // The last half pixel lands at once: no endless creep.
    this.pos = Math.abs(next) < 0.5 ? this.target : this.target - next
    if (!this.moving) { this.last = -1; return false }
    return true
  }

  /** The view as whole rows and the pixels into the next one: line = floor(pos/rowH). */
  split(rowH: number): { line: number; frac: number } {
    if (rowH <= 0) return { line: 0, frac: 0 }
    // Floating point: 3 rows of 16.8 px must be line 3, not 2.9999.
    const exact = this.pos / rowH
    const line = Math.floor(exact + 1e-6)
    const frac = Math.max(0, this.pos - line * rowH)
    return { line, frac: frac < 0.01 ? 0 : frac }
  }
}

/**
 * Pixels in, whole rows out, the rest kept for the next event: for what can
 * only move by rows (arrow keys to a full-screen app, wheel reports to an
 * app that reads the mouse). Small deltas add up instead of being dropped,
 * and a notch of six rows sends six, not one.
 */
export class RowAccumulator {
  private rest = 0
  /** Rows to send for this delta: negative up, positive down. */
  add(px: number, rowH: number): number {
    if (rowH <= 0) return 0
    // A change of direction starts afresh: half a row up does not eat a row down.
    if (this.rest !== 0 && Math.sign(this.rest) !== Math.sign(px)) this.rest = 0
    this.rest += px / rowH
    const rows = Math.trunc(this.rest + (this.rest > 0 ? 1e-6 : -1e-6)) || 0
    this.rest -= rows
    return rows
  }
  reset(): void { this.rest = 0 }
}

export const clamp = (x: number, lo: number, hi: number) => Math.min(hi, Math.max(lo, x))

/** An SGR mouse wheel report at cell (col, row), 1-based: what xterm sends for one wheel step. */
export function sgrWheel(up: boolean, col: number, row: number): string {
  return `\x1b[<${up ? 64 : 65};${Math.max(1, col)};${Math.max(1, row)}M`
}

/** Smooth scrolling on? The setting, unless the address says `scroll=rows` or
 *  `scroll=smooth` (to compare the two in one window, and the e2e suite). */
export function smoothOn(setting: boolean | undefined, search = typeof window === 'undefined' ? '' : window.location.search): boolean {
  const q = new URLSearchParams(search).get('scroll')
  if (q === 'rows') return false
  if (q === 'smooth') return true
  return setting ?? true
}
