/**
 * The terminal log, the page's half (tk_f89e84c4; the server's half is
 * backend/termlog.py). How the terminal works, to find its bugs and slowdowns.
 *
 * Light (the default): counters for the minute — frame times as a histogram
 * while output flows and while scrolling, long tasks, bytes in and out per
 * terminal, keys, pastes and their path, the wheel's path (smooth layer,
 * tmux reader, a full-screen program's rows, xterm's rows), socket
 * reconnects, errors, failed requests, the page's memory and the window's —
 * sent as one row a minute when something happened (a row every ten minutes
 * when nothing did), never per keystroke. The frame clock runs only while
 * something moves.
 *
 * Full (for bug hunting): all of that plus a stream of events with their
 * times — each key, paste, wheel, click, selection, socket message, frame
 * and the scroll offset of each frame — in a ring buffer (10 min, 30 000
 * events), sent every 10 s while Full is on.
 *
 * Never: what was typed, pasted or printed. Only kinds, sizes and times
 * leave the handlers. A paste's hash (to see the same paste twice) stays in
 * termRules.ts for 50 ms and is never stored or sent.
 */

import type { Terminal } from 'xterm'
import { BUCKETS, KEY_WAIT_MS, Rules, STALL_MS, bucketOf, hashOf, isReport, keyKind, routeOf, type Doing, type Finding } from './termRules'

export type LogMode = 'off' | 'light' | 'full'

const ROW_MS = 60_000
const FULL_MS = 10_000
const IDLE_ROW_MS = 10 * 60_000
const RING_MAX = 30_000
const RING_AGE_MS = 10 * 60_000
const ACTIVE_MS = 1000
const FINAL_CODES = new Set([1000, 4000, 4400, 4401, 4403, 4409, 4429, 4500])

/** [t ms, kind, sid, a, b] — a time, a kind, a terminal, a number, a number or a short word. */
export type LogEvent = [number, string, string, number | null, number | string | null]

interface Frames { h: number[]; max: number }
interface TermCount {
  p: string; b: string; in: number; out: number; keys: number; pastes: number; paste_bytes: number
  wheels: number; clicks: number; selections: number; resizes: number; msgs_in: number; msgs_out: number
}
interface Minute {
  t: number
  frames: Partial<Record<Doing, Frames>>
  longtasks: { n: number; max: number; ms: number }
  terms: Record<string, TermCount>
  scroll: Record<string, number>
  paste: Record<string, number>
  sock: { reconnects: number; down_ms: number; max_down_ms: number }
  errors: { js: number; fetch: number; xterm: number }
  fetch: Record<string, number>
  findings: Finding[]
}

export interface Attached {
  /** Every socket the screen opens: its messages counted, its sends watched. */
  socket: (ws: WebSocket) => void
  dispose: () => void
}

export interface AttachOptions {
  sid: string
  project: string
  backend: string
  el: HTMLElement
  term: Terminal
  /** Which path a wheel takes right now: smooth, reader, alt, rows. */
  scrollPath: () => string
  /** Where the view stands in px (Full: one reading a frame while scrolling). */
  offset?: () => number
}

type Spw = { spWindow?: { metrics?: () => Promise<Array<{ type: string; kb: number; cpu: number }> | null> } }

function emptyMinute(t: number): Minute {
  return {
    t: Math.floor(t / ROW_MS) * 60, frames: {}, longtasks: { n: 0, max: 0, ms: 0 }, terms: {}, scroll: {}, paste: {},
    sock: { reconnects: 0, down_ms: 0, max_down_ms: 0 }, errors: { js: 0, fetch: 0, xterm: 0 }, fetch: {}, findings: [],
  }
}

const now = () => Date.now()

function nonZero<T extends Record<string, number | string>>(o: T): Record<string, number | string> {
  const out: Record<string, number | string> = {}
  for (const [k, v] of Object.entries(o)) if (v !== 0 && v !== '') out[k] = v
  return out
}

