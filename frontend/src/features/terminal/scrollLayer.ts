/**
 * Pixel-smooth scrolling over an xterm.js terminal (any version scrolls its
 * text by whole rows only).
 *
 * The page takes the wheel before xterm does (capture phase) whenever the
 * terminal shows its own history: the normal buffer, no program asking for
 * the mouse. The view's position is kept in pixels (smoothScroll.ts); xterm
 * is moved to the whole row (`scrollToLine`, drawn at once, not a frame
 * later), and `.xterm-screen` is shifted up by the pixels into the next row.
 * The gap that opens at the bottom (under a row) shows the next line of the
 * history in a "ghost row" drawn here with xterm's own CSS classes; it is
 * only a picture (no clicks, no selection on it).
 *
 * Everything inside `.xterm-screen` moves with the shift: the selection, the
 * cursor, search marks, link underlines. xterm maps the mouse with the
 * screen's getBoundingClientRect, which includes the shift, so a click lands
 * on the row under the pointer.
 *
 * Any other move of the view (new output at the bottom, typing, a search
 * jump, the scrollbar, a resize) snaps the position back to xterm's row.
 */

import type { IBufferCell, IBufferLine, Terminal } from 'xterm'
import { Scroller, wheelPx } from './smoothScroll'

export interface SmoothLayer {
  /** A wheel event the layer may take: true when it did (the caller stops it). */
  wheel: (e: WheelEvent) => boolean
  /** Whether the layer would take a wheel now (normal buffer, no mouse reporting). */
  owns: () => boolean
  /** Snap the position to where xterm stands. */
  resync: () => void
  /** Scroll to the very bottom smoothly-free (instant). */
  bottom: () => void
  /** The view's position in pixels from the top and the bottom's (for tests and the reader). */
  where: () => { pos: number; target: number; max: number; rowH: number }
  /** Put the view at `px` from the top, at once (the reader's swap). */
  setPos: (px: number) => void
  /** Move by `px`: at once (a finger) or gliding (a notch, PageUp). */
  by: (px: number, glide: boolean) => void
  /** The view stands at the newest line (and is not gliding away from it). */
  atBottom: () => boolean
  dispose: () => void
}

type Core = { _core?: { _renderService?: { _renderDebouncer?: { _animationFrame?: number; _innerRefresh?: () => void } } } }

/** Draw xterm's pending rows now, not in its next animation frame: the rows
 *  and the shift must reach the screen in the same frame. Private xterm 5.x
 *  internals, looked up defensively: without them the rows come a frame late. */
function drawNow(t: Terminal) {
  const d = (t as unknown as Core)._core?._renderService?._renderDebouncer
  if (!d || typeof d._innerRefresh !== 'function' || d._animationFrame === undefined) return
  try {
    cancelAnimationFrame(d._animationFrame)
    d._innerRefresh()
  } catch { /* drawn in its own frame then */ }
}

type ViewportCore = { _core?: { viewport?: { _innerRefresh?: () => void; syncScrollArea?: (immediate?: boolean) => void; _refreshAnimationFrame?: number | null } } }

/**
 * Dispose an xterm that may have an animation frame of its own pending.
 *
 * xterm 5.3's Viewport asks for a frame after every scroll (syncScrollArea,
 * _innerRefresh) and does not cancel it on dispose: a reader closed in the
 * frame it scrolled in (the wheel down at the newest line, a key, the swap to
 * the longer history) ran that frame on a disposed renderer — "Cannot read
 * properties of undefined (reading 'dimensions')" (tk_988aeb37, found by the
 * terminal log). The pending frame is cancelled and the instance's two
 * callbacks become no-ops before the dispose, so a frame already queued finds
 * nothing to do. Private internals, looked up defensively.
 */
export function disposeTerminal(t: Terminal): void {
  const v = (t as unknown as ViewportCore)._core?.viewport
  if (v) {
    try {
      if (typeof v._refreshAnimationFrame === 'number') cancelAnimationFrame(v._refreshAnimationFrame)
      v._refreshAnimationFrame = null
      v._innerRefresh = () => {}
      v.syncScrollArea = () => {}
    } catch { /* a newer xterm: its own dispose then */ }
  }
  try { t.dispose() } catch { /* disposed already */ }
}

