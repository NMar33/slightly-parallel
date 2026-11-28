/**
 * One terminal's screen: xterm on the socket /ws/terminal/{id}.
 *
 * - fits its box, whatever resizes it (the drawer's handle, a split, the
 *   window) — a ResizeObserver, not the window's resize;
 * - comes back on its own: a dropped socket reconnects (the terminal lives
 *   on in tmux), and says so in one grey line;
 * - the mouse selects, Ctrl+Shift+C or the menu copies. Program clipboard
 *   requests follow the operator's OSC 52 setting. Shift+drag selects locally,
 *   Ctrl+C with native text selected copies, Ctrl+Shift+C/V
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
import { readable, xtermTheme, type XtermTheme } from './schemes'
import './cursor.css'
import { useTermScheme } from './useScheme'
import { letter } from '../../lib/typing'
import { IS_MAC, pasteKey, pasteKeyName } from './pasteKeys'
import { attachSmoothLayer, disposeTerminal, type SmoothLayer } from './scrollLayer'
import { keepSelectionLocal } from './explicitClipboard'
import { buildReader, fetchRows, FIRST_ROWS, placeAt, plainRows, readerKeeps, topOf, type FoldOpts, type HistoryRows, type Reader } from './reader'
import { joinedRows, tmuxRows } from './fold'
import { foldIds, hasFolds, onFolds, setFolds, clearFolds } from './foldStore'
import { RowAccumulator, Scroller, sgrWheel, wheelPx } from './smoothScroll'
import { startTermLog, termLog, type Attached } from './telemetry'
import { InputMarker } from './operatorInput'
import { enableTextSelection, hasTextSelectionAnchor, transferTextSelection } from './textSelection'
import { useProgramClipboard } from './programClipboard'
import { terminalSnapshot } from './diagnostics'

const SELECTION_FLASH_DURATION_MS = 350
const MOUSE_MODE_POLL_INTERVAL_MS = 200
const COPY_MODE_POLL_INTERVAL_MS = 400
const COPY_MODE_INITIAL_POLL_DELAY_MS = 120
const SCROLLBACK_FRESH_LINES_POLL_MS = 1000

/** tmux: the history is taken ahead once the terminal has rested this long (no output) under the pointer, at most once per AHEAD_EVERY_MS. */
const AHEAD_REST_MS = 700
const AHEAD_EVERY_MS = 5000
/** tmux: what the pane shows (history or a full-screen program) is asked this long after the operator typed. */
const KIND_AFTER_TYPING_MS = 1000
/** Once the pane answers with output, ask sooner so its next gesture goes to the right owner. */
const KIND_AFTER_OUTPUT_MS = 50
/** Refresh the known pane kind during output without spawning tmux for every frame. */
const KIND_REFRESH_MS = 300
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
  /** The terminal's rows as text, and which one is under a point (null: no text there). */
  rowsAt: (clientX: number, clientY: number) => Promise<ScreenRows | null>
  /** The text selected in the terminal, or ''. */
  selection: () => string
  /** Copy text selected in tmux itself, which xterm cannot read. */
  copyTmuxSelection?: () => Promise<boolean>
  /** The screen's own right-click menu (copy, paste, find …) at a point. */
  ownMenu: (clientX: number, clientY: number) => void
  /** Open a printed path in the editor, as Ctrl+click does (the link menu's «Open»). */
  openPath?: (p: PrintedPath) => void
  /** The editor printed paths open in; '' — paths are no links. */
  editor?: () => string
  /** Put text on the live terminal's prompt the way a paste key does (xterm's paste: once, bracketed when the shell asked for it); never Enter. */
  paste?: (text: string) => void
  /** The shell asked for bracketed paste (a plain terminal; never under tmux): a pasted line break waits for Enter instead of running. */
  bracketed?: () => boolean
  /** Messages collapsed to one line in the history (fold.ts, tk_a2bb64a1). */
  fold?: FoldApi
}

/**
 * Collapsing messages (fold.ts): only the history the page draws (scrolled
 * up) shows them as one line; the live screen at the bottom is the program's.
 */
export interface FoldApi {
  /** The message with this id is collapsed in this terminal. */
  has: (id: string) => boolean
  /** How many are collapsed. */
  count: () => number
  /** Collapse or expand; then: shown (the history on view changed), later (the message is on the live screen: it collapses once it is history), off (no page-drawn history: smooth scrolling is off). */
  set: (ids: string[], on: boolean) => Promise<'shown' | 'later' | 'off'>
  /** Expand all. */
  clear: () => Promise<void>
}

/** Every row the screen can read — a tmux pane's history from tmux — wrapped rows joined; `at` is the row under the point. */
export interface ScreenRows { rows: string[]; at: number }

/**
 * A layer over the screen that takes some clicks (the message menu,
 * messageMenu/): it is handed each xterm the screen makes — the live one,
 * then each tmux history reader — and is asked first about a mouse press
 * and a right click. True: the layer took it, xterm (and tmux) never see it.
 */
export interface ScreenHooks {
  terminal?: (t: Terminal, kind: 'live' | 'reader') => void
  mouse?: (e: MouseEvent) => boolean
  contextMenu?: (e: MouseEvent) => boolean
}

// What `capture-pane -e` leaves in the text besides the words: colours, titles, charsets.
const ESC = '\u001b', BEL = '\u0007'
const ANSI = new RegExp(`${ESC}\\[[0-9;?]*[ -/]*[@-~]|${ESC}\\][^${BEL}${ESC}]*(?:${BEL}|${ESC}\\\\)|${ESC}[()][0-9A-B]`, 'g')

/** The buffer's rows, wrapped ones joined back into their line, and the line `row` is in. */
function bufferRows(t: Terminal, row: number): ScreenRows {
  const b = t.buffer.active
  const rows: string[] = []
  let at = 0
  for (let i = 0; i < b.length; i++) {
    const line = b.getLine(i)
    const s = line?.translateToString(true) ?? ''
    if (line?.isWrapped && rows.length) rows[rows.length - 1] += s
    else rows.push(s)
    if (i === row) at = rows.length - 1
  }
  return { rows, at }
}