export class TermLog {
  mode: LogMode = 'light'
  readonly page = Math.random().toString(36).slice(2, 8)
  private min: Minute = emptyMinute(now())
  private ring: LogEvent[] = []
  private sentSeq = 0
  private seq = 0
  private lastRow = 0
  private active = -Infinity
  private doing: Doing = 'idle'
  private doingSid = ''
  private raf = 0
  private lastFrame = 0
  private selfMs = 0
  private timers: number[] = []
  private installed = false
  private origFetch: typeof fetch | null = null
  private ourFetch: typeof fetch | null = null
  private observer: PerformanceObserver | null = null
  private terms = new Map<string, AttachOptions>()
  private pasteHint: { path: string; at: number } | null = null
  /** A terminal whose socket dropped: since when. */
  private down: Record<string, number> = {}
  /** When the window last got the focus back, the terminal last focused, Alt held down. */
  private focusAt = now()
  private lastSid = ''
  private altHeld = false
  readonly rules: Rules
  /** Where batches go: the page's own fetch, kept before the wrapper. */
  post: (body: string) => Promise<LogMode | null>

  constructor() {
    this.rules = new Rules((f) => this.finding(f))
    this.post = async (body) => {
      const f = this.origFetch ?? fetch
      const r = await f('/api/terminal/log', { method: 'POST', headers: { 'content-type': 'application/json' }, body, keepalive: body.length < 60_000 })
      if (!r.ok) return null
      const got = await r.json() as { mode?: LogMode }
      return got.mode ?? null
    }
  }

  /* ---------------------------------------------------------------- mode */

  setMode(m: LogMode) {
    if (m === this.mode && (m === 'off') === !this.installed) return
    this.mode = m
    if (m === 'off') { this.uninstall(); this.ring = []; this.min = emptyMinute(now()); this.selfMs = 0; return }
    if (m !== 'full') { this.ring = []; this.sentSeq = this.seq }
    this.install()
  }

  /* ------------------------------------------------------------ a screen */

  attach(o: AttachOptions): Attached {
    this.terms.set(o.sid, o)
    if (this.mode !== 'off') this.install()
    const offs: Array<() => void> = []
    const on = <K extends keyof HTMLElementEventMap>(type: K, fn: (e: HTMLElementEventMap[K]) => void) => {
      const h = (e: HTMLElementEventMap[K]) => { if (this.mode === 'off') return; const t0 = performance.now(); try { fn(e) } finally { this.selfMs += performance.now() - t0 } }
      o.el.addEventListener(type, h, { capture: true, passive: true })
      offs.push(() => o.el.removeEventListener(type, h, { capture: true }))
    }
    on('focusin', () => { this.lastSid = o.sid })
    on('keydown', () => { this.count(o.sid).keys++; this.rules.key(now()); this.busy('typing', o.sid); this.event('key', o.sid, null, null) })
    on('wheel', (e) => {
      const path = o.scrollPath()
      this.min.scroll[path] = (this.min.scroll[path] ?? 0) + 1
      this.count(o.sid).wheels++
      this.busy('scroll', o.sid)
      this.event('wheel', o.sid, Math.round(e.deltaY * 10) / 10, path)
    })
    on('mousedown', (e) => {
      if (e.button === 1) this.pasteHint = { path: 'middle', at: now() }
      this.count(o.sid).clicks++
      this.rules.click(o.sid, now())
      this.event('click', o.sid, e.button, null)
    })
    on('paste', (e) => {
      // Only its size: the text is not read further.
      this.pasteHint = { path: 'native', at: now() }
      this.event('paste-event', o.sid, e.clipboardData?.getData('text/plain').length ?? 0, null)
    })
    const sel = o.term.onSelectionChange(() => {
      if (this.mode === 'off' || !o.term.hasSelection()) return
      this.count(o.sid).selections++
      this.event('select', o.sid, o.term.getSelection().length, null)
    })
    const rs = o.term.onResize(({ cols, rows }) => {
      if (this.mode === 'off') return
      this.count(o.sid).resizes++
      this.event('resize', o.sid, cols, rows)
    })
    return {
      socket: (ws) => this.socket(o, ws),
      dispose: () => { offs.forEach((f) => f()); sel.dispose(); rs.dispose(); this.terms.delete(o.sid) },
    }
  }

