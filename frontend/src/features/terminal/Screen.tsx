/**
 * One terminal's screen: xterm on the socket /ws/terminal/{id}.
 *
 * - fits its box, whatever resizes it (the drawer's handle, a split, the
 *   window) — a ResizeObserver, not the window's resize;
 * - comes back on its own: a dropped socket reconnects (the terminal lives
 *   on in tmux), and says so in one grey line;
 * - copying just works: a tmux mouse-drag lands on the clipboard (tmux
 *   announces the copy, OSC 52, and the screen listens), Shift+drag makes
 *   a native selection, Ctrl+C with text selected copies, Ctrl+Shift+C/V
 *   are the classic pair, and the right-click menu needs no keys at all;
 * - a lot of text: "Select lines" opens a slim gutter — click a line, click
 *   another, everything between lands on the clipboard, joined out of its
 *   wrapping, however far apart the clicks were (the dots anchor to the
 *   history, not the screen — rangeMath.ts). "Copy the last output" takes
 *   everything since your last Enter in one click;
 * - find: Ctrl+Shift+F, a small box over the corner;
 * - kept mounted while hidden, so its scrollback survives switching tabs.
 */

import { useCallback, useEffect, useRef, useState } from 'react'
import { useQueryClient } from '@tanstack/react-query'
import type { Terminal } from 'xterm'
import type { SearchAddon } from 'xterm-addon-search'

import { toast } from 'sonner'

import { getJson, postJson } from '../../lib/getJson'
import { copyText } from '../../lib/useCopy'
import { absOf, relOf, rowOf, type PanePos } from './rangeMath'
import { findPaths, type PrintedPath } from './printedPaths'
import { setWork } from '../../lib/timer'
import { t as tr, tn } from '../../i18n/scope/system'
import { THEME } from './palette'
import { letter } from '../../lib/typing'
import { IS_MAC, pasteKey, pasteKeyName } from './pasteKeys'
import { attachSmoothLayer, type SmoothLayer } from './scrollLayer'
import { buildReader, fetchRows, FIRST_ROWS, readerKeeps, type Reader } from './reader'
import { RowAccumulator, sgrWheel, wheelPx } from './smoothScroll'

const INVALID_TOKEN = 4401
const OFF = 4409
const ENDED = 4000
/** Refusals a retry cannot change: a foreign page, a bad id, too many
 *  terminals, a shell that did not start (4500, the reason says why). */
const REFUSED = new Set([4400, 4403, 4429, 4500])

/** What the bar (and the right-click menu) can ask a screen to do. */
export interface ScreenApi {
  find: () => void
  range: () => void
  copyScreen: () => void
  copyLast: () => void
}

interface Dot { abs: number; rel: number }

