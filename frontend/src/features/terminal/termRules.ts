/**
 * The terminal log's rules (tk_f89e84c4): signals in, findings out. Each
 * rule is a bug found by hand on 18 Nov, so the log shows it next time
 * without anyone noticing it first:
 *
 * - `paste-twice`  — the same paste sent twice within 50 ms (Ctrl+Shift+V
 *   pasted by the page and by Chromium both);
 * - `scroll-stall` — a frame or a long task over 200 ms while scrolling
 *   (the jerky scroll; the scroll that froze after a click on a path);
 * - `reconnect`    — the terminal's socket dropped and came back;
 * - `fetch`        — a request of the terminal that failed ("failed to fetch"
 *   while the server restarted) or that the server answered with a 5xx;
 * - `click-typed`  — a mouse or focus report counted as typing (in tmux a
 *   click sends a mouse report, and it beat the timer: mouse clicks counted
 *   as typing time). A paste by a middle click is typing, not this;
 * - `slow-frames`  — a minute whose frame p95 was over budget;
 * - `keys-lost`    — a key pressed in the window while it had focus, and no
 *   input reached the socket within 300 ms (tk_184f61e4: after switching
 *   windows and back, the first keys typed did not appear). Recorded with the
 *   time since the window got the focus back, what had the focus, the views
 *   open, the key's kind (never the character) and the terminal's mode.
 *
 * Pure: no DOM, no clock of its own. What a finding holds is kinds, sizes
 * and times, never the text.
 */

export type Doing = 'scroll' | 'output' | 'paste' | 'typing' | 'idle'

export interface Finding {
  /** ms since the epoch. */
  t: number
  kind: 'paste-twice' | 'scroll-stall' | 'reconnect' | 'fetch' | 'click-typed' | 'slow-frames' | 'error' | 'keys-lost'
  sid: string
  /** The terminal's project. */
  p: string
  /** What was going on: scrolling, output, a paste, typing. */
  doing: Doing
  /** The number that matters: ms of the stall, bytes of the paste, ms down. */
  n: number
  /** A short word: the route and status, the paste's path, the error's first words. */
  what: string
}

/** Frame-time buckets, ms: the server's (termlog.EDGES). */
export const EDGES = [8, 12, 17, 20, 25, 34, 50, 75, 100, 150, 200, 300, 500, 1000] as const
export const BUCKETS = EDGES.length + 1

export function bucketOf(ms: number): number {
  for (let i = 0; i < EDGES.length; i++) if (ms < EDGES[i]!) return i
  return EDGES.length
}

/** The bucket edge under which `q` of the frames fall. */
export function percentile(hist: number[], q: number, top = 0): number {
  const total = hist.reduce((a, b) => a + b, 0)
  if (!total) return 0
  let run = 0
  for (let i = 0; i < hist.length; i++) {
    run += hist[i]!
    if (run >= q * total) return i < EDGES.length ? EDGES[i]! : Math.max(top, EDGES[EDGES.length - 1]!)
  }
  return top
}

export const PASTE_TWICE_MS = 50
export const STALL_MS = 200
export const CLICK_MS = 150
export const FRAME_BUDGET_MS = 50
export const MIN_FRAMES = 30
export const KEY_WAIT_MS = 300

export class Rules {
  private lastPaste: { h: number; n: number; at: number; sid: string } | null = null
  private lastClick: { at: number; sid: string } | null = null
  private lastKey = -Infinity
  private lastStall = -Infinity
  /** A key that should have sent input, per terminal: when, and what to say if none came. */
  private waiting = new Map<string, { at: number; p: string; what: string; n: number; count: number }>()
  private readonly emit: (f: Finding) => void
  constructor(emit: (f: Finding) => void) {
    this.emit = emit
  }

  /** A paste was sent (its hash and size only: the hash never leaves here). */
  paste(sid: string, p: string, h: number, n: number, at: number, path: string) {
    const last = this.lastPaste
    if (last && last.sid === sid && last.h === h && last.n === n && at - last.at <= PASTE_TWICE_MS) {
      this.emit({ t: at, kind: 'paste-twice', sid, p, doing: 'paste', n, what: path })
      this.lastPaste = null
      return
    }
    this.lastPaste = { h, n, at, sid }
  }

  click(sid: string, at: number) { this.lastClick = { at, sid } }
  key(at: number) { this.lastKey = at; this.lastClick = null }

  /** Input sent to the shell; `typed` as the page marked it (counted as
   *  typing), `report` when its bytes are only mouse or focus reports. */
  sent(sid: string, p: string, typed: boolean, n: number, at: number, report: boolean) {
    if (!typed || !report) return
    const c = this.lastClick
    const click = !!c && c.sid === sid && at - c.at <= CLICK_MS && this.lastKey < c.at
    if (click) this.lastClick = null
    this.emit({ t: at, kind: 'click-typed', sid, p, doing: 'typing', n, what: click ? 'click' : 'report' })
  }