  private socket(o: AttachOptions, ws: WebSocket) {
    const sid = o.sid
    const down = this.down
    // The prototype's send is looked up at each call, not kept: whatever wraps
    // WebSocket.prototype.send later (a test's spy) still sees every frame.
    const proto = Object.getPrototypeOf(ws) as { send: (d: unknown) => void }
    ws.send = (d: string | ArrayBufferLike | Blob | ArrayBufferView) => {
      if (this.mode !== 'off') {
        const t0 = performance.now()
        try { this.sent(o, d) } finally { this.selfMs += performance.now() - t0 }
      }
      proto.send.call(ws, d)
    }
    ws.addEventListener('message', (ev: MessageEvent) => {
      if (this.mode === 'off') return
      const t0 = performance.now()
      const n = ev.data instanceof ArrayBuffer ? ev.data.byteLength : String(ev.data).length
      const c = this.count(sid)
      c.in += n
      c.msgs_in++
      this.busy('output', sid)
      this.event('out', sid, n, null)
      this.selfMs += performance.now() - t0
    })
    ws.addEventListener('close', (ev: CloseEvent) => {
      if (this.mode === 'off') return
      this.event('sock-close', sid, ev.code, null)
      if (!FINAL_CODES.has(ev.code) && down[sid] == null) down[sid] = now()
    })
    ws.addEventListener('open', () => {
      if (this.mode === 'off') return
      const since = down[sid]
      this.event('sock-open', sid, since != null ? now() - since : 0, null)
      if (since == null) return
      delete down[sid]
      const ms = now() - since
      this.min.sock.reconnects++
      this.min.sock.down_ms += ms
      this.min.sock.max_down_ms = Math.max(this.min.sock.max_down_ms, ms)
      this.rules.reconnect(sid, o.project, ms, now(), this.doingNow())
    })
  }

  /** A message the screen sends: counted by kind and size; input's text is looked at only for its size and hash. */
  private sent(o: AttachOptions, d: unknown) {
    const c = this.count(o.sid)
    c.msgs_out++
    if (typeof d !== 'string') {
      this.rules.input(o.sid)
      const n = (d as ArrayBuffer).byteLength ?? 0
      c.out += n
      this.event('send', o.sid, n, 'bytes')
      return
    }
    type Msg = { type?: string; data?: unknown; typed?: unknown }
    let m: Msg | null = null
    try { m = JSON.parse(d) as Msg } catch { /* raw text */ }
    if (!m || m.type !== 'input' || typeof m.data !== 'string') {
      this.event('send', o.sid, d.length, m?.type ? String(m.type).slice(0, 12) : 'text')
      return
    }
    const data = m.data
    this.rules.input(o.sid)
    const typed = m.typed !== false
    c.out += data.length
    const at = now()
    this.rules.sent(o.sid, o.project, typed, data.length, at, isReport(data))
    const paste = typed && data.length > 1 && (data.startsWith('\x1b[200~') || !data.startsWith('\x1b'))
    if (paste) {
      const hint = this.pasteHint && at - this.pasteHint.at < 300 ? this.pasteHint.path : 'page'
      this.min.paste[hint] = (this.min.paste[hint] ?? 0) + 1
      c.pastes++
      c.paste_bytes += data.length
      this.busy('paste', o.sid)
      this.rules.paste(o.sid, o.project, hashOf(data), data.length, at, hint)
      this.event('paste', o.sid, data.length, hint)
    } else {
      this.event('input', o.sid, data.length, typed ? 'typed' : 'report')
    }
  }