interface Dot { abs: number; rel: number }

function setSteadyCursorColors(term: Terminal, theme: XtermTheme) {
  const element = term.element
  if (!element) return
  element.classList.add('sp-steady-cursor')
  // A colored input row also needs enough contrast in a light scheme.
  element.style.setProperty('--sp-cursor-fill', readable(theme.cursor, [theme.background]))
  element.style.setProperty('--sp-cursor-text', theme.cursorAccent)
}

export function Screen({ sid, token, fontSize = 13, scrollback = 10000, editor = '', visible = true, program = '', project = '', taskId = '', backend = 'tmux', smooth = true, onEnded, onFocus, autoFocus = true, onZoom, bind, onInput, onTitle, hooks }: {
  sid: string
  token: string
  fontSize?: number
  visible?: boolean
  program?: string
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
  /** Told of each input the operator sends to the shell (a key, a paste), after it is sent; not of mouse or focus reports or xterm's replies. What is sent never changes. */
  onInput?: (data: string) => void
  /** The title the program in the terminal set for itself (OSC 0/2): Claude Code sets the chat's name. */
  onTitle?: (title: string) => void
  /** A layer that takes some clicks first (the message menu in the terminal window). */
  hooks?: ScreenHooks
}) {
  const box = useRef<HTMLDivElement>(null)
  const fitRef = useRef<() => void>(() => {})
  const api = useRef<{ fit: () => void; focus: () => void; size: (n: number) => void } | null>(null)
  const termRef = useRef<Terminal | null>(null)
  const searchRef = useRef<SearchAddon | null>(null)
  const qc = useQueryClient()
  // The colour scheme (Settings › Terminal › Colour scheme): set live on the
  // xterm and on an open history reader, no reload.
  const { scheme } = useTermScheme()
  const schemeRef = useRef(scheme)
  schemeRef.current = scheme
  useEffect(() => {
    const t = termRef.current
    if (!t) return
    const theme = xtermTheme(scheme, getComputedStyle(document.documentElement).getPropertyValue('--brand').trim())
    t.options.theme = theme
    setSteadyCursorColors(t, theme)
    const r = readerRef.current
    if (r) { r.term.options.theme = theme; r.el.style.background = theme.background }
  }, [scheme])
  const onEndedRef = useRef(onEnded)
  const onFocusRef = useRef(onFocus)
  const workRef = useRef({ project, taskId })
  workRef.current = { project, taskId }
  const onZoomRef = useRef(onZoom)
  const onInputRef = useRef(onInput)
  onInputRef.current = onInput
  const onTitleRef = useRef(onTitle)
  onTitleRef.current = onTitle
  const hooksRef = useRef(hooks)
  hooksRef.current = hooks
  const visibleRef = useRef(visible)
  const smoothRef = useRef(smooth)
  smoothRef.current = smooth
  const layerRef = useRef<SmoothLayer | null>(null)
  /** tmux mode, scrolled up: the history in a reader over the live xterm (reader.ts). */
  const readerRef = useRef<Reader | null>(null)
  const captureDiagnostics = useCallback(async () => {
    const live = termRef.current
    if (!live) return
    try {
      const body = terminalSnapshot(live, layerRef.current, readerRef.current, smoothRef.current)
      const { path, owner_only: ownerOnly } = await postJson<{ path: string; owner_only: boolean }>(`/api/terminal/sessions/${encodeURIComponent(sid)}/diagnostics`, body)
      if (ownerOnly === false) toast.warning(tr('Terminal diagnostics saved to {path}. On Windows the file inherits the folder’s permissions.', { path }))
      else toast.success(tr('Terminal diagnostics saved to {path}', { path }))
    } catch (e) {
      toast.error(tr('Terminal diagnostics could not be saved: {error}', { error: (e as Error).message }))
    }
  }, [sid])
  const [reading, setReading] = useState(false)
  const openReaderRef = useRef<(px: number, first?: WheelEvent, rows?: number) => void>(() => {})
  const closeReaderRef = useRef<() => void>(() => {})
  /** The history taken ahead while the terminal rests, dropped (hidden, unmounted). */
  const dropAheadRef = useRef<() => void>(() => {})
  const autoFocusRef = useRef(autoFocus)
  const editorRef = useRef(editor)
  editorRef.current = editor
  const openPathRef = useRef<(p: PrintedPath) => void>(() => {})
  /** Make the reader again with the collapsed messages as they are now (fold.ts); a plain terminal scrolled up gets one. */
  const refoldRef = useRef<() => Promise<void>>(async () => {})
  /** Who this screen is to the fold store: its own changes it has made already. */
  const foldOrigin = useRef({}).current
  /** The gutter is open: its rows are counted whole, so nothing is collapsed meanwhile. */
  const foldsOffRef = useRef(false)
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
      // The reader's rows are the pane's: its history above, then the screen (collapsed messages counted whole).
      const top = topOf(r).src
      return { history: r.history, scroll: Math.max(0, r.src.length - r.term.rows - top), rows: r.term.rows }
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
    setTimeout(() => { setFlash(null); setRange(false); setDot(null) }, SELECTION_FLASH_DURATION_MS)
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

  /** The rows around a point: the reader's or a plain terminal's own buffer, else (tmux) the pane's history from tmux. */
  const rowsAt = useCallback(async (cx: number, cy: number): Promise<ScreenRows | null> => {
    const r = readerRef.current
    const t = r?.term ?? termRef.current
    const scr = (r?.el ?? box.current)?.querySelector('.xterm-screen') as HTMLElement | null
    if (!t || !scr || !t.rows) return null
    const rect = scr.getBoundingClientRect()
    const row = Math.floor(((cy - rect.top) / rect.height) * t.rows)
    if (row < 0 || row >= t.rows) return null
    const b = t.buffer.active
    // The reader: its source rows, collapsed messages whole (a label row is its message's first row).
    if (r) return joinedRows(r.src, r.map.toSrc(b.viewportY + row))
    if (backend !== 'tmux' || b.type === 'normal') return bufferRows(t, b.viewportY + row)
    // tmux draws its screen on xterm's alternate screen: the rows above it are tmux's.
    const got = await fetchRows(sid, FIRST_ROWS)
    const rows = got.text.replace(ANSI, '').split('\n')
    // In tmux's copy mode the screen shows the history `scroll` rows up.
    const scroll = (got as unknown as { in_mode?: boolean }).in_mode
      ? (await getJson<PanePos>(`/api/terminal/sessions/${encodeURIComponent(sid)}/pos`).catch(() => null))?.scroll ?? 0 : 0
    const at = got.above + row - scroll
    // Soft-wrapped rows joined, as the reader reads them (fold.tmuxRows): a message is named the same in both.
    return at >= 0 && at < rows.length ? joinedRows(tmuxRows(rows, got.cols || t.cols), at) : null
  }, [backend, sid])
  const selection = useCallback(() => {
    const r = readerRef.current?.term
    if (r?.hasSelection()) return r.getSelection()
    return termRef.current?.hasSelection() ? termRef.current.getSelection() : ''
  }, [])
  const { receive: receiveProgramCopy, copySelection: copyExplicitSelection } = useProgramClipboard(sid, visible, program)
  const copyTmuxSelection = useCallback(async () => {
    if (backend !== 'tmux' || readerRef.current) return false
    return copyExplicitSelection(async () => {
      const got = await postJson<{ text: string | null }>(`/api/terminal/sessions/${encodeURIComponent(sid)}/capture`, { mode: 'selection' })
      return got.text ?? null
    })
  }, [backend, sid, copyExplicitSelection])
  const copySelected = useCallback(async () => {
    const term = readerRef.current?.term ?? termRef.current
    if (term?.hasSelection()) {
      void copyText(term.getSelection())
      term.clearSelection()
    } else {
      await copyTmuxSelection().catch((e: Error) => toast.error(tr('The terminal could not be copied: {error}', { error: e.message })))
    }
  }, [copyTmuxSelection])
  const ownMenu = useCallback((cx: number, cy: number) => {
    const r = box.current?.parentElement?.getBoundingClientRect()
    if (r) setMenu({ x: cx - r.left, y: cy - r.top })
  }, [])

  useEffect(() => {
    bind?.({ find: toggleFind, range: toggleRange, copyScreen: () => void copyWhole('screen'), copyLast: () => void copyWhole('last'), rowsAt, selection, ownMenu,
      copyTmuxSelection,
      openPath: (p) => openPathRef.current(p), editor: () => editorRef.current,
      paste: (text) => {
        const t = termRef.current
        if (!t) return
        // As a paste in the reader does: the reader steps aside, the text goes to the shell.
        if (readerRef.current) closeReaderRef.current()
        t.paste(text)
        t.focus()
      },
      // tmux asks the window for bracketed paste whatever its pane's shell asked, and hands a paste
      // to a shell that did not ask unbracketed: its line breaks run. Only a plain terminal's mode is the shell's.
      bracketed: () => backend !== 'tmux' && !!termRef.current?.modes.bracketedPasteMode,
      fold: {
        has: (id) => foldIds(sid).has(id),
        count: () => foldIds(sid).size,
        set: async (ids, on) => {
          setFolds(sid, ids, on, foldOrigin)
          // Without smooth scrolling the history is tmux's own (or xterm's rows): nothing of the page's to collapse in.
          if (!smoothRef.current) return 'off'
          await refoldRef.current()
          if (!on) return 'shown'
          return readerRef.current?.folds.some((f) => ids.includes(f.id)) ? 'shown' : 'later'
        },
        clear: async () => { clearFolds(sid, foldOrigin); await refoldRef.current() },
      } })
    return () => bind?.(null)
  }, [bind, toggleFind, toggleRange, copyWhole, rowsAt, selection, copyTmuxSelection, ownMenu, backend, sid, foldOrigin])

  // The gutter numbers whole rows: a collapsed message opens while it is there, and closes again after.
  useEffect(() => {
    if (foldsOffRef.current === range) return
    foldsOffRef.current = range
    if (readerRef.current && (range ? readerRef.current.folds.length > 0 : hasFolds(sid))) void refoldRef.current()
  }, [range, sid])

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
    const id = window.setInterval(tick, MOUSE_MODE_POLL_INTERVAL_MS)
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
      window.setTimeout(() => void tick(), COPY_MODE_POLL_INTERVAL_MS)
    }
    // A wheel lands before tmux moves: look once it has.
    window.setTimeout(() => void tick(), COPY_MODE_INITIAL_POLL_DELAY_MS)
  }, [backend, readPos])

  // The reader is a snapshot: while it is open, count what the pane printed since.
  useEffect(() => {
    if (!reading) return
    setBehind({ up: true, fresh: 0 })
    let dead = false
    const id = window.setInterval(() => {
      const r = readerRef.current
      if (!r) return
      // A plain terminal's reader: the live buffer below it says what came since.
      if (backend !== 'tmux') { const b = termRef.current?.buffer.normal; if (b) setBehind({ up: true, fresh: Math.max(0, b.baseY - r.history) }); return }
      void getJson<PanePos>(`/api/terminal/sessions/${encodeURIComponent(sid)}/pos`)
        .then((p) => { if (!dead) setBehind({ up: true, fresh: Math.max(0, p.history - r.history) }) }, () => undefined)
    }, SCROLLBACK_FRESH_LINES_POLL_MS)
    return () => { dead = true; window.clearInterval(id); setBehind({ up: false, fresh: 0 }) }
  }, [reading, sid, backend])

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
    let offFolds: (() => void) | null = null
    /** The terminal log's view of this screen (telemetry.ts): kinds, sizes, times. */
    let logged: Attached | null = null

    const onDiagnosticsKey = (e: KeyboardEvent) => {
      if (IS_MAC || e.code !== 'KeyD' || !e.ctrlKey || !e.altKey || !e.shiftKey || e.metaKey) return false
      e.preventDefault()
      if (!e.repeat) void captureDiagnostics()
      return true
    }
    const init = async () => {
      const [{ Terminal: XTerminal }, { FitAddon }, { WebLinksAddon }, { SearchAddon: Search }] = await Promise.all([
        import('xterm'), import('xterm-addon-fit'), import('xterm-addon-web-links'), import('xterm-addon-search'),
      ])
      await import('xterm/css/xterm.css')
      if (disposed) return
      // The cursor wears the accent the operator chose (accent themes), not a fixed green.
      const accent = getComputedStyle(document.documentElement).getPropertyValue('--brand').trim()
      const theme = xtermTheme(schemeRef.current, accent)
      const t = new XTerminal({
        theme,
        fontFamily: '"Geist Mono","JetBrains Mono","SF Mono",Menlo,monospace',
        fontSize, lineHeight: 1.15, cursorBlink: true, allowProposedApi: true,
        scrollback, macOptionIsMeta: true, rightClickSelectsWord: false,
      })
      term = t
      termRef.current = t
      t.onTitleChange((title) => onTitleRef.current?.(title))
      const fit = new FitAddon()
      t.loadAddon(fit)
      t.loadAddon(new WebLinksAddon((_e, uri) => window.open(uri, '_blank', 'noopener')))
      const search = new Search()
      t.loadAddon(search)
      searchRef.current = search
      t.open(el)
      keepSelectionLocal(t)
      setSteadyCursorColors(t, theme)
      hooksRef.current?.terminal?.(t, 'live')
      // Pixel-smooth scrolling of the history xterm keeps (scrollLayer.ts):
      // the page takes the wheel before xterm when the terminal shows its own
      // history; a program that reads the mouse, or a full-screen one, still
      // gets it from xterm as before.
      const layer = attachSmoothLayer(t)
      layerRef.current = layer
      startTermLog()
      logged = termLog.attach({
        sid, project, backend, el, term: t,
        scrollPath: () => readerRef.current ? 'reader' : !smoothRef.current ? 'rows' : backend === 'tmux' ? 'tmux' : t.buffer.active.type === 'alternate' ? 'alt' : 'smooth',
        offset: () => (readerRef.current?.layer ?? layer).where().pos,
      })
      const stop = (e: Event) => { e.preventDefault(); e.stopPropagation() }
      // Desktop backends may turn a vertical Shift+wheel notch into deltaX.
      // This is only used after checking that Shift is extending a selection.
      const wheelMotion = (e: WheelEvent) => e.deltaY || !e.shiftKey ? e : { deltaY: e.deltaX, deltaMode: e.deltaMode }
      const rowSteps = new RowAccumulator()
      const scrollRows = (term: Terminal, e: WheelEvent) => {
        const height = rowH()
        if (height <= 0) return
        const { px } = wheelPx(wheelMotion(e), height, term.rows)
        const steps = rowSteps.add(px, height)
        if (steps) term.scrollLines(steps)
      }
      onWheel = (e: WheelEvent) => {
        const r = readerRef.current
        const extending = e.shiftKey && hasTextSelectionAnchor(r?.term ?? t)
        const smooth = smoothRef.current
        const motion = wheelMotion(e)
        if (!motion.deltaY || e.ctrlKey || (e.shiftKey && !extending) || (!smooth && !extending && !r)) return
        if (r) {
          // Down at the newest line: the reader has shown it all, the live terminal comes back.
          if (motion.deltaY > 0 && r.layer.atBottom() && !r.term.hasSelection() && !e.shiftKey) { stop(e); closeReader(); return }
          if (!smooth) { stop(e); scrollRows(r.term, e); return }
          if (r.layer.wheel(motion)) stop(e)
          return
        }
        if (opening) { stop(e); lead.push(e); pendingEvents.push(e); return }
        // A plain terminal with collapsed messages shows its history in a reader too (fold.ts):
        // the rows the page writes can leave a message out, xterm's own cannot.
        if (smooth && backend !== 'tmux' && layer.owns() && !foldsOffRef.current && hasFolds(sid)
          && (motion.deltaY < 0 || t.buffer.active.viewportY < t.buffer.active.baseY)) { stop(e); void openPlain(e); return }
        if (smooth && layer.wheel(motion)) { stop(e); return }
        if (!smooth && e.shiftKey && layer.owns()) { stop(e); scrollRows(t, e); return }
        // tmux draws on xterm's alternate screen and asks for the mouse: the
        // page routes the wheel by what the pane shows (tmuxWheel).
        if (backend === 'tmux' && t.buffer.active.type === 'alternate' && t.modes.mouseTrackingMode !== 'none') { stop(e); tmuxWheel(e) }
      }

      /* ---- tmux: the wheel by what the pane shows ---- */
      const rowH = () => { const sc = el.querySelector('.xterm-screen') as HTMLElement | null; return sc && t.rows ? sc.clientHeight / t.rows : 16 }
      type PaneFlags = { alt?: boolean; mouse?: boolean; in_mode?: boolean; selecting?: boolean }
      type Flags = { at: number; alt: boolean; mouse: boolean; in_mode: boolean }
      let flags: Flags | null = null
      let asking = false
      let lastWheel = 0
      let queued: WheelEvent[] = []
      const acc = new RowAccumulator()
      const route = (e: WheelEvent, f: Flags) => {
        const { px } = wheelPx(wheelMotion(e), rowH(), t.rows)
        if (!f.alt && !f.mouse && !f.in_mode) {
          // The history: up opens the reader; down at the bottom is nothing.
          if (px < 0) openReader(px)
          return
        }
        // A full-screen program, one that reads the mouse, or tmux's own copy
        // mode (five lines a report): one wheel report per row the wheel moved,
        // where xterm sent one per event (a notch of six rows was one line).
        if (e.shiftKey) return
        const n = acc.add(px, rowH() * (f.in_mode ? 5 : 1))
        if (!n || ws?.readyState !== WebSocket.OPEN) return
        const sc = (el.querySelector('.xterm-screen') as HTMLElement).getBoundingClientRect()
        const col = Math.floor(((e.clientX - sc.left) / sc.width) * t.cols) + 1
        const row = Math.floor(((e.clientY - sc.top) / sc.height) * t.rows) + 1
        ws.send(JSON.stringify({ type: 'input', data: sgrWheel(n < 0, col, row).repeat(Math.min(Math.abs(n), 50)), typed: false }))
      }
      const tmuxWheel = (e: WheelEvent) => {
        const now = performance.now()
        // One question to the server per gesture (a pause of 300 ms ends one).
        const same = now - lastWheel < 300
        lastWheel = now
        if (flags && same && now - flags.at < 2000) { route(e, flags); return }
        // Up, the pane unknown: ask for the history straight away; its answer
        // says what the pane shows too (one round trip, not two).
        if (wheelMotion(e).deltaY < 0 && !asking) { openReader(wheelPx(wheelMotion(e), rowH(), t.rows).px, e); return }
        queued.push(e)
        if (asking) return
        asking = true
        getJson<PanePos & PaneFlags>(`/api/terminal/sessions/${encodeURIComponent(sid)}/pos`)
          .then((p) => {
            learn(p)
            flags = { at: performance.now(), alt: !!p.alt, mouse: !!p.mouse, in_mode: !!p.in_mode }
            const q = queued; queued = []
            for (const ev of q) route(ev, flags)
          })
          .catch(() => { queued = [] })
          .finally(() => { asking = false })
      }

      /* ---- tmux: the reader ---- */
      let opening = false
      let pendingEvents: WheelEvent[] = []
      const make = { Terminal: XTerminal, Search }
      /** The collapsed messages a reader is made with (none while the gutter is open); the live screen at the bottom never. */
      const foldOpts = (): FoldOpts | undefined => {
        if (foldsOffRef.current) return undefined
        const ids = foldIds(sid)
        return ids.size ? { has: (id) => ids.has(id), tail: t.rows } : undefined
      }

      // While the reader loads (a round trip and an xterm: 4–5 frames), the
      // live screen moves with the finger at once, so the first frame of a
      // gesture already moves (tk_0d123cd5). The rows above the screen are
      // not in the page yet: the band that opens at the top stays empty until
      // the reader takes over at the very same pixel. Only when the pane is
      // known to show its history (paneKind): a full-screen program gets the
      // wheel as rows, and a screen led and pulled back would be a jiggle.
      // Not known (before the first answer, after the operator typed — a
      // command may start one), the input waits and glides in, as before.
      let paneKind: 'history' | 'program' | null = null
      let paneKindVersion = 0
      let tmuxSelecting = false
      const learn = (f: PaneFlags) => {
        tmuxSelecting = !!f.selecting
        paneKind = f.alt || f.mouse || f.in_mode ? 'program' : 'history'
      }
      enableTextSelection(t, () => backend === 'tmux' && paneKind === 'history', backend === 'tmux', () => tmuxSelecting)
      const lead = (() => {
        const sc = () => el.querySelector('.xterm-screen') as HTMLElement | null
        // Pixels up from the newest line; not capped: what the screen cannot show, the reader does.
        const s = new Scroller()
        let raf = 0
        const paint = () => {
          const screen = sc()
          if (!screen) return
          const H = screen.clientHeight
          const dpr = window.devicePixelRatio || 1
          const px = Math.round(Math.min(s.pos, H) * dpr) / dpr
          screen.style.transform = px > 0 ? `translateY(${px}px)` : ''
          screen.style.clipPath = px > 0 ? `polygon(0 ${-px}px, 100% ${-px}px, 100% ${H - px}px, 0 ${H - px}px)` : ''
        }
        let shown = false
        const tick = (now: number) => {
          raf = 0
          if (disposed || !opening) return
          const more = s.step(now)
          paint()
          if (more) raf = requestAnimationFrame(tick)
        }
        return {
          /** A gesture starts: led on the screen (`show`), or only kept until the reader is there. */
          start: (show: boolean) => { shown = show; s.set(0, Number.MAX_SAFE_INTEGER) },
          /** A wheel event (or a finger's pixels) while the reader loads: up is positive here. */
          push: (e: WheelEvent | number) => {
            const { px, notch } = typeof e === 'number' ? { px: e, notch: false } : wheelPx(wheelMotion(e), rowH(), t.rows)
            s.push(-px, notch)
            if (!shown) return
            if (notch) { if (!raf) raf = requestAnimationFrame(tick) } else paint()
          },
          /** Back to no shift; what the screen was moved (`pos`) and where the input is going (`target`). */
          end: () => {
            if (raf) { cancelAnimationFrame(raf); raf = 0 }
            const out = shown ? { pos: s.pos, target: s.target } : { pos: 0, target: s.target }
            s.set(0, 0)
            shown = false
            paint()
            return out
          },
        }
      })()

      // The history taken ahead while the terminal rests (no output for a
      // moment), so a gesture that starts then waits for no round trip: only
      // the reader's xterm is made (a frame or two, the screen led meanwhile).
      // Good only while nothing came from the terminal since: its last rows
      // are the screen. Bounded: only while the pointer is over the terminal
      // (the wheel needs it there), one capture per rest, at most one every
      // AHEAD_EVERY_MS, only for a shown terminal of a visible page (a capture
      // holds tmux's one thread for every pane meanwhile); text only, nothing
      // in the page (an xterm made ahead would be one more .xterm-rows in the
      // window, and 2000 rows of it).
      let received = 0
      let ahead: { got: HistoryRows; at: number } | null = null
      let aheadTimer: ReturnType<typeof setTimeout> | null = null
      let aheadBusy = false
      let aheadLast = -AHEAD_EVERY_MS
      let over = false
      let kindTimer: ReturnType<typeof setTimeout> | null = null
      let kindPending = false
      let kindAskedAt = -Infinity
      const dropAhead = () => {
        if (aheadTimer) { clearTimeout(aheadTimer); aheadTimer = null }
        if (kindTimer) { clearTimeout(kindTimer); kindTimer = null }
        ahead = null
      }
      dropAheadRef.current = dropAhead
      const prepareAhead = () => {
        aheadTimer = null
        if (disposed || !over || aheadBusy || opening || readerRef.current || !smoothRef.current || !visibleRef.current || document.hidden) return
        if (ahead && ahead.at === received) return
        const wait = AHEAD_EVERY_MS - (performance.now() - aheadLast)
        if (wait > 0) { aheadTimer = setTimeout(prepareAhead, wait); return }
        aheadBusy = true
        aheadLast = performance.now()
        const at = received
        const version = paneKindVersion
        void fetchRows(sid, FIRST_ROWS)
          .then((got) => {
            if (disposed || received !== at || paneKindVersion !== version) return
            const f = got as unknown as PaneFlags
            learn(f)
            if (f.alt || f.mouse || f.in_mode) return
            ahead = { got, at }
          })
          .catch(() => undefined)
          .finally(() => { aheadBusy = false })
      }
      /** Output arrived: a reader made ahead is out of date; make one again once the terminal rests. */
      const restAhead = () => {
        received += 1
        if (backend !== 'tmux') return
        if (ahead && ahead.at !== received) ahead = null
        if (aheadTimer) clearTimeout(aheadTimer)
        aheadTimer = over ? setTimeout(prepareAhead, AHEAD_REST_MS) : null
        // Keep the last route while an agent streams. A command can still
        // open a pager later, so recheck even if the previous route was known.
        if (visibleRef.current && !kindPending && kindTimer === null) scheduleKind()
      }
      const scheduleKind = () => {
        const delay = Math.max(KIND_AFTER_OUTPUT_MS, KIND_REFRESH_MS - (performance.now() - kindAskedAt))
        kindTimer = setTimeout(askKind, delay)
      }
      // Ordinary output does not invalidate a reply. Input may have started
      // a different program while this request was in flight.
      const askKind = () => {
        kindTimer = null
        if (disposed || !visibleRef.current || document.hidden || kindPending) return
        if (performance.now() - kindAskedAt < KIND_REFRESH_MS) { scheduleKind(); return }
        kindPending = true
        kindAskedAt = performance.now()
        const version = paneKindVersion
        const at = received
        getJson<PaneFlags>(`/api/terminal/sessions/${encodeURIComponent(sid)}/pos`)
          .then((f) => { if (!disposed && paneKindVersion === version) learn(f) })
          .catch(() => undefined)
          .finally(() => {
            kindPending = false
            if (!disposed && visibleRef.current && !document.hidden && kindTimer === null
              && (received !== at || paneKindVersion !== version)) scheduleKind()
          })
      }
      const typedHere = () => {
        if (backend !== 'tmux') return
        paneKindVersion += 1
        paneKind = null
        tmuxSelecting = false
        if (kindTimer) clearTimeout(kindTimer)
        kindTimer = over ? setTimeout(askKind, KIND_AFTER_TYPING_MS) : null
      }
      if (backend === 'tmux') {
        const enter = () => {
          over = true
          if (!ahead && !aheadTimer) aheadTimer = setTimeout(prepareAhead, AHEAD_REST_MS)
          if (!paneKind && !kindTimer) askKind()
        }
        el.addEventListener('pointerenter', enter)
        // A terminal made under a pointer at rest (the window opened under it,
        // a tab switched by key) gets no pointerenter: Chromium counts the
        // pointer as already inside. It is over the terminal all the same.
        el.addEventListener('pointermove', () => { if (!over) enter() })
        if (el.matches(':hover')) enter()
        else askKind()
        el.addEventListener('pointerleave', () => {
          over = false
          if (aheadTimer) { clearTimeout(aheadTimer); aheadTimer = null }
          if (kindTimer) { clearTimeout(kindTimer); kindTimer = null }
        })
      }
      const wire = (r: Reader) => {
        enableTextSelection(r.term, () => false)
        hooksRef.current?.terminal?.(r.term, 'reader')
        // A collapsed message's row: a click opens it; the pointer says it can.
        const foldAtPoint = (ev: MouseEvent) => {
          const scr = r.el.querySelector('.xterm-screen') as HTMLElement | null
          if (!scr || !r.term.rows || !r.folds.length) return null
          const rect = scr.getBoundingClientRect()
          const row = Math.floor(((ev.clientY - rect.top) / rect.height) * r.term.rows)
          return row >= 0 && row < r.term.rows ? r.map.foldAt(r.term.buffer.active.viewportY + row) : null
        }
        r.el.addEventListener('click', (ev) => {
          if (ev.button !== 0 || ev.shiftKey || ev.ctrlKey || ev.metaKey || ev.altKey || r.term.hasSelection()) return
          const f = foldAtPoint(ev)
          if (!f) return
          setFolds(sid, [f.id], false, foldOrigin)
          void refold()
        })
        r.el.addEventListener('mousemove', (ev) => {
          if (!r.folds.length) return
          const scr = r.el.querySelector('.xterm-screen') as HTMLElement | null
          if (scr) scr.style.cursor = foldAtPoint(ev) ? 'pointer' : ''
        })
        r.term.attachCustomKeyEventHandler((e) => {
          if (e.type !== 'keydown') return true
          if (onDiagnosticsKey(e)) return false
          const what = readerKeeps(e, IS_MAC, r.term.hasSelection())
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
      const readerRow = (r: Reader, source: number) => {
        const row = r.map.toView(source)
        return r.map.toSrc(row) === source ? row : undefined
      }
      const carryReaderSelection = (r: Reader, next: Reader, offset = 0) => {
        transferTextSelection(r.term, next.term, (row) => readerRow(next, r.map.toSrc(row) + offset))
        if (document.activeElement === r.term.textarea) next.term.focus()
      }
      const show = (r: Reader, offset: number) => {
        r.el.style.visibility = 'visible'
        readerRef.current = r
        setReading(true)
        if (transferTextSelection(t, r.term, (row) => readerRow(r, row + offset))) {
          t.clearSelection()
          if (document.activeElement === t.textarea) r.term.focus()
        }
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
      /** The reader in front, at the pixel the live screen was led to, a glide under way going on. */
      const takeOver = (r: Reader) => {
        wire(r)
        const led = lead.end()
        const { max, rowH } = r.layer.where()
        if (!smoothRef.current && rowH > 0) r.layer.setPos(max - Math.round(led.target / rowH) * rowH)
        else {
          if (led.pos > 0) r.layer.setPos(max - led.pos)
          if (Math.abs(led.target - led.pos) > 0.01) r.layer.by(-(led.target - led.pos), true)
        }
        // tmux capture ends with the live pane. Its xterm is on a separate
        // buffer without the preceding history, so align those last rows.
        show(r, r.src.length - t.rows - t.buffer.active.viewportY)
      }
      /** A longer history follows, swapped in at the same line. */
      const longer = async (got: HistoryRows) => {
        if (got.complete) return
        const full = await fetchRows(sid, 50_000).catch(() => null)
        // The reader may have been made again meanwhile (a message collapsed): the same rows still.
        const holds = () => readerRef.current?.got === got ? readerRef.current : null
        if (!full || !holds() || disposed) return
        const r2 = await buildReader(make, el, t, full, foldOpts())
        const r = holds()
        if (!r || disposed) { r2.dispose(); return }
        // The same absolute line at the top: rows above r's first are (history - above).
        const w = r.layer.where()
        const at = topOf(r)
        wire(r2)
        placeAt(r2, at.src + (r.history - r.above) - (full.history - full.above), at.frac)
        // A glide under way goes on in the new reader.
        if (Math.abs(w.target - w.pos) > 0.01) r2.layer.by(w.target - w.pos, true)
        r2.el.style.visibility = 'visible'
        readerRef.current = r2
        carryReaderSelection(r, r2, (r.history - r.above) - (full.history - full.above))
        r.dispose()
      }
      const openReader = (px: number, first?: WheelEvent, rows = FIRST_ROWS) => {
        if (readerRef.current || opening || disposed) return
        // Taken ahead and still the screen: no round trip.
        const kept = ahead && ahead.at === received && rows === FIRST_ROWS ? ahead.got : null
        ahead = null
        opening = true
        pendingEvents = first ? [first] : []
        lead.start(paneKind === 'history')
        if (first || px) lead.push(first ?? px)
        void (kept ? Promise.resolve(kept) : fetchRows(sid, rows))
          .then(async (got) => {
            if (disposed) return
            const f = got as unknown as PaneFlags
            learn(f)
            if (f.alt || f.mouse || f.in_mode) {
              // Not the history: a full-screen program or one that reads the mouse gets the wheel.
              lead.end()
              flags = { at: performance.now(), alt: !!f.alt, mouse: !!f.mouse, in_mode: !!f.in_mode }
              lastWheel = performance.now()
              for (const ev of pendingEvents) route(ev, flags)
              return
            }
            const r = await buildReader(make, el, t, got, foldOpts())
            if (disposed) { r.dispose(); return }
            takeOver(r)
            await longer(got)
          })
          .catch(() => undefined)
          .finally(() => { opening = false; pendingEvents = []; lead.end() })
      }
      openReaderRef.current = openReader

      /** A plain terminal's history in a reader (it has collapsed messages): at the text the live view shows, a gesture under way going on. */
      const openPlain = async (first?: WheelEvent) => {
        if (readerRef.current || opening || disposed) return
        opening = true
        pendingEvents = []
        lead.start(false)
        if (first) lead.push(first)
        const live = layer.where()
        const top = live.rowH > 0 ? Math.floor(live.pos / live.rowH + 1e-6) : t.buffer.active.viewportY
        const frac = Math.max(0, live.pos - top * live.rowH)
        try {
          const r = await buildReader(make, el, t, plainRows(t), foldOpts())
          if (disposed) { r.dispose(); return }
          wire(r)
          const led = lead.end()
          placeAt(r, top, frac)
          if (Math.abs(led.target) > 0.01) r.layer.by(-led.target, true)
          // The live terminal waits at its newest line: the reader closes onto it.
          layer.bottom()
          show(r, 0)
        } catch { /* the live terminal stays */ } finally { opening = false; pendingEvents = []; lead.end() }
      }

      /** The collapsed messages changed: the reader made again at the same text (a plain terminal scrolled up gets one). */
      const refold = async () => {
        if (disposed || !smoothRef.current) return
        const r = readerRef.current
        if (!r) {
          const b = t.buffer.active
          if (backend !== 'tmux' && !foldsOffRef.current && hasFolds(sid) && layer.owns() && b.viewportY < b.baseY) await openPlain()
          return
        }
        const at = topOf(r)
        const w = r.layer.where()
        const r2 = await buildReader(make, el, t, r.got, foldOpts())
        if (readerRef.current !== r || disposed) { r2.dispose(); return }
        wire(r2)
        placeAt(r2, at.src, at.frac)
        if (Math.abs(w.target - w.pos) > 0.01) r2.layer.by(w.target - w.pos, true)
        r2.el.style.visibility = 'visible'
        readerRef.current = r2
        carryReaderSelection(r, r2)
        r.dispose()
        // The marks on the messages follow at once (MessageMenu's BlockMarks).
        window.dispatchEvent(new CustomEvent('sp-reader-swap'))
      }
      refoldRef.current = refold
      offFolds = onFolds((s, origin) => { if (s === sid && origin !== foldOrigin) void refold() })
      // The live terminal resized: the reader's rows no longer match it.
      t.onResize(() => { closeReader(); dropAhead() })
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
          // A reader in front (collapsed messages): it counts what came since.
          if (readerRef.current) return
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
      t.parser.registerOscHandler(52, receiveProgramCopy)
      const doFit = () => {
        if (!el.offsetWidth || !el.offsetHeight) return
        try { fit.fit() } catch { /* not laid out yet */ }
        // The size xterm drew, for the window's tests (the pty must get the same).
        el.dataset.cols = String(t.cols)
        el.dataset.rows = String(t.rows)
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
        if (onDiagnosticsKey(e)) return false
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
        if (letter(e) === 'c' && ((e.ctrlKey && e.shiftKey) || (IS_MAC && e.metaKey && !e.altKey))) {
          void copySelected()
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
      // A key or a paste is the operator's; a mouse or focus report and
      // xterm's answers to a program are not: they neither close the reader,
      // nor beat the timer, nor count as keys.
      const marker = new InputMarker()
      t.onKey(() => marker.key())
      t.onData((data) => {
        const typed = marker.typed(data)
        // Typed into the live terminal: the reader steps aside, and what the pane shows is asked again.
        if (typed && readerRef.current) closeReaderRef.current()
        if (typed) typedHere()
        if (ws?.readyState === WebSocket.OPEN) ws.send(JSON.stringify({ type: 'input', data, typed }))
        if (typed) onInputRef.current?.(data)
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
        logged?.socket(s)
        s.binaryType = 'arraybuffer'
        s.onopen = () => { tries = 0; doFit() }
        // The server opens every socket and refuses after (4401 and the rest):
        // only the terminal's first output says the token was taken.
        s.onmessage = (ev) => { authFails = 0; t.write(ev.data instanceof ArrayBuffer ? new Uint8Array(ev.data) : String(ev.data)); restAhead() }
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
      offFolds?.()
      logged?.dispose()
      layerRef.current?.dispose()
      layerRef.current = null
      readerRef.current?.dispose()
      readerRef.current = null
      dropAheadRef.current()
      document.fonts?.removeEventListener?.('loadingdone', fitRef.current)
      try { ws?.close() } catch { /* fine */ }
      // A terminal removed while it has the keyboard may never see its blur:
      // the timer must not go on counting it as the work at hand.
      if (term?.textarea && document.activeElement === term.textarea) setWork('terminal', null)
      if (term) disposeTerminal(term)
      api.current = null
      termRef.current = null
      searchRef.current = null
    }
    // One terminal per session: the size, scrollback and backend are read
    // when it is made (size changes go through api.size below), the callbacks
    // through refs. A new sid, token or project makes a new terminal.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [sid, token, project, captureDiagnostics])

  useEffect(() => { api.current?.size(fontSize) }, [fontSize])
  useEffect(() => {
    if (!visible) {
      // Hidden, kept mounted (the window's last tabs): the history reader goes
      // (it is a snapshot, and 50 000 rows of xterm), and so does the keyboard —
      // a hidden terminal must not go on taking keys or counting as the work at hand.
      closeReaderRef.current()
      dropAheadRef.current()
      const t = termRef.current
      if (t?.textarea && document.activeElement === t.textarea) t.blur()
      return
    }
    // Shown: fit once laid out (the box was display:none), then take the
    // keyboard. In tmux the focus also makes this view the latest client, so
    // the window takes this view's size again (window-size latest) even if
    // another view of the terminal was used meanwhile.
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

  const menuItem = 'w-full text-left px-10 min-h-[26px] py-2 text-12 text-[var(--term-soft)] hover:bg-white/10 hover:text-[var(--term-text)] inline-flex items-center gap-8 disabled:opacity-40'
  // Shift+right-click opens Screen's own menu. Keep both mouse reports away
  // from the pane, including on macOS where xterm does not reserve Shift.
  const takesMouse = (event: MouseEvent) => (event.button === 2 && event.shiftKey) || hooksRef.current?.mouse?.(event)

  return (
    <div className="relative w-full h-full min-h-0" style={{ background: TERMINAL_GROUND }}
      onContextMenu={(e) => {
        e.preventDefault()
        if (hooksRef.current?.contextMenu?.(e.nativeEvent)) return
        const r = e.currentTarget.getBoundingClientRect(); setMenu({ x: e.clientX - r.left, y: e.clientY - r.top })
      }}>
      <div ref={box} className="w-full h-full min-h-0 px-6 pt-4" style={{ display: visible ? 'block' : 'none' }}
        onWheelCapture={(e) => { if (e.deltaY < 0 || behind.up) watchTmux() }}
        onMouseMoveCapture={hintAt}
        onMouseLeave={() => setLinkHint(null)}
        onMouseUpCapture={(e) => { if (takesMouse(e.nativeEvent)) { e.preventDefault(); e.stopPropagation() } }}
        onMouseDownCapture={(e) => {
          if (takesMouse(e.nativeEvent)) { e.preventDefault(); e.stopPropagation(); return }
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
          <div role="menu" className="absolute z-20 w-[300px] max-w-full overflow-y-auto py-4 rounded-input border border-white/15 shadow-lg"
            style={{
              background: 'var(--term-bar)',
              left: Math.max(0, Math.min(menu.x, (box.current?.clientWidth ?? 300) - 310)),
              top: Math.max(0, Math.min(menu.y, (box.current?.clientHeight ?? 200) - 255)),
              maxHeight: box.current?.clientHeight ?? 200,
            }}>
            <button type="button" role="menuitem" className={menuItem} disabled={!selection() && backend !== 'tmux'}
              onClick={() => { void copySelected(); setMenu(null) }}>
              {tr('Copy')} <span className="ml-auto text-10 text-[var(--term-muted)]">{IS_MAC ? '⌘C' : 'Ctrl+Shift+C'}</span>
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
            <button type="button" role="menuitem" className={menuItem} onClick={() => { void captureDiagnostics(); setMenu(null) }}>
              <span>{tr('Capture terminal state (diagnostics)')}</span>
              {!IS_MAC && <span className="ml-auto whitespace-nowrap text-10 text-[var(--term-muted)]">Ctrl+Alt+Shift+D</span>}
            </button>
          </div>
        </>
      )}
    </div>
  )
}

/** The terminal's ground in the scheme (useApplyTermScheme sets --sp-term-bg on the page). */
export const TERMINAL_GROUND = 'var(--sp-term-bg, var(--term-ground))'