export function attachSmoothLayer(t: Terminal, opts: { onMove?: (fromBottom: number) => void } = {}): SmoothLayer {
  const el = t.element!
  const screen = el.querySelector('.xterm-screen') as HTMLElement
  const s = new Scroller()
  let raf = 0
  let own = false
  let shift = 0
  let disposed = false

  const ghost = document.createElement('div')
  // Not class xterm-rows (selectors count xterm's rows by it): its font copied instead.
  ghost.className = 'sp-ghost-row'
  ghost.setAttribute('aria-hidden', 'true')
  Object.assign(ghost.style, { position: 'absolute', left: '0', pointerEvents: 'none', display: 'none', zIndex: '0' })
  screen.appendChild(ghost)
  let ghostLine = -1

  const rowH = () => (t.rows > 0 ? screen.clientHeight / t.rows : 0)
  const maxPx = () => t.buffer.active.baseY * rowH()

  const drawGhost = (line: number) => {
    const b = t.buffer.active
    const l = b.getLine(line)
    const h = rowH()
    ghost.style.top = `${t.rows * h}px`
    ghost.style.height = `${h}px`
    ghost.style.width = `${screen.clientWidth}px`
    const rowsEl = screen.querySelector('.xterm-rows') as HTMLElement | null
    if (rowsEl) {
      const cs = getComputedStyle(rowsEl)
      Object.assign(ghost.style, { fontFamily: cs.fontFamily, fontSize: cs.fontSize, color: cs.color, whiteSpace: 'pre', fontKerning: 'none' })
    }
    ghost.replaceChildren(l ? lineDom(l, t.cols, screen.clientWidth / t.cols, h) : document.createElement('div'))
    ghostLine = line
  }

  const setShift = (raw: number, line: number) => {
    // Whole device pixels: a shift between two blurs the text (scale 2.5: steps of 0.4 px).
    const dpr = window.devicePixelRatio || 1
    const px = Math.round(raw * dpr) / dpr
    shift = px
    if (px <= 0) {
      screen.style.transform = ''
      screen.style.clipPath = ''
      ghost.style.display = 'none'
      return
    }
    const H = t.rows * rowH()
    screen.style.transform = `translateY(${-px}px)`
    screen.style.clipPath = `polygon(0 ${px}px, 100% ${px}px, 100% ${H + px}px, 0 ${H + px}px)`
    const next = line + t.rows
    if (next !== ghostLine || ghost.style.display === 'none') drawGhost(next)
    ghost.style.display = 'block'
  }

  /** Show `s.pos`: xterm at the whole row, the screen shifted by the rest. */
  const apply = () => {
    const b = t.buffer.active
    const h = rowH()
    let { line, frac } = s.split(h)
    if (line >= b.baseY) { line = b.baseY; frac = 0 }
    if (b.viewportY !== line) {
      own = true
      try { t.scrollToLine(line) } finally { own = false }
      drawNow(t)
    }
    setShift(frac, line)
    opts.onMove?.(s.max - s.pos)
  }

  const tick = (now: number) => {
    raf = 0
    if (disposed) return
    const more = s.step(now)
    apply()
    if (more) raf = requestAnimationFrame(tick)
  }

  const resync = () => {
    if (disposed) return
    const b = t.buffer.active
    s.set(b.viewportY * rowH(), maxPx())
    if (raf) { cancelAnimationFrame(raf); raf = 0 }
    setShift(0, b.viewportY)
  }

  const owns = () => t.buffer.active.type === 'normal' && t.modes.mouseTrackingMode === 'none'

  const wheel = (e: WheelEvent): boolean => {
    if (disposed || !owns() || e.deltaY === 0 || e.shiftKey || e.ctrlKey) return false
    const h = rowH()
    if (h <= 0) return false
    // xterm may have moved since (output, a search): start from where it stands.
    // (A trimmed history moves xterm's row without telling.)
    const b = t.buffer.active
    if (!s.moving && Math.min(s.split(h).line, b.baseY) !== b.viewportY) s.set(b.viewportY * h, maxPx())
    else s.max = maxPx()
    const { px, notch } = wheelPx(e, h, t.rows)
    s.push(px * (t.options.scrollSensitivity ?? 1), notch)
    if (notch) { if (!raf) raf = requestAnimationFrame(tick) } else apply()
    return true
  }

  const subs = [
    // A move that is not the layer's own: snap to it. One that leaves xterm on
    // the row already shown (its viewport catching up, a swap) keeps the pixels.
    t.onScroll(() => {
      if (own) return
      const b = t.buffer.active
      if (b.viewportY === Math.min(s.split(rowH()).line, b.baseY) && b.viewportY < b.baseY) { s.max = maxPx(); return }
      resync()
    }),
    t.onResize(() => resync()),
    // The rows changed under a shifted view (output, a redraw): the ghost follows.
    t.onRender(() => { if (shift > 0 && ghostLine >= 0) drawGhost(ghostLine) }),
  ]
  s.set(t.buffer.active.viewportY * rowH(), maxPx())

  return {
    wheel, owns, resync,
    bottom: () => { t.scrollToBottom(); resync() },
    where: () => ({ pos: s.pos, target: s.target, max: s.max, rowH: rowH() }),
    setPos: (px: number) => {
      s.set(px, maxPx())
      apply()
    },
    by: (px: number, glide: boolean) => {
      s.max = maxPx()
      s.push(px, glide)
      if (glide) { if (!raf) raf = requestAnimationFrame(tick) } else apply()
    },
    atBottom: () => s.target >= maxPx() - 0.5,
    dispose: () => {
      disposed = true
      if (raf) cancelAnimationFrame(raf)
      for (const d of subs) d.dispose()
      screen.style.transform = ''
      screen.style.clipPath = ''
      ghost.remove()
    },
  }
}