  /* ------------------------------------------------------------ the page */

  private install() {
    if (this.installed || typeof window === 'undefined') return
    this.installed = true
    window.addEventListener('error', this.onError)
    window.addEventListener('unhandledrejection', this.onRejection)
    document.addEventListener('visibilitychange', this.onVisible)
    window.addEventListener('keydown', this.onWindowKey, { capture: true, passive: true })
    window.addEventListener('keyup', this.onWindowKeyUp, { capture: true, passive: true })
    window.addEventListener('focus', this.onWindowFocus)
    this.focusAt = now()
    // Requests: a failed one, or a 5xx, of any page with a terminal.
    if (!this.origFetch) {
      this.origFetch = window.fetch.bind(window)
      const orig = this.origFetch
      this.ourFetch = (async (input: RequestInfo | URL, init?: RequestInit) => {
        const url = typeof input === 'string' ? input : input instanceof URL ? input.href : input.url
        const watch = this.mode !== 'off' && url.includes('/api/') && !url.includes('/api/terminal/log')
        if (!watch) return orig(input, init)
        const t0 = performance.now()
        try {
          const r = await orig(input, init)
          this.request(url, r.status, performance.now() - t0, init?.method)
          return r
        } catch (e) {
          if ((e as Error)?.name !== 'AbortError') this.request(url, 0, performance.now() - t0, init?.method)
          throw e
        }
      }) as typeof fetch
      window.fetch = this.ourFetch
    }
    try {
      this.observer = new PerformanceObserver((list) => {
        for (const e of list.getEntries()) this.longtask(e.duration)
      })
      this.observer.observe({ type: 'longtask', buffered: false })
    } catch { this.observer = null }
    this.timers.push(window.setInterval(() => void this.tick(), FULL_MS))
    window.addEventListener('pagehide', this.onHide)
  }

  private uninstall() {
    if (!this.installed) return
    this.installed = false
    window.removeEventListener('error', this.onError)
    window.removeEventListener('unhandledrejection', this.onRejection)
    document.removeEventListener('visibilitychange', this.onVisible)
    window.removeEventListener('keydown', this.onWindowKey, { capture: true })
    window.removeEventListener('keyup', this.onWindowKeyUp, { capture: true })
    window.removeEventListener('focus', this.onWindowFocus)
    window.removeEventListener('pagehide', this.onHide)
    if (this.ourFetch && window.fetch === this.ourFetch && this.origFetch) window.fetch = this.origFetch
    this.ourFetch = null
    this.origFetch = null
    this.observer?.disconnect()
    this.observer = null
    this.timers.forEach((t) => window.clearInterval(t))
    this.timers = []
    if (this.raf) cancelAnimationFrame(this.raf)
    this.raf = 0
  }

  private onError = (e: ErrorEvent) => {
    if (this.mode === 'off') return
    const where = (e.filename ?? '').split('/').pop() ?? ''
    const xterm = /xterm/i.test(e.filename ?? '') || /xterm/i.test(String(e.error?.stack ?? ''))
    if (xterm) this.min.errors.xterm++
    else this.min.errors.js++
    this.finding({ t: now(), kind: 'error', sid: this.doingSid, p: this.projectOf(this.doingSid), doing: this.doingNow(), n: e.lineno ?? 0, what: `${String(e.message ?? '').slice(0, 80)} ${where}`.trim() })
  }

  private onRejection = (e: PromiseRejectionEvent) => {
    if (this.mode === 'off') return
    const r = e.reason as { name?: string; message?: string } | undefined
    this.min.errors.js++
    this.finding({ t: now(), kind: 'error', sid: this.doingSid, p: this.projectOf(this.doingSid), doing: this.doingNow(), n: 0, what: `${r?.name ?? 'rejection'}: ${String(r?.message ?? '').slice(0, 80)}` })
  }