  /** A key that should reach the shell: printable, space, Enter, Backspace, Tab, with no shortcut modifier. */
  keyExpected(sid: string, p: string, at: number, what: string, sinceFocusMs: number) {
    const w = this.waiting.get(sid)
    if (w) { w.count++; return }
    this.waiting.set(sid, { at, p, what, n: Math.round(sinceFocusMs), count: 1 })
  }

  /** Input reached the socket for this terminal: whatever key waited has arrived. */
  input(sid: string) { this.waiting.delete(sid) }

  /** A key whose input never came within KEY_WAIT_MS is a finding. */
  keysDue(at: number) {
    for (const [sid, w] of this.waiting) {
      if (at - w.at < KEY_WAIT_MS) continue
      this.waiting.delete(sid)
      this.emit({ t: w.at, kind: 'keys-lost', sid, p: w.p, doing: 'typing', n: w.n, what: `${w.what}${w.count > 1 ? ` · ${w.count} keys` : ''}`.slice(0, 120) })
    }
  }

  /** A frame, or a long task, of `ms` while `doing`. One stall a second at most. */
  stall(sid: string, p: string, ms: number, doing: Doing, at: number, what: string) {
    if (doing !== 'scroll' || ms <= STALL_MS || at - this.lastStall < 1000) return
    this.lastStall = at
    this.emit({ t: at, kind: 'scroll-stall', sid, p, doing, n: Math.round(ms), what })
  }

  reconnect(sid: string, p: string, downMs: number, at: number, doing: Doing) {
    this.emit({ t: at, kind: 'reconnect', sid, p, doing, n: Math.round(downMs), what: 'socket' })
  }

  /** A request that failed (status 0: no answer) or a 5xx. */
  fetch(sid: string, p: string, route: string, status: number, ms: number, at: number, doing: Doing) {
    if (status !== 0 && status < 500) return
    this.emit({ t: at, kind: 'fetch', sid, p, doing, n: Math.round(ms), what: `${route} ${status || 'no answer'}` })
  }

  /** The end of a minute: a p95 over budget, with frames enough to say so. */
  minute(hist: number[], top: number, doing: Doing, at: number, sid: string, p: string) {
    const n = hist.reduce((a, b) => a + b, 0)
    if (n < MIN_FRAMES) return
    const p95 = percentile(hist, 0.95, top)
    if (p95 > FRAME_BUDGET_MS) this.emit({ t: at, kind: 'slow-frames', sid, p, doing, n: p95, what: `${n} frames` })
  }
}

/**
 * A key's kind, never its character: Enter, Backspace, Tab, space,
 * modifier, a digit key with or without Shift ("Shift+3 printable": "#"),
 * letter, printable, other. Names a digit key, which the "#" case needs, and
 * no letter.
 */
export function keyKind(e: { key: string; code: string; shiftKey: boolean; ctrlKey: boolean; altKey: boolean; metaKey: boolean }): string {
  const mods = `${e.ctrlKey ? 'Ctrl+' : ''}${e.altKey ? 'Alt+' : ''}${e.metaKey ? 'Meta+' : ''}${e.shiftKey ? 'Shift+' : ''}`
  if (['Shift', 'Control', 'Alt', 'Meta', 'AltGraph', 'CapsLock'].includes(e.key)) return 'modifier'
  if (e.key === ' ') return `${mods}space`
  if (['Enter', 'Backspace', 'Tab', 'Escape'].includes(e.key)) return `${mods}${e.key}`
  if (e.key.length === 1) {
    if (/^Digit\d$/.test(e.code)) return `${mods}${e.code.slice(5)} printable`
    if (/^Key[A-Z]$/.test(e.code)) return `${mods}letter`
    return `${mods}printable`
  }
  return 'other'
}

const ESC_ = '\u001b'
const REPORTS = new RegExp(`^(?:${ESC_}\\[<\\d+;\\d+;\\d+[Mm]|${ESC_}\\[M[\\s\\S]{3}|${ESC_}\\[[IO])+$`)

/** Input that is only mouse reports (SGR, X10) or focus in/out: what a click sends, never a key. */
export function isReport(data: string): boolean {
  return REPORTS.test(data)
}

/** FNV-1a of a string: tells two pastes apart without keeping either. */
export function hashOf(s: string): number {
  let h = 0x811c9dc5
  for (let i = 0; i < s.length; i++) {
    h ^= s.charCodeAt(i)
    h = Math.imul(h, 0x01000193)
  }
  return h >>> 0
}

/** A request's route with its ids folded: /api/terminal/sessions/:id/open. */
export function routeOf(url: string): string {
  let path = url
  try { path = new URL(url, 'http://x').pathname } catch { /* a bare path */ }
  return path.split('/').map((s) => (/\d/.test(s) && s.length >= 6) || /^\d+$/.test(s) ? ':id' : s).join('/').slice(0, 80)
}