export function Screen({ sid, token, fontSize = 13, scrollback = 10000, editor = '', visible = true, project = '', taskId = '', backend = 'tmux', smooth = true, onEnded, onFocus, autoFocus = true, onZoom, bind, onInput }: {
  sid: string
  token: string
  fontSize?: number
  visible?: boolean
  project?: string
  /** tmux terminals ask the server about their history; plain ones own it here. */
  backend?: 'tmux' | 'plain'
  /** The task the terminal was opened for: in focus, that is what you work on. */
  taskId?: string
  /** Lines a plain terminal keeps (a tmux one keeps its pane's own history). */
  scrollback?: number
  /** Scroll by pixels (Settings › Smooth scrolling); off: xterm's own whole rows. */
  smooth?: boolean
  /** The editor printed paths open in ("" = no links). */
  editor?: string
  onEnded?: () => void
  onFocus?: () => void
  /** Take the keyboard when shown (a wall of screens leaves it to a click). */
  autoFocus?: boolean
  /** Ctrl + / Ctrl − inside the terminal: the text a step bigger or smaller. */
  onZoom?: (delta: number) => void
  /** Hands the bar this screen's actions (find, select lines, …). */
  bind?: (api: ScreenApi | null) => void
  /** Told of each input that goes to the shell (a key, a paste), after it is sent; what is sent never changes. */
  onInput?: (data: string) => void
}) {
  const box = useRef<HTMLDivElement>(null)
  const fitRef = useRef<() => void>(() => {})
  const api = useRef<{ fit: () => void; focus: () => void; size: (n: number) => void } | null>(null)
  const termRef = useRef<Terminal | null>(null)
  const searchRef = useRef<SearchAddon | null>(null)
  const qc = useQueryClient()
  const onEndedRef = useRef(onEnded)
  const onFocusRef = useRef(onFocus)
  const workRef = useRef({ project, taskId })
  workRef.current = { project, taskId }
  const onZoomRef = useRef(onZoom)
  const onInputRef = useRef(onInput)
  onInputRef.current = onInput
  const visibleRef = useRef(visible)
  const smoothRef = useRef(smooth)
  smoothRef.current = smooth
  const layerRef = useRef<SmoothLayer | null>(null)
  /** tmux mode, scrolled up: the history in a reader over the live xterm (reader.ts). */
  const readerRef = useRef<Reader | null>(null)
  const [reading, setReading] = useState(false)
  const openReaderRef = useRef<(px: number, first?: WheelEvent, rows?: number) => void>(() => {})
  const closeReaderRef = useRef<() => void>(() => {})
  const autoFocusRef = useRef(autoFocus)
  const editorRef = useRef(editor)
  editorRef.current = editor
  const openPathRef = useRef<(p: PrintedPath) => void>(() => {})
  visibleRef.current = visible
  autoFocusRef.current = autoFocus
  useEffect(() => { onEndedRef.current = onEnded; onFocusRef.current = onFocus; onZoomRef.current = onZoom })

  /* ------------------------------------------------ copy, find, the gutter */

  const [menu, setMenu] = useState<{ x: number; y: number } | null>(null)
  const [find, setFind] = useState(false)
  const [range, setRange] = useState(false)
  const [pos, setPos] = useState<PanePos>({ history: 0, scroll: 0, rows: 24 })
  const [dot, setDot] = useState<Dot | null>(null)
  const [hoverRow, setHoverRow] = useState<number | null>(null)
  const [flash, setFlash] = useState<{ a: number; b: number } | null>(null)
  const [cellH, setCellH] = useState(0)
  /** Why the terminal could not start (xterm failed to load), or ''. */
  const [broken, setBroken] = useState('')
  const rangeRef = useRef(range); rangeRef.current = range
  const findRef = useRef(find); findRef.current = find
  const menuRef = useRef(menu); menuRef.current = menu
  /** A plain terminal's Enter stamp (a tmux one is stamped on the server). */
  const plainStamp = useRef<number | null>(null)

  /** Where the pane stands right now — the server for tmux, the buffer here for plain. */
  const readPos = useCallback(async (): Promise<PanePos> => {
    const r = readerRef.current
    if (r) {
      // The reader's rows are the pane's: its history above, then the screen.
      const rb = r.term.buffer.active
      return { history: r.history, scroll: rb.baseY - rb.viewportY, rows: r.term.rows }
    }
    if (backend === 'tmux') {
      const p = await getJson<PanePos & { cursor: number }>(`/api/terminal/sessions/${encodeURIComponent(sid)}/pos`)
      return { history: p.history, scroll: p.scroll, rows: p.rows }
    }
    const b = termRef.current?.buffer.active
    const t = termRef.current
    if (!b || !t) return { history: 0, scroll: 0, rows: 24 }
    return { history: b.viewportY + (b.baseY - b.viewportY), scroll: b.baseY - b.viewportY, rows: t.rows }
  }, [backend, sid])

  /** Rows a..b out of a plain terminal's own buffer, wrapped lines joined. */
  const plainSlice = (a: number, b: number): string => {
    const t = termRef.current
    const buf = t?.buffer.active
    if (!t || !buf) return ''
    const out: string[] = []
    for (let i = Math.max(0, a); i <= Math.min(b, buf.length - 1); i++) {
      const line = buf.getLine(i)
      if (!line) continue
      const s = line.translateToString(true)
      // A wrapped row continues the previous line: joined back, like tmux -J.
      if (out.length && line.isWrapped) out[out.length - 1] += s
      else out.push(s)
    }
    while (out.length && !out[out.length - 1]!.trim()) out.pop()
    return out.join('\n')
  }

  const copyRows = useCallback(async (a: number, b: number) => {
    const [lo, hi] = a <= b ? [a, b] : [b, a]
    if (backend === 'tmux') {
      // A refused capture is said; the gutter stays open for another try.
      const got = await postJson<{ text: string; lines: number; truncated: boolean }>(
        `/api/terminal/sessions/${encodeURIComponent(sid)}/capture`, { mode: 'range', from: lo, to: hi })
        .catch((e: Error) => { toast.error(tr('The lines could not be copied: {error}', { error: e.message })); return null })
      if (!got) return
      void copyText(got.text, `${tn(got.lines, 'Copied {n} line', 'Copied {n} lines')}${got.truncated ? tr(' (cut at 20 000)') : ''}`)
    } else {
      const text = plainSlice(lo, hi)
      void copyText(text, tn(text ? text.split('\n').length : 0, 'Copied {n} line', 'Copied {n} lines'))
    }
    setFlash({ a: lo, b: hi })
    setTimeout(() => { setFlash(null); setRange(false); setDot(null) }, 350)
  }, [backend, sid])

  const copyWhole = useCallback(async (mode: 'screen' | 'last') => {
    if (backend === 'tmux') {
      const got = await postJson<{ text: string; lines: number }>(
        `/api/terminal/sessions/${encodeURIComponent(sid)}/capture`, { mode })
        .catch((e: Error) => { toast.error(tr('The terminal could not be copied: {error}', { error: e.message })); return null })
      if (got) void copyText(got.text, tn(got.lines, 'Copied {n} line', 'Copied {n} lines'))
      return
    }
    const p = await readPos()
    const bottom = p.history + p.rows - 1
    const from = mode === 'last' && plainStamp.current != null ? plainStamp.current + 1 : p.history - p.scroll
    const text = plainSlice(from, bottom)
    void copyText(text, tn(text ? text.split('\n').length : 0, 'Copied {n} line', 'Copied {n} lines'))
  }, [backend, sid, readPos])

  const toggleRange = useCallback(() => {
    setRange((on) => !on)
    // The gutter's rows are whole rows: the reader stops between two.
    readerRef.current?.layer.resync()
    setDot(null)
    setHoverRow(null)
    // The gutter opens on the last known position when the pane cannot be read.
    void readPos().then(setPos, () => undefined)
  }, [readPos])

  /** What find searches: the reader while it is open (all the tmux history), else the live xterm. */
  const searcher = () => readerRef.current?.search ?? searchRef.current
  const toggleFind = useCallback(() => setFind((v) => {
    if (v) searcher()?.clearDecorations?.()
    // tmux keeps the history: find opens the reader, which holds it.
    else if (backend === 'tmux' && smoothRef.current && !readerRef.current) openReaderRef.current(0, undefined, 50_000)
    return !v
  }), [backend])

  useEffect(() => {
    bind?.({ find: toggleFind, range: toggleRange, copyScreen: () => void copyWhole('screen'), copyLast: () => void copyWhole('last') })
    return () => bind?.(null)
  }, [bind, toggleFind, toggleRange, copyWhole])

  // While the gutter is open the pane keeps moving (a scroll, new output):
  // follow it, so the numbers and the dot stay on their lines.
  useEffect(() => {
    if (!range) return
    let dead = false
    const tick = () => {
      // A missed read is the next tick's to make, 200 ms later.
      void readPos().then((p) => { if (!dead) setPos(p) }, () => undefined)
      const scr = box.current?.querySelector('.xterm-screen') as HTMLElement | null
      const t = termRef.current
      if (scr && t && t.rows > 0) setCellH(scr.clientHeight / t.rows)
    }
    tick()
    const id = window.setInterval(tick, 200)
    return () => { dead = true; window.clearInterval(id) }
  }, [range, readPos])

  /* ---------------------------------------------- scrolled up, and back */

  // Scrolled up into the history, and how many lines arrived since: the
  // "↓ newest" pill. A plain terminal's widget tells us on its own; a tmux
  // one scrolls inside tmux (copy mode), so a wheel starts a short watch
  // of the pane's position that ends once it is back at the bottom.
  const [behind, setBehind] = useState<{ up: boolean; fresh: number }>({ up: false, fresh: 0 })
  const watching = useRef(false)
  const mark = useRef(0)
  // The watch is a chain of timers: it ends with the screen.
  const mounted = useRef(true)
  useEffect(() => { mounted.current = true; return () => { mounted.current = false } }, [])
  const watchTmux = useCallback(() => {
    if (backend !== 'tmux' || watching.current || readerRef.current) return
    watching.current = true
    let first = true
    const tick = async () => {
      if (!mounted.current) { watching.current = false; return }
      try {
        const p = await readPos()
        if (!mounted.current) { watching.current = false; return }
        if (first) { mark.current = p.history; first = false }
        const up = p.scroll > 0
        setBehind({ up, fresh: up ? Math.max(0, p.history - mark.current) : 0 })
        if (!up) { watching.current = false; return }
      } catch { watching.current = false; return }
      window.setTimeout(() => void tick(), 400)
    }
    // A wheel lands before tmux moves: look once it has.
    window.setTimeout(() => void tick(), 120)
  }, [backend, readPos])

  // The reader is a snapshot: while it is open, count what the pane printed since.
  useEffect(() => {
    if (!reading) return
    setBehind({ up: true, fresh: 0 })
    let dead = false
    const id = window.setInterval(() => {
      const r = readerRef.current
      if (!r) return
      void getJson<PanePos>(`/api/terminal/sessions/${encodeURIComponent(sid)}/pos`)
        .then((p) => { if (!dead) setBehind({ up: true, fresh: Math.max(0, p.history - r.history) }) }, () => undefined)
    }, 1000)
    return () => { dead = true; window.clearInterval(id); setBehind({ up: false, fresh: 0 }) }
  }, [reading, sid])

  const toBottom = useCallback(async () => {
    if (readerRef.current) {
      closeReaderRef.current()
    } else if (backend === 'tmux') {
      try { await postJson(`/api/terminal/sessions/${encodeURIComponent(sid)}/bottom`, {}) } catch { /* the watch will see */ }
    } else {
      termRef.current?.scrollToBottom()
    }
    setBehind({ up: false, fresh: 0 })
    termRef.current?.focus()
  }, [backend, sid])

  /* ------------------------------------------------ printed paths → editor */

  const openPath = useCallback((p: PrintedPath) => {
    void postJson(`/api/terminal/sessions/${encodeURIComponent(sid)}/open`, { path: p.path, line: p.line, col: p.col })
      .then(() => toast.success(tr('Opened {file}', { file: `${p.path.split('/').pop()}${p.line ? `:${p.line}` : ''}` })))
      .catch((e: Error) => toast.error(e.message))
  }, [sid])

  /** The printed path under the mouse, if any: its screen row and columns. */
  const pathAt = (e: { clientX: number; clientY: number }): { path: PrintedPath; row: number } | null => {
    const t = termRef.current
    const scr = box.current?.querySelector('.xterm-screen') as HTMLElement | null
    if (!t || !scr || !editorRef.current) return null
    const r = scr.getBoundingClientRect()
    const col = Math.floor(((e.clientX - r.left) / r.width) * t.cols)
    const row = Math.floor(((e.clientY - r.top) / r.height) * t.rows)
    if (col < 0 || row < 0 || col >= t.cols || row >= t.rows) return null
    const b = t.buffer.active
    const text = b.getLine(b.viewportY + row)?.translateToString(true) ?? ''
    const hit = findPaths(text).find((p) => col >= p.start && col < p.start + p.length)
    return hit ? { path: hit, row } : null
  }

  // Ctrl (⌘) held over a path: underline it, like any editor's terminal.
  // tmux owns the mouse, so the widget's own link hover never fires — this
  // draws the hint itself and takes the Ctrl+click before tmux sees it.
  const [linkHint, setLinkHint] = useState<{ row: number; start: number; length: number } | null>(null)
  const hintAt = (e: React.MouseEvent) => {
    if (!(e.ctrlKey || e.metaKey)) { if (linkHint) setLinkHint(null); return }
    const hit = pathAt(e)
    const next = hit ? { row: hit.row, start: hit.path.start, length: hit.path.length } : null
    if (next?.row !== linkHint?.row || next?.start !== linkHint?.start) setLinkHint(next)
  }
  useEffect(() => {
    // xterm sets its own cursor on the screen element: point it while a path is lit.
    const scr = box.current?.querySelector('.xterm-screen') as HTMLElement | null
    if (scr) scr.style.cursor = linkHint ? 'pointer' : ''
    if (!linkHint) return
    const off = (e: KeyboardEvent) => { if (e.key === 'Control' || e.key === 'Meta') setLinkHint(null) }
    window.addEventListener('keyup', off)
    return () => window.removeEventListener('keyup', off)
  }, [linkHint])

  openPathRef.current = openPath

  const gutterClick = async (row: number) => {
    const p = await readPos().catch((e: Error) => { toast.error(tr('The terminal could not be read: {error}', { error: e.message })); return null })
    if (!p) return
    setPos(p)
    const abs = absOf(row, p)
    if (!dot) { setDot({ abs, rel: relOf(row, p) }); return }
    await copyRows(dot.abs, abs)
  }

  const paste = useCallback(async () => {
    try {
      const text = await navigator.clipboard.readText()
      if (text) termRef.current?.paste(text)
    } catch {
      toast.error(tr('The browser blocked the clipboard. Press {key} instead.', { key: pasteKeyName(IS_MAC) }))
    }
    termRef.current?.focus()
  }, [])

  /* --------------------------------------------------------------- xterm */

  useEffect(() => {
    const el = box.current
    if (!el) return
    let disposed = false
    let term: Terminal | null = null
    let ws: WebSocket | null = null
    let ro: ResizeObserver | null = null
    let retry: ReturnType<typeof setTimeout> | null = null
    let tries = 0
    let authFails = 0
    let onWheel: ((e: WheelEvent) => void) | null = null

    const init = async () => {
      const [{ Terminal: XTerminal }, { FitAddon }, { WebLinksAddon }, { SearchAddon: Search }] = await Promise.all([
        import('xterm'), import('xterm-addon-fit'), import('xterm-addon-web-links'), import('xterm-addon-search'),
      ])
      await import('xterm/css/xterm.css')
      if (disposed) return
      // The cursor wears the accent the operator chose (accent themes), not a fixed green.
      const accent = getComputedStyle(document.documentElement).getPropertyValue('--brand').trim() || THEME.cursor
      const t = new XTerminal({
        theme: { ...THEME, cursor: accent },
        fontFamily: '"Geist Mono","JetBrains Mono","SF Mono",Menlo,monospace',
        fontSize, lineHeight: 1.15, cursorBlink: true, allowProposedApi: true,
        scrollback, macOptionIsMeta: true, rightClickSelectsWord: false,
      })
      term = t
      termRef.current = t
      const fit = new FitAddon()
      t.loadAddon(fit)
      t.loadAddon(new WebLinksAddon((_e, uri) => window.open(uri, '_blank', 'noopener')))
      const search = new Search()
      t.loadAddon(search)
      searchRef.current = search
      t.open(el)
      // Pixel-smooth scrolling of the history xterm keeps (scrollLayer.ts):
      // the page takes the wheel before xterm when the terminal shows its own
      // history; a program that reads the mouse, or a full-screen one, still
      // gets it from xterm as before.
      const layer = attachSmoothLayer(t)
      layerRef.current = layer
      const stop = (e: Event) => { e.preventDefault(); e.stopPropagation() }
      onWheel = (e: WheelEvent) => {
        if (!smoothRef.current || e.deltaY === 0 || e.shiftKey || e.ctrlKey) return
        const r = readerRef.current
        if (r) {
          // Down at the newest line: the reader has shown it all, the live terminal comes back.
          if (e.deltaY > 0 && r.layer.atBottom()) { stop(e); closeReader(); return }
          if (r.layer.wheel(e)) stop(e)
          return
        }
        if (opening) { stop(e); pendingPx += wheelPx(e, rowH(), t.rows).px; pendingEvents.push(e); return }
        if (layer.wheel(e)) { stop(e); return }
        // tmux draws on xterm's alternate screen and asks for the mouse: the
        // page routes the wheel by what the pane shows (tmuxWheel).
        if (backend === 'tmux' && t.buffer.active.type === 'alternate' && t.modes.mouseTrackingMode !== 'none') { stop(e); tmuxWheel(e) }
      }

      /* ---- tmux: the wheel by what the pane shows ---- */
      const rowH = () => { const sc = el.querySelector('.xterm-screen') as HTMLElement | null; return sc && t.rows ? sc.clientHeight / t.rows : 16 }
      type Flags = { at: number; alt: boolean; mouse: boolean; in_mode: boolean }
      let flags: Flags | null = null
      let asking = false
      let lastWheel = 0
      let queued: WheelEvent[] = []
      const acc = new RowAccumulator()
      const route = (e: WheelEvent, f: Flags) => {
        const { px } = wheelPx(e, rowH(), t.rows)
        if (!f.alt && !f.mouse && !f.in_mode) {
          // The history: up opens the reader; down at the bottom is nothing.
          if (px < 0) openReader(px)
          return
        }
        // A full-screen program, one that reads the mouse, or tmux's own copy
        // mode (five lines a report): one wheel report per row the wheel moved,
        // where xterm sent one per event (a notch of six rows was one line).
        const n = acc.add(px, rowH() * (f.in_mode ? 5 : 1))
        if (!n || ws?.readyState !== WebSocket.OPEN) return
        const sc = (el.querySelector('.xterm-screen') as HTMLElement).getBoundingClientRect()
        const col = Math.floor(((e.clientX - sc.left) / sc.width) * t.cols) + 1
        const row = Math.floor(((e.clientY - sc.top) / sc.height) * t.rows) + 1
        ws.send(JSON.stringify({ type: 'input', data: sgrWheel(n < 0, col, row).repeat(Math.min(Math.abs(n), 50)) }))
      }
      const tmuxWheel = (e: WheelEvent) => {
        const now = performance.now()
        // One question to the server per gesture (a pause of 300 ms ends one).
        const same = now - lastWheel < 300
        lastWheel = now
        if (flags && same && now - flags.at < 2000) { route(e, flags); return }
        // Up, the pane unknown: ask for the history straight away; its answer
        // says what the pane shows too (one round trip, not two).
        if (e.deltaY < 0 && !asking) { openReader(wheelPx(e, rowH(), t.rows).px, e); return }
        queued.push(e)
        if (asking) return
        asking = true
        getJson<PanePos & { alt: boolean; mouse: boolean; in_mode: boolean }>(`/api/terminal/sessions/${encodeURIComponent(sid)}/pos`)
          .then((p) => {
            flags = { at: performance.now(), alt: !!p.alt, mouse: !!p.mouse, in_mode: !!p.in_mode }
            const q = queued; queued = []
            for (const ev of q) route(ev, flags)
          })
          .catch(() => { queued = [] })
          .finally(() => { asking = false })
      }

      /* ---- tmux: the reader ---- */
      let opening = false
      let pendingPx = 0
      let pendingEvents: WheelEvent[] = []
      const wire = (r: Reader) => {
        r.term.attachCustomKeyEventHandler((e) => {
          if (e.type !== 'keydown') return true
          const what = readerKeeps(e, IS_MAC)
          if (what === 'keep') {
            const mod = IS_MAC ? e.metaKey : e.ctrlKey
            const k = letter(e)
            if ((mod || (e.ctrlKey && e.shiftKey)) && k === 'c') { if (r.term.hasSelection()) { void copyText(r.term.getSelection()); r.term.clearSelection() } return false }
            if (e.ctrlKey && e.shiftKey && k === 'f') { toggleFind(); return false }
            return mod && k === 'a' ? (r.term.selectAll(), false) : true
          }
          if (what === 'page-up' || what === 'page-down') { r.layer.by((what === 'page-up' ? -1 : 1) * rowH() * (r.term.rows - 1), true); return false }
          closeReader()
          if (what === 'close') return false
          // Any other key is meant for the shell: it goes there, once.
          t.focus()
          const printable = e.key.length === 1 && !e.ctrlKey && !e.altKey && !e.metaKey
          if (!printable) {
            // (A printable key's own keypress follows the focus to the live terminal.)
            const again = new KeyboardEvent('keydown', { key: e.key, code: e.code, ctrlKey: e.ctrlKey, altKey: e.altKey, shiftKey: e.shiftKey, metaKey: e.metaKey, bubbles: true, cancelable: true })
            Object.defineProperty(again, 'keyCode', { get: () => e.keyCode })
            Object.defineProperty(again, 'which', { get: () => e.which })
            t.textarea?.dispatchEvent(again)
          }
          return false
        })
        // A paste in the reader goes to the shell.
        r.el.addEventListener('paste', (ev) => {
          const text = ev.clipboardData?.getData('text/plain') ?? ''
          ev.preventDefault(); ev.stopPropagation()
          closeReader(); t.focus()
          if (text) t.paste(text)
        }, true)
      }
      const show = (r: Reader) => {
        r.el.style.visibility = 'visible'
        readerRef.current = r
        setReading(true)
      }
      const closeReader = () => {
        const r = readerRef.current
        if (!r) return
        readerRef.current = null
        r.dispose()
        flags = null
        setReading(false)
        if (findRef.current) searchRef.current?.clearDecorations?.()
        if (visibleRef.current && autoFocusRef.current) t.focus()
      }
      closeReaderRef.current = closeReader
      const openReader = (px: number, first?: WheelEvent, rows = FIRST_ROWS) => {
        if (readerRef.current || opening || disposed) return
        opening = true
        pendingPx = px
        pendingEvents = first ? [first] : []
        const make = { Terminal: XTerminal, Search }
        void fetchRows(sid, rows)
          .then(async (got) => {
            if (disposed) return
            const f = got as unknown as { alt?: boolean; mouse?: boolean; in_mode?: boolean }
            if (f.alt || f.mouse || f.in_mode) {
              // Not the history: a full-screen program or one that reads the mouse gets the wheel.
              flags = { at: performance.now(), alt: !!f.alt, mouse: !!f.mouse, in_mode: !!f.in_mode }
              lastWheel = performance.now()
              for (const ev of pendingEvents) route(ev, flags)
              return
            }
            const r = await buildReader(make, el, t, got)
            if (disposed) { r.dispose(); return }
            wire(r)
            show(r)
            if (pendingPx) r.layer.by(pendingPx, true)
            // A longer history follows, swapped in at the same line.
            if (!got.complete) {
              const full = await fetchRows(sid, 50_000).catch(() => null)
              if (!full || readerRef.current !== r || disposed) return
              const r2 = await buildReader(make, el, t, full)
              if (readerRef.current !== r || disposed) { r2.dispose(); return }
              // The same absolute line at the top: rows above r's first are (history - above).
              const h = rowH()
              const w = r.layer.where()
              const abs = w.pos + (r.history - r.above) * h
              wire(r2)
              r2.layer.setPos(abs - (full.history - full.above) * h)
              // A glide under way goes on in the new reader.
              if (Math.abs(w.target - w.pos) > 0.01) r2.layer.by(w.target - w.pos, true)
              r2.el.style.visibility = 'visible'
              readerRef.current = r2
              r.dispose()
            }
          })
          .catch(() => undefined)
          .finally(() => { opening = false; pendingPx = 0; pendingEvents = [] })
      }
      openReaderRef.current = openReader
      // The live terminal resized: the reader's rows no longer match it.
      t.onResize(() => closeReader())
      el.addEventListener('wheel', onWheel, { capture: true, passive: false })
      // A path the terminal printed (src/app.ts:42) opens in the editor at
      // that line; the server resolves it where the shell stands now.
      t.registerLinkProvider({
        provideLinks(y, callback) {
          if (!editorRef.current) { callback(undefined); return }
          const text = t.buffer.active.getLine(y - 1)?.translateToString(true) ?? ''
          const found = findPaths(text)
          callback(found.length ? found.map((p) => ({
            range: { start: { x: p.start + 1, y }, end: { x: p.start + p.length, y } },
            text: p.text,
            decorations: { underline: true, pointerCursor: true },
            activate: () => openPathRef.current(p),
          })) : undefined)
        },
      })
      if (backend === 'plain') {
        const look = () => {
          const b = t.buffer.active
          const up = b.viewportY < b.baseY
          if (up && mark.current < 0) mark.current = b.baseY
          if (!up) mark.current = -1
          setBehind({ up, fresh: up ? Math.max(0, b.baseY - mark.current) : 0 })
        }
        mark.current = -1
        t.onScroll(look)
        t.onWriteParsed(look)
      }
      // tmux announces every copy-mode copy (set-clipboard on, OSC 52):
      // a plain mouse-drag in the terminal lands on the system clipboard.
      t.parser.registerOscHandler(52, (data) => {
        const semi = data.indexOf(';')
        const b64 = semi >= 0 ? data.slice(semi + 1) : data
        if (!b64 || b64 === '?') return true
        try {
          const bytes = Uint8Array.from(atob(b64), (c) => c.charCodeAt(0))
          void copyText(new TextDecoder().decode(bytes))
        } catch { /* not base64: not a copy */ }
        return true
      })
      const doFit = () => {
        if (!el.offsetWidth || !el.offsetHeight) return
        try { fit.fit() } catch { /* not laid out yet */ }
        layerRef.current?.resync()
        if (ws?.readyState === WebSocket.OPEN) ws.send(JSON.stringify({ type: 'resize', cols: t.cols, rows: t.rows }))
      }
      fitRef.current = doFit
      api.current = { fit: doFit, focus: () => t.focus(), size: (n) => { t.options.fontSize = n; doFit() } }
      doFit()
      ro = new ResizeObserver(() => doFit())
      ro.observe(el)
      // Measured with the fallback font the columns come out wrong, and the
      // text fills only part of the box: measure again once the font is in.
      void document.fonts?.ready.then(() => { if (!disposed) doFit() })
      document.fonts?.addEventListener?.('loadingdone', doFit)
      // The view you type in sets the terminal's size (tmux: the latest client).
      t.textarea?.addEventListener('focus', () => { doFit(); onFocusRef.current?.(); setWork('terminal', { project: workRef.current.project, taskId: workRef.current.taskId }) })
      t.textarea?.addEventListener('blur', () => setWork('terminal', null))
      // Shown and meant to take the keyboard (a new split pane): take it now —
      // the effect below ran before the terminal existed. After the focus
      // listener: taken before it, the pane never became the work at hand.
      if (visibleRef.current && autoFocusRef.current) t.focus()

      t.attachCustomKeyEventHandler((e) => {
        if (e.type !== 'keydown') return true
        // Esc leaves the gutter or the find box before it reaches the shell.
        if (e.key === 'Escape' && (rangeRef.current || findRef.current || menuRef.current)) {
          setRange(false); setDot(null); setFind(false); setMenu(null)
          return false
        }
        // Ctrl/Cmd+C copies a selection; without one it is ^C.
        if ((e.ctrlKey || e.metaKey) && !e.shiftKey && letter(e) === 'c' && t.hasSelection()) {
          void copyText(t.getSelection())
          t.clearSelection()
          return false
        }
        // The classic pair, and find.
        if (e.ctrlKey && e.shiftKey && letter(e) === 'c') {
          if (t.hasSelection()) { void copyText(t.getSelection()); t.clearSelection() }
          return false
        }
        // A paste key pastes once: the browser's own paste (its paste event
        // reaches xterm), or the page's where the browser has none.
        const by = pasteKey(e, IS_MAC)
        if (by === 'native') return false
        if (by === 'page') { e.preventDefault(); void paste(); return false }
        if (e.ctrlKey && e.shiftKey && letter(e) === 'f') { toggleFind(); return false }
        // Ctrl+` belongs to the drawer.
        if (e.ctrlKey && e.key === '`') return false
        // Ctrl + / Ctrl − : the text size (the browser's zoom stays the browser's elsewhere).
        if (e.ctrlKey && !e.altKey && ['=', '+', '-', '_'].includes(e.key) && onZoomRef.current) {
          e.preventDefault()
          onZoomRef.current(e.key === '-' || e.key === '_' ? -1 : 1)
          return false
        }
        return true
      })
      t.onData((data) => {
        // Typed into the live terminal: the reader steps aside (focus and mouse reports are not typing).
        if (readerRef.current && !(data.startsWith('\x1b[I') || data.startsWith('\x1b[O') || data.startsWith('\x1b[<'))) closeReaderRef.current()
        if (ws?.readyState === WebSocket.OPEN) ws.send(JSON.stringify({ type: 'input', data }))
        onInputRef.current?.(data)
        if (data.includes('\r')) {
          const b = t.buffer.active
          plainStamp.current = b.baseY + b.cursorY
        }
      })

      const connect = () => {
        if (disposed) return
        const proto = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
        const url = `${proto}//${window.location.host}/ws/terminal/${encodeURIComponent(sid)}?token=${encodeURIComponent(token)}&cols=${t.cols}&rows=${t.rows}&project=${encodeURIComponent(project)}`
        const s = new WebSocket(url)
        ws = s
        s.binaryType = 'arraybuffer'
        s.onopen = () => { tries = 0; doFit() }
        // The server opens every socket and refuses after (4401 and the rest):
        // only the terminal's first output says the token was taken.
        s.onmessage = (ev) => { authFails = 0; t.write(ev.data instanceof ArrayBuffer ? new Uint8Array(ev.data) : String(ev.data)) }
        s.onclose = (ev) => {
          if (disposed) return
          if (ev.code === ENDED) { t.write(`\r\n\x1b[90m${tr('— the terminal ended —')}\x1b[0m\r\n`); onEndedRef.current?.(); return }
          // A restart made a new token: fetch it. A new token remounts this
          // screen; the same one (fetched before a second restart, or a failed
          // fetch) comes back here and tries again, a few times, then says so.
          if (ev.code === INVALID_TOKEN) {
            authFails += 1
            if (authFails > 5) { t.write(`\r\n\x1b[90m${tr('— could not reconnect: reload the page —')}\x1b[0m\r\n`); return }
            void qc.refetchQueries({ queryKey: ['terminal', 'state'] }).finally(() => {
              if (!disposed) retry = setTimeout(connect, Math.min(8000, 500 * 2 ** authFails))
            })
            return
          }
          if (ev.code === OFF) { t.write(`\r\n\x1b[90m${tr('— the terminal is off —')}\x1b[0m\r\n`); return }
          if (REFUSED.has(ev.code)) { t.write(`\r\n\x1b[90m${tr('— refused: {why} —', { why: ev.reason || ev.code })}\x1b[0m\r\n`); return }
          // Anything else: come back; tmux kept the terminal.
          tries += 1
          if (tries === 1) t.write(`\r\n\x1b[90m${tr('— reconnecting —')}\x1b[0m`)
          retry = setTimeout(connect, Math.min(8000, 400 * 2 ** Math.min(tries, 5)))
        }
      }
      connect()
    }
    setBroken('')
    init().catch((e: unknown) => { if (!disposed) setBroken(e instanceof Error ? e.message : String(e)) })
    return () => {
      disposed = true
      if (retry) clearTimeout(retry)
      ro?.disconnect()
      if (onWheel) el.removeEventListener('wheel', onWheel, { capture: true })
      layerRef.current?.dispose()
      layerRef.current = null
      readerRef.current?.dispose()
      readerRef.current = null
      document.fonts?.removeEventListener?.('loadingdone', fitRef.current)
      try { ws?.close() } catch { /* fine */ }
      // A terminal removed while it has the keyboard may never see its blur:
      // the timer must not go on counting it as the work at hand.
      if (term?.textarea && document.activeElement === term.textarea) setWork('terminal', null)
      try { term?.dispose() } catch { /* fine */ }
      api.current = null
      termRef.current = null
      searchRef.current = null
    }
    // One terminal per session: the size, scrollback and backend are read
    // when it is made (size changes go through api.size below), the callbacks
    // through refs. A new sid, token or project makes a new terminal.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [sid, token, project])

  useEffect(() => { api.current?.size(fontSize) }, [fontSize])
  useEffect(() => {
    if (!visible) return
    const id = requestAnimationFrame(() => { api.current?.fit(); if (autoFocusRef.current) api.current?.focus() })
    return () => cancelAnimationFrame(id)
  }, [visible])

  /* ------------------------------------------------------------- overlays */

  const rows = pos.rows
  const dotRow = dot ? rowOf(dot.abs, pos) : null
  const previewLo = dot && hoverRow != null ? Math.min(dotRow ?? hoverRow, hoverRow) : null
  const previewHi = dot && hoverRow != null ? Math.max(dotRow ?? hoverRow, hoverRow) : null
  const flashLo = flash ? rowOf(flash.a, pos) : null
  const flashHi = flash ? rowOf(flash.b, pos) : null

  const menuItem = 'w-full text-left px-10 h-[26px] text-12 text-[var(--term-soft)] hover:bg-white/10 hover:text-[var(--term-text)] inline-flex items-center gap-8 disabled:opacity-40'

  return (
    <div className="relative w-full h-full min-h-0" style={{ background: THEME.background }}
      onContextMenu={(e) => { e.preventDefault(); const r = e.currentTarget.getBoundingClientRect(); setMenu({ x: e.clientX - r.left, y: e.clientY - r.top }) }}>
      <div ref={box} className="w-full h-full min-h-0 px-6 pt-4" style={{ display: visible ? 'block' : 'none' }}
        onWheelCapture={(e) => { if (e.deltaY < 0 || behind.up) watchTmux() }}
        onMouseMoveCapture={hintAt}
        onMouseLeave={() => setLinkHint(null)}
        onMouseDownCapture={(e) => {
          if (!(e.ctrlKey || e.metaKey) || e.button !== 0) return
          const hit = pathAt(e)
          if (!hit) return
          e.preventDefault(); e.stopPropagation()
          setLinkHint(null)
          openPath(hit.path)
        }} />

      {broken && (
        <p role="alert" className="absolute inset-x-0 top-0 px-12 py-8 text-12 font-mono text-error">
          {tr('The terminal could not start: {error}', { error: broken })}
        </p>
      )}

      {visible && linkHint && (() => {
        const scr = box.current?.querySelector('.xterm-screen') as HTMLElement | null
        const t = termRef.current
        if (!scr || !t || !box.current) return null
        const r = scr.getBoundingClientRect()
        const o = box.current.getBoundingClientRect()
        const cw = r.width / t.cols, ch = r.height / t.rows
        return (
          <div aria-hidden className="absolute pointer-events-none z-10" style={{
            left: r.left - o.left + linkHint.start * cw, top: r.top - o.top + (linkHint.row + 1) * ch - 2,
            width: linkHint.length * cw, height: 1, background: 'var(--term-text)',
          }} />
        )
      })()}

      {visible && behind.up && !range && (
        <button type="button" onClick={() => void toBottom()}
          className="absolute bottom-8 right-12 z-10 inline-flex items-center gap-6 h-24 px-10 rounded-pill border border-white/15 text-11 font-mono text-[var(--term-text)] shadow-lg hover:border-brand"
          style={{ background: 'var(--term-bar)' }} title={tr('Back to the newest line')}>
          ↓ {tr('newest')}{behind.fresh > 0 ? <span className="text-brand">· {tr('{n} new', { n: behind.fresh })}</span> : null}
        </button>
      )}

      {visible && range && (
        <div className="absolute inset-y-0 left-0 w-[52px] select-none z-10"
          style={{ background: 'rgba(14,16,19,0.97)', borderRight: '1px solid rgba(255,255,255,0.10)', paddingTop: 4 }}
          aria-label={tr('Select lines to copy')}>
          {dot && dotRow != null && dotRow < 0 && (
            <span className="absolute top-2 left-2 right-2 text-center text-10 font-mono text-brand" title={tr('First selected line, above the screen')}>● {-dotRow}↑</span>
          )}
          {Array.from({ length: rows }, (_, r) => {
            const inPreview = previewLo != null && previewHi != null && r >= previewLo && r <= previewHi
            const inFlash = flashLo != null && flashHi != null && r >= flashLo && r <= flashHi
            return (
              <button key={r} type="button"
                onClick={() => void gutterClick(r)}
                onMouseEnter={() => setHoverRow(r)}
                onMouseLeave={() => setHoverRow((h) => (h === r ? null : h))}
                style={{ height: cellH || 18 }}
                className={`w-full px-4 text-right text-10 font-mono leading-none inline-flex items-center justify-end gap-3 ${
                  inFlash ? 'bg-brand/30 text-[var(--term-text)]' : inPreview ? 'bg-brand/15 text-[var(--term-soft)]' : 'text-[var(--term-muted)] hover:bg-white/10 hover:text-[var(--term-text)]'}`}
                title={dot ? tr('Click to copy the lines between') : tr('Click to start the selection')}>
                {dotRow === r && <span className="text-brand" aria-hidden>●</span>}
                {relOf(r, pos)}
              </button>
            )
          })}
          {dot && dotRow != null && dotRow >= rows && (
            <span className="absolute bottom-2 left-2 right-2 text-center text-10 font-mono text-brand" title={tr('First selected line, below the screen')}>● {dotRow - rows + 1}↓</span>
          )}
        </div>
      )}

      {visible && find && (
        <div className="absolute top-4 right-6 z-10 flex items-center gap-4 rounded-input border border-white/15 px-6 h-[28px]"
          style={{ background: 'var(--term-bar)' }}>
          <input autoFocus placeholder={tr('find')} aria-label={tr('Find in the terminal')}
            className="w-[160px] bg-transparent text-12 font-mono text-[var(--term-text)] outline-none placeholder:text-[var(--term-muted)]"
            onKeyDown={(e) => {
              if (e.key === 'Enter' && !e.shiftKey) searcher()?.findNext(e.currentTarget.value)
              if (e.key === 'Enter' && e.shiftKey) searcher()?.findPrevious(e.currentTarget.value)
              if (e.key === 'Escape') toggleFind()
            }}
            onChange={(e) => searcher()?.findNext(e.target.value, { incremental: true })} />
          <button type="button" className="text-[var(--term-muted)] hover:text-[var(--term-text)] text-12 px-2" title={tr('Previous (Shift+Enter)')}
            onClick={(e) => searcher()?.findPrevious((e.currentTarget.parentElement?.querySelector('input') as HTMLInputElement)?.value ?? '')}>‹</button>
          <button type="button" className="text-[var(--term-muted)] hover:text-[var(--term-text)] text-12 px-2" title={tr('Next (Enter)')}
            onClick={(e) => searcher()?.findNext((e.currentTarget.parentElement?.querySelector('input') as HTMLInputElement)?.value ?? '')}>›</button>
          <button type="button" className="text-[var(--term-muted)] hover:text-[var(--term-text)] text-12 px-2" aria-label={tr('Close find')} onClick={toggleFind}>×</button>
        </div>
      )}

      {visible && menu && (
        <>
          <button type="button" aria-label={tr('Close the menu')} className="fixed inset-0 z-10 cursor-default" onClick={() => setMenu(null)} onContextMenu={(e) => { e.preventDefault(); setMenu(null) }} />
          <div role="menu" className="absolute z-20 w-[220px] py-4 rounded-input border border-white/15 shadow-lg flex flex-col"
            style={{ background: 'var(--term-bar)', left: Math.min(menu.x, (box.current?.clientWidth ?? 300) - 230), top: Math.min(menu.y, (box.current?.clientHeight ?? 200) - 224) }}>
            <button type="button" role="menuitem" className={menuItem} disabled={!termRef.current?.hasSelection()}
              onClick={() => { const t = termRef.current; if (t?.hasSelection()) { void copyText(t.getSelection()); t.clearSelection() } setMenu(null) }}>
              {tr('Copy')} <span className="ml-auto text-10 text-[var(--term-muted)]">Ctrl+C</span>
            </button>
            <button type="button" role="menuitem" className={menuItem} onClick={() => { void paste(); setMenu(null) }}>
              {tr('Paste')} <span className="ml-auto text-10 text-[var(--term-muted)]">{pasteKeyName(IS_MAC)}</span>
            </button>
            <div className="h-1 my-3 bg-white/10" />
            <button type="button" role="menuitem" className={menuItem} onClick={() => { void copyWhole('last'); setMenu(null) }}>{tr('Copy the last output')}</button>
            <button type="button" role="menuitem" className={menuItem} onClick={() => { void copyWhole('screen'); setMenu(null) }}>{tr('Copy the screen')}</button>
            <button type="button" role="menuitem" className={menuItem} onClick={() => { toggleRange(); setMenu(null) }}>
              {tr('Select lines…')} <span className="ml-auto text-10 text-[var(--term-muted)]">{tr('two clicks')}</span>
            </button>
            <div className="h-1 my-3 bg-white/10" />
            <button type="button" role="menuitem" className={menuItem} onClick={() => { toggleFind(); setMenu(null) }}>
              {tr('Find')} <span className="ml-auto text-10 text-[var(--term-muted)]">Ctrl+Shift+F</span>
            </button>
          </div>
        </>
      )}
    </div>
  )
}

export const TERMINAL_GROUND = THEME.background