  private onVisible = () => { this.lastFrame = 0; if (!document.hidden) this.focusAt = now() }
  private onWindowFocus = () => { this.focusAt = now() }
  private onWindowKeyUp = (e: KeyboardEvent) => { if (e.key === 'Alt') this.altHeld = false }

  /**
   * A key pressed in the window that should reach a terminal's shell; none
   * came within KEY_WAIT_MS: `keys-lost` (termRules). Known reasons are not
   * findings: an IME composing, a shortcut (Ctrl, Alt, Meta), typing in
   * another box of the page, the tmux history view open (it closes and
   * hands the key on). Only the key's kind is kept, never the character.
   */
  private onWindowKey = (e: KeyboardEvent) => {
    if (this.mode === 'off') return
    const t0 = performance.now()
    try {
      if (e.key === 'Alt') { this.altHeld = true; return }
      if (e.isComposing || e.key === 'Process' || e.key === 'Dead' || e.ctrlKey || e.metaKey || e.altKey) return
      if (typeof document.hasFocus === 'function' && !document.hasFocus()) return
      if (!(e.key.length === 1 || ['Enter', 'Backspace', 'Tab'].includes(e.key))) return
      const active = document.activeElement as HTMLElement | null
      let o: AttachOptions | undefined
      for (const x of this.terms.values()) if (active && x.el.contains(active)) o = x
      if (!o) {
        // The focus is on another box or control of the page: its keys, not lost ones.
        if (active && (active.isContentEditable || ['INPUT', 'TEXTAREA', 'SELECT', 'BUTTON', 'A'].includes(active.tagName))) return
        const last = this.terms.get(this.lastSid)
        o = last && last.el.offsetParent !== null ? last : [...this.terms.values()].find((x) => x.el.offsetParent !== null)
      }
      if (!o || o.scrollPath() === 'reader') return
      const at = now()
      const where = active === o.term.textarea ? 'terminal' : active && o.el.contains(active) ? 'in-terminal' : (active?.tagName ?? 'none').toLowerCase()
      const screen = o.term.buffer?.active?.type === 'alternate' ? ' alt-screen' : ''
      const what = `${keyKind(e)} · focus=${where} · ${o.backend}${screen}${this.altHeld ? ' · alt-view' : ''}`
      this.rules.keyExpected(o.sid, o.project, at, what, at - this.focusAt)
      window.setTimeout(() => this.rules.keysDue(now()), KEY_WAIT_MS + 20)
    } finally { this.selfMs += performance.now() - t0 }
  }
  private onHide = () => { void this.flush(true) }

  private request(url: string, status: number, ms: number, method?: string) {
    const route = routeOf(url)
    if (status === 0 || status >= 400) {
      const key = `${(method ?? 'GET').toUpperCase()} ${route} ${status}`
      this.min.fetch[key] = (this.min.fetch[key] ?? 0) + 1
      if (status === 0 || status >= 500) this.min.errors.fetch++
      this.rules.fetch(this.doingSid, this.projectOf(this.doingSid), route, status, ms, now(), this.doingNow())
    }
    if (this.mode === 'full' && route.startsWith('/api/terminal')) this.event('req', this.doingSid, Math.round(ms), `${status} ${route}`.slice(0, 40))
  }

  private longtask(ms: number) {
    if (this.mode === 'off') return
    const lt = this.min.longtasks
    lt.n++
    lt.ms += ms
    lt.max = Math.max(lt.max, ms)
    this.event('longtask', this.doingSid, Math.round(ms), this.doingNow())
    this.rules.stall(this.doingSid, this.projectOf(this.doingSid), ms, this.doingNow(), now(), 'long task')
  }

  /* ------------------------------------------------------------- frames */