/* ------------------------------------------------------------ the ghost row */

const INVERTED_DEFAULT = 257

/** One buffer line as xterm's DOM renderer would draw it, near enough for a
 *  row that is visible only in part while it scrolls in: xterm's own classes
 *  (palette colours, bold, italic, dim, underline), true colour inline, every
 *  cell its exact width so the columns line up with the rows above. */
export function lineDom(line: IBufferLine, cols: number, cellW: number, h: number): HTMLElement {
  const row = document.createElement('div')
  Object.assign(row.style, { width: `${cols * cellW}px`, height: `${h}px`, lineHeight: `${h}px`, overflow: 'hidden' })
  let cell: IBufferCell | undefined
  let run: HTMLSpanElement | null = null
  let runKey = ''
  let runCells = 0
  const close = () => { if (run) run.style.width = `${runCells * cellW}px` }
  for (let x = 0; x < cols; x++) {
    cell = line.getCell(x, cell)
    if (!cell) break
    const w = cell.getWidth()
    if (w === 0) continue
    const chars = cell.getChars() || ' '
    const { cls, style } = cellLook(cell)
    const key = `${cls}|${style}`
    // Wide characters get a span of their own: their glyph's advance is not the font's.
    if (!run || key !== runKey || w !== 1 || chars.length !== 1 || chars.charCodeAt(0) > 0x7e) {
      close()
      run = document.createElement('span')
      run.style.display = 'inline-block'
      run.style.height = '100%'
      run.style.verticalAlign = 'top'
      if (cls) run.className = cls
      if (style) run.style.cssText += style
      run.textContent = ''
      runKey = w === 1 && chars.length === 1 && chars.charCodeAt(0) <= 0x7e ? key : `!${x}`
      runCells = 0
      row.appendChild(run)
    }
    run.textContent += chars
    runCells += w
  }
  close()
  return row
}

function cellLook(c: IBufferCell): { cls: string; style: string } {
  const cls: string[] = []
  let style = ''
  const inverse = !!c.isInverse()
  let fgPal = c.isFgPalette() ? c.getFgColor() : -1
  const bgPal = c.isBgPalette() ? c.getBgColor() : -1
  if (c.isBold()) { cls.push('xterm-bold'); if (fgPal >= 0 && fgPal < 8) fgPal += 8 }
  if (c.isItalic()) cls.push('xterm-italic')
  if (c.isDim()) cls.push('xterm-dim')
  if (c.isUnderline()) cls.push('xterm-underline-1')
  if (c.isStrikethrough()) cls.push('xterm-strikethrough')
  const hex = (n: number) => `#${(n >>> 0).toString(16).padStart(6, '0')}`
  const fg = fgPal >= 0 ? { cls: `xterm-fg-${fgPal}` } : c.isFgRGB() ? { css: hex(c.getFgColor()) } : null
  const bg = bgPal >= 0 ? { cls: `xterm-bg-${bgPal}` } : c.isBgRGB() ? { css: hex(c.getBgColor()) } : null
  if (!inverse) {
    if (fg?.cls) cls.push(fg.cls); else if (fg?.css) style += `color:${fg.css};`
    if (bg?.cls) cls.push(bg.cls); else if (bg?.css) style += `background-color:${bg.css};`
  } else {
    // Inverse: the colours trade places (the default ones by xterm's own class).
    if (fg?.cls) cls.push(fg.cls.replace('fg', 'bg')); else if (fg?.css) style += `background-color:${fg.css};`; else cls.push(`xterm-bg-${INVERTED_DEFAULT}`)
    if (bg?.cls) cls.push(bg.cls.replace('bg', 'fg')); else if (bg?.css) style += `color:${bg.css};`; else cls.push(`xterm-fg-${INVERTED_DEFAULT}`)
  }
  if (c.isInvisible()) style += 'visibility:hidden;'
  return { cls: cls.join(' '), style }
}