  /** Something moved: the frame clock runs while it does. */
  busy(d: Doing, sid: string) {
    const at = now()
    // Scrolling wins over output for a moment: a stall while scrolling is what matters.
    if (!(this.doing === 'scroll' && d === 'output' && at - this.active < 300)) this.doing = d
    this.doingSid = sid
    this.active = at
    if (!this.raf && this.mode !== 'off' && typeof requestAnimationFrame !== 'undefined') {
      this.lastFrame = 0
      this.raf = requestAnimationFrame(this.frame)
    }
  }

  private frame = (ts: number) => {
    this.raf = 0
    if (this.mode === 'off') return
    const t0 = performance.now()
    if (this.lastFrame && !document.hidden) {
      const dt = ts - this.lastFrame
      if (dt > 0 && dt < 5000) {
        const d = this.doingNow()
        const f = (this.min.frames[d] ??= { h: new Array(BUCKETS).fill(0), max: 0 })
        f.h[bucketOf(dt)]!++
        if (dt > f.max) f.max = dt
        if (dt > STALL_MS) this.rules.stall(this.doingSid, this.projectOf(this.doingSid), dt, d, now(), 'frame')
        if (this.mode === 'full') {
          this.event('frame', this.doingSid, Math.round(dt * 10) / 10, d)
          const o = this.terms.get(this.doingSid)
          if (d === 'scroll' && o?.offset) this.event('offset', this.doingSid, Math.round(o.offset() * 10) / 10, null)
        }
      }
    }
    this.lastFrame = ts
    if (now() - this.active < ACTIVE_MS) this.raf = requestAnimationFrame(this.frame)
    this.selfMs += performance.now() - t0
  }

  doingNow(): Doing {
    return now() - this.active < ACTIVE_MS ? this.doing : 'idle'
  }

  /* ------------------------------------------------------------ records */

  private count(sid: string): TermCount {
    const o = this.terms.get(sid)
    return (this.min.terms[sid] ??= {
      p: o?.project ?? '', b: o?.backend ?? '', in: 0, out: 0, keys: 0, pastes: 0, paste_bytes: 0,
      wheels: 0, clicks: 0, selections: 0, resizes: 0, msgs_in: 0, msgs_out: 0,
    })
  }

  private projectOf(sid: string): string { return this.terms.get(sid)?.project ?? '' }

  private finding(f: Finding) {
    if (this.mode === 'off') return
    if (this.min.findings.length < 50) this.min.findings.push(f)
    this.event('finding', f.sid, f.n, f.kind)
  }

  /** Full only: one event into the ring, bounded by count and age. */
  event(kind: string, sid: string, a: number | null, b: number | string | null) {
    if (this.mode !== 'full') return
    const t = now()
    this.ring.push([t, kind, sid, a, b])
    this.seq++
    if (this.ring.length > RING_MAX || t - this.ring[0]![0] > RING_AGE_MS) {
      const cut = Math.max(this.ring.length - RING_MAX, this.ring.findIndex((e) => t - e[0] <= RING_AGE_MS))
      if (cut > 0) this.ring.splice(0, cut)
    }
  }

  /** What Full holds now (the ring), newest last. */
  events(): readonly LogEvent[] { return this.ring }

  /** The minute so far as the row the server keeps; null when nothing happened. */
  row(at = now()): Record<string, unknown> | null {
    if (this.mode === 'off') return null
    const m = this.min
    const busy = Object.keys(m.frames).length || Object.keys(m.terms).length || m.findings.length
      || m.errors.js || m.errors.fetch || m.errors.xterm || m.longtasks.n
    if (!busy && at - this.lastRow < IDLE_ROW_MS) return null
    const frames: Record<string, Frames> = {}
    for (const [k, v] of Object.entries(m.frames)) frames[k] = { h: v.h, max: Math.round(v.max) }
    const lt = m.longtasks
    // Zeros are left out: a day of rows stays under a megabyte.
    const terms: Record<string, Record<string, number | string>> = {}
    for (const [sid, c] of Object.entries(m.terms)) terms[sid] = nonZero(c as unknown as Record<string, number | string>)
    const row: Record<string, unknown> = {
      t: m.t, where: /SlightlyParallelWindow/.test(navigator.userAgent) ? 'window' : 'browser', frames,
      longtasks: nonZero({ n: lt.n, max: Math.round(lt.max), ms: Math.round(lt.ms) }),
      terms, scroll: m.scroll, paste: m.paste, sock: nonZero(m.sock), errors: nonZero(m.errors), fetch: m.fetch,
      findings: m.findings, self: { ms: Math.round(this.selfMs * 10) / 10, events: this.ring.length },
    }
    for (const k of Object.keys(row)) {
      const v = row[k]
      if (v && typeof v === 'object' && !Array.isArray(v) && !Object.keys(v).length) delete row[k]
      if (Array.isArray(v) && !v.length) delete row[k]
    }
    return row
  }

  /** The minute ends: its frame budget is judged, a fresh one starts. */
  private roll(at: number) {
    for (const [d, f] of Object.entries(this.min.frames)) this.rules.minute(f.h, f.max, d as Doing, at, this.doingSid, this.projectOf(this.doingSid))
  }

  private async tick() {
    const at = now()
    const rowDue = at - this.lastRow >= ROW_MS || Math.floor(at / ROW_MS) * 60 !== this.min.t
    if (rowDue || (this.mode === 'full' && this.seq > this.sentSeq)) await this.flush(false, rowDue)
  }

  /** Send what is due: the minute's row (when it is due or the page hides) and Full's new events. */
  async flush(hiding = false, rowDue = true): Promise<void> {
    if (this.mode === 'off') return
    const at = now()
    let rows: unknown[] = []
    if (rowDue || hiding) {
      this.roll(at)
      const r = this.row(at)
      if (r) {
        r.mem = await this.memory()
        rows = [r]
        this.lastRow = at
      }
      this.min = emptyMinute(at)
      this.selfMs = 0
    }
    const fresh = this.mode === 'full' ? this.ring.slice(Math.max(0, this.ring.length - (this.seq - this.sentSeq))) : []
    this.sentSeq = this.seq
    if (!rows.length && !fresh.length) return
    try {
      const got = await this.post(JSON.stringify({ page: this.page, rows, events: fresh.slice(-20_000) }))
      if (got && got !== this.mode) this.setMode(got)
    } catch { /* the server is away: this minute is lost, the next is kept */ }
  }

  private async memory(): Promise<Record<string, unknown>> {
    const pm = (performance as unknown as { memory?: { usedJSHeapSize: number; jsHeapSizeLimit: number } }).memory
    const out: Record<string, unknown> = {}
    if (pm) { out.heap = pm.usedJSHeapSize; out.heap_limit = pm.jsHeapSizeLimit }
    const w = (window as unknown as Spw).spWindow
    if (w?.metrics) {
      try {
        const procs = await w.metrics()
        if (procs) {
          out.app_kb = procs.reduce((a, p) => a + (p.kb || 0), 0)
          out.procs = procs.slice(0, 20).map((p) => ({ type: p.type, kb: p.kb, cpu: Math.round(p.cpu * 10) / 10 }))
        }
      } catch { /* an older window: no metrics */ }
    }
    return out
  }
}

/** The page's one log, shared by every screen on it. */
export const termLog = new TermLog()

let asked = false
/** The mode the server holds, once per page (the settings switch it after). */
export function startTermLog(): void {
  if (asked || typeof window === 'undefined') return
  asked = true
  ;(window as unknown as { __spTermLog?: TermLog }).__spTermLog = termLog
  void fetch('/api/terminal/log/mode').then((r) => (r.ok ? r.json() : null)).then((m: { mode?: LogMode } | null) => {
    if (m?.mode) termLog.setMode(m.mode)
  }).catch(() => undefined)
}
