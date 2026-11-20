/**
 * The terminal log (tk_f89e84c4): each rule catches its bug of 18 Nov and
 * stays quiet on the good case; the minute's counters add up; Full's ring is
 * bounded; and nothing typed, pasted or printed ever leaves the page.
 */

import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import type { Terminal } from 'xterm'
import { Rules, bucketOf, hashOf, isReport, keyKind, percentile, routeOf, EDGES, type Finding } from './termRules'
import { TermLog } from './telemetry'

const SECRET = 'hunter2-S3CRET-correct-horse'

function rules() {
  const got: Finding[] = []
  return { r: new Rules((f) => got.push(f)), got }
}

describe('the rules, each against its known case', () => {
  it('paste-twice: Ctrl+Shift+V pasted by the page and by Chromium, 3 ms apart', () => {
    const { r, got } = rules()
    const h = hashOf('npm run build\n')
    r.paste('t1', 'alpha', h, 14, 1000, 'page')
    r.paste('t1', 'alpha', h, 14, 1003, 'native')
    expect(got.map((f) => f.kind)).toEqual(['paste-twice'])
    expect(got[0]!.n).toBe(14)
  })
  it('paste-twice: the same text pasted again a second later is two pastes, not a bug', () => {
    const { r, got } = rules()
    const h = hashOf('ls\n')
    r.paste('t1', '', h, 3, 1000, 'native')
    r.paste('t1', '', h, 3, 2000, 'native')
    r.paste('t1', '', hashOf('pwd\n'), 4, 2010, 'native')
    expect(got).toEqual([])
  })

  it('scroll-stall: a 240 ms frame while scrolling (the freeze after a click on a path)', () => {
    const { r, got } = rules()
    r.stall('t1', 'alpha', 240, 'scroll', 5000, 'frame')
    r.stall('t1', 'alpha', 300, 'scroll', 5100, 'long task') // the same stall: one finding a second
    expect(got.map((f) => [f.kind, f.n, f.doing])).toEqual([['scroll-stall', 240, 'scroll']])
  })
  it('scroll-stall: a slow frame while output flows, or a 150 ms one while scrolling, is not', () => {
    const { r, got } = rules()
    r.stall('t1', '', 400, 'output', 5000, 'frame')
    r.stall('t1', '', 150, 'scroll', 7000, 'frame')
    expect(got).toEqual([])
  })

  it('reconnect: a dropped socket that came back', () => {
    const { r, got } = rules()
    r.reconnect('t1', 'alpha', 3200, 9000, 'idle')
    expect(got[0]).toMatchObject({ kind: 'reconnect', n: 3200 })
  })

  it('fetch: "failed to fetch" while the server restarted, and a 502; not a 404', () => {
    const { r, got } = rules()
    r.fetch('t1', 'alpha', '/api/terminal/sessions/:id/open', 0, 12, 1, 'scroll')
    r.fetch('t1', 'alpha', '/api/terminal/sessions/:id/pos', 502, 40, 2, 'scroll')
    r.fetch('t1', 'alpha', '/api/terminal/sessions/:id', 404, 3, 3, 'idle')
    expect(got.map((f) => f.what)).toEqual(['/api/terminal/sessions/:id/open no answer', '/api/terminal/sessions/:id/pos 502'])
  })

  it('click-typed: a click whose mouse report was counted as typing', () => {
    const { r, got } = rules()
    const report = '\x1b[<0;5;5M\x1b[<0;5;5m'
    expect(isReport(report)).toBe(true)
    r.click('t1', 1000)
    r.sent('t1', 'alpha', true, report.length, 1004, isReport(report))   // marked typed: the bug
    expect(got.map((f) => [f.kind, f.what])).toEqual([['click-typed', 'click']])
  })
  it('click-typed: a report marked not typed, a key after a click, or a middle-click paste is fine', () => {
    const { r, got } = rules()
    r.click('t1', 1000)
    r.sent('t1', '', false, 9, 1004, true)
    r.click('t1', 2000)
    r.key(2050)
    r.sent('t1', '', true, 1, 2060, isReport('l'))
    r.click('t1', 3000)                    // a middle click pastes: typed, right after a click, and not a report
    r.sent('t1', '', true, 18, 3030, isReport('\x1b[200~echo hi\x1b[201~'))
    expect(got).toEqual([])
  })

  it('slow-frames: a minute of scrolling whose p95 was 75 ms; not a smooth minute, not 10 frames', () => {
    const { r, got } = rules()
    const slow = new Array(EDGES.length + 1).fill(0)
    slow[bucketOf(16)] = 20; slow[bucketOf(60)] = 40
    r.minute(slow, 70, 'scroll', 1, 't1', '')
    const fine = new Array(EDGES.length + 1).fill(0)
    fine[bucketOf(16)] = 300; fine[bucketOf(60)] = 3
    r.minute(fine, 60, 'scroll', 2, 't1', '')
    const few = new Array(EDGES.length + 1).fill(0)
    few[bucketOf(400)] = 10
    r.minute(few, 400, 'scroll', 3, 't1', '')
    expect(got.map((f) => [f.kind, f.n])).toEqual([['slow-frames', 75]])
  })

  it('reads routes with their ids folded, and percentiles off the bucket edges', () => {
    expect(routeOf('/api/terminal/sessions/t-8f3a21/open?x=1')).toBe('/api/terminal/sessions/:id/open')
    expect(routeOf('http://127.0.0.1:8123/api/tasks/42')).toBe('/api/tasks/:id')
    const h = new Array(EDGES.length + 1).fill(0)
    h[bucketOf(10)] = 50; h[bucketOf(16)] = 45; h[bucketOf(2000)] = 5
    expect(percentile(h, 0.5)).toBe(12)
    expect(percentile(h, 0.9)).toBe(17)
    expect(percentile(h, 0.99, 2000)).toBe(2000)
  })
})

/* ------------------------------------------------------- the collector */

class FakeSocket extends EventTarget {
  sent: unknown[] = []
  send(d: unknown) { this.sent.push(d) }
}

function fakeTerm(selection = '') {
  const subs: Record<string, Array<(x: unknown) => void>> = { sel: [], resize: [] }
  return {
    term: {
      onSelectionChange: (f: () => void) => { subs.sel!.push(f); return { dispose: () => {} } },
      onResize: (f: (x: unknown) => void) => { subs.resize!.push(f); return { dispose: () => {} } },
      hasSelection: () => !!selection,
      getSelection: () => selection,
    } as unknown as Terminal,
    select: () => subs.sel!.forEach((f) => f(undefined)),
  }
}

function setup(mode: 'light' | 'full' = 'light') {
  const log = new TermLog()
  const bodies: string[] = []
  log.post = async (b) => { bodies.push(b); return null }
  log.setMode(mode)
  const el = document.createElement('div')
  document.body.appendChild(el)
  const { term, select } = fakeTerm(SECRET)
  const a = log.attach({ sid: 't-1', project: 'alpha', backend: 'tmux', el, term, scrollPath: () => 'smooth', offset: () => 12.5 })
  const ws = new FakeSocket()
  a.socket(ws as unknown as WebSocket)
  return { log, bodies, el, ws, a, select }
}

const frame = (log: TermLog, ts: number) => (log as unknown as { frame: (t: number) => void }).frame(ts)

describe('the collector', () => {
  let origFetch: typeof fetch
  beforeEach(() => { origFetch = window.fetch })
  afterEach(() => { window.fetch = origFetch; vi.useRealTimers() })

  it('counts a minute: bytes in and out, keys, wheels, frames by what was going on', async () => {
    const { log, bodies, el, ws, a } = setup()
    ws.dispatchEvent(new MessageEvent('message', { data: new ArrayBuffer(4096) }))
    el.dispatchEvent(new KeyboardEvent('keydown', { key: 'a' }))
    ;(ws as unknown as WebSocket).send(JSON.stringify({ type: 'input', data: 'a', typed: true }))
    el.dispatchEvent(new WheelEvent('wheel', { deltaY: -30 }))
    for (let i = 1; i <= 10; i++) frame(log, i * 16.7)
    await log.flush()
    const row = JSON.parse(bodies[0]!).rows[0]
    expect(row.terms['t-1']).toMatchObject({ p: 'alpha', b: 'tmux', in: 4096, out: 1, keys: 1, wheels: 1, msgs_in: 1, msgs_out: 1 })
    expect(row.scroll).toEqual({ smooth: 1 })
    expect(row.frames.scroll.h.reduce((x: number, y: number) => x + y, 0)).toBe(9)
    // Light keeps no events.
    expect(JSON.parse(bodies[0]!).events).toEqual([])
    a.dispose()
  })

  it('sends nothing for a quiet minute, and a row every ten minutes for the memory', async () => {
    const { log, bodies } = setup()
    ;(log as unknown as { lastRow: number }).lastRow = Date.now()
    await log.flush()
    expect(bodies).toEqual([])
    ;(log as unknown as { lastRow: number }).lastRow = Date.now() - 11 * 60_000
    await log.flush()
    expect(bodies.length).toBe(1)
  })

  it('finds a doubled paste sent through the socket, and names its path', async () => {
    const { log, bodies, el, ws } = setup()
    const paste = JSON.stringify({ type: 'input', data: 'git status\r', typed: true })
    el.dispatchEvent(new Event('paste'))
    ;(ws as unknown as WebSocket).send(paste)
    ;(ws as unknown as WebSocket).send(paste)
    await log.flush()
    const row = JSON.parse(bodies[0]!).rows[0]
    expect(row.findings.map((f: Finding) => [f.kind, f.what])).toEqual([['paste-twice', 'native']])
    expect(row.paste).toEqual({ native: 2 })
  })

  it('finds a reconnect with how long the socket was down', async () => {
    const { log, bodies, ws, a } = setup()
    ws.dispatchEvent(new CloseEvent('close', { code: 1006 }))
    const ws2 = new FakeSocket()
    a.socket(ws2 as unknown as WebSocket)
    ws2.dispatchEvent(new Event('open'))
    await log.flush()
    const row = JSON.parse(bodies[0]!).rows[0]
    expect(row.sock.reconnects).toBe(1)
    expect(row.findings[0].kind).toBe('reconnect')
  })

  it('finds a failed request of the page', async () => {
    window.fetch = vi.fn(async () => { throw new TypeError('Failed to fetch') }) as unknown as typeof fetch
    const { log, bodies } = setup()
    await expect(fetch('/api/terminal/sessions/t-1abcdef/open', { method: 'POST' })).rejects.toThrow()
    await log.flush()
    const row = JSON.parse(bodies[0]!).rows[0]
    expect(row.fetch).toEqual({ 'POST /api/terminal/sessions/:id/open 0': 1 })
    expect(row.findings[0]).toMatchObject({ kind: 'fetch', what: '/api/terminal/sessions/:id/open no answer' })
    log.setMode('off')
    expect(window.fetch).not.toBe(undefined)
  })

  it('leaves the socket\'s send to its prototype: a spy put on it later sees every frame', () => {
    const { ws } = setup()
    const seen: unknown[] = []
    const orig = FakeSocket.prototype.send
    FakeSocket.prototype.send = function (this: FakeSocket, d: unknown) { seen.push(d); orig.call(this, d) }
    try {
      ;(ws as unknown as WebSocket).send('{"type":"input","data":"a","typed":true}')
    } finally { FakeSocket.prototype.send = orig }
    expect(seen).toHaveLength(1)
    expect(ws.sent).toHaveLength(1)
  })

  it('Full keeps events in a ring bounded by count and age', () => {
    const { log } = setup('full')
    for (let i = 0; i < 31_000; i++) log.event('key', 't-1', null, null)
    expect(log.events().length).toBe(30_000)
    vi.useFakeTimers({ now: Date.now() + 11 * 60_000 })
    log.event('key', 't-1', null, null)
    expect(log.events().length).toBe(1)
  })

  it('Full sends its new events once, and Light none', async () => {
    const { log, bodies, el } = setup('full')
    el.dispatchEvent(new KeyboardEvent('keydown', { key: 'x' }))
    await log.flush(false, false)
    await log.flush(false, false)
    expect(bodies.length).toBe(1)
    expect(JSON.parse(bodies[0]!).events.map((e: unknown[]) => e[1])).toEqual(['key'])
    log.setMode('light')
    expect(log.events().length).toBe(0)
  })

  it('Off records nothing and sends nothing', async () => {
    const { log, bodies, el, ws } = setup()
    log.setMode('off')
    el.dispatchEvent(new KeyboardEvent('keydown', { key: 'x' }))
    ws.dispatchEvent(new MessageEvent('message', { data: 'x' }))
    await log.flush(true)
    expect(bodies).toEqual([])
    // Not even the ten-minute row for the memory, nor the time it spent before.
    ;(log as unknown as { lastRow: number }).lastRow = 0
    expect(log.row()).toBe(null)
  })

  it('never lets out what was typed, pasted, selected or printed', async () => {
    for (const mode of ['light', 'full'] as const) {
      const { log, bodies, el, ws, select } = setup(mode)
      const send = (data: string) => (ws as unknown as WebSocket).send(JSON.stringify({ type: 'input', data, typed: true }))
      // Typed, a key at a time.
      for (const ch of SECRET) { el.dispatchEvent(new KeyboardEvent('keydown', { key: ch })); send(ch) }
      // Pasted twice (a finding), natively.
      const dt = { getData: () => SECRET } as unknown as DataTransfer
      const pe = new Event('paste') as ClipboardEvent
      Object.defineProperty(pe, 'clipboardData', { value: dt })
      el.dispatchEvent(pe)
      send(`\x1b[200~${SECRET}\x1b[201~`)
      send(`\x1b[200~${SECRET}\x1b[201~`)
      // Printed by the terminal, as text and as bytes.
      ws.dispatchEvent(new MessageEvent('message', { data: `echo ${SECRET}\r\n${SECRET}\r\n` }))
      ws.dispatchEvent(new MessageEvent('message', { data: new TextEncoder().encode(SECRET).buffer }))
      // Selected.
      select()
      // An error that does not carry it, a request that fails.
      window.dispatchEvent(new ErrorEvent('error', { message: 'boom', filename: 'x.js', lineno: 3 }))
      for (let i = 1; i < 5; i++) frame(log, i * 16)
      await log.flush(true)
      const everything = bodies.join('\n') + JSON.stringify(log.events()) + JSON.stringify(log.row())
      expect(bodies.length).toBeGreaterThan(0)
      expect(everything).not.toContain(SECRET)
      expect(everything).not.toContain('hunter2')
      // And the paste was still seen, by its size.
      expect(bodies.join('')).toContain('paste-twice')
      log.setMode('off')
    }
  })
})

describe('keys-lost (tk_184f61e4): keys pressed, no input sent', () => {
  const rulesOnly = () => { const got: Finding[] = []; return { r: new Rules((f) => got.push(f)), got } }

  it('the known case: back from another window, "#" pressed, nothing reaches the socket', () => {
    const { r, got } = rulesOnly()
    r.keyExpected('t1', 'alpha', 1000, 'Shift+3 printable · focus=body · tmux alt-screen', 140)
    r.keysDue(1100)
    expect(got).toEqual([])            // not yet: 300 ms to arrive
    r.keysDue(1320)
    expect(got.map((f) => [f.kind, f.n, f.what])).toEqual([['keys-lost', 140, 'Shift+3 printable · focus=body · tmux alt-screen']])
  })

  it('the good case: the key\'s input arrives', () => {
    const { r, got } = rulesOnly()
    r.keyExpected('t1', '', 1000, 'letter', 5000)
    r.input('t1')
    r.keysDue(1400)
    expect(got).toEqual([])
  })

  it('names a key by its kind, never its character', () => {
    const k = (key: string, code: string, shiftKey = false, ctrlKey = false) => keyKind({ key, code, shiftKey, ctrlKey, altKey: false, metaKey: false })
    expect(k('#', 'Digit3', true)).toBe('Shift+3 printable')
    expect(k('q', 'KeyQ')).toBe('letter')
    expect(k(' ', 'Space')).toBe('space')
    expect(k('Shift', 'ShiftLeft', true)).toBe('modifier')
    expect(k('/', 'Slash')).toBe('printable')
  })

  it('in the window: a key on the page with no send is found once, with focus and mode; a sent one, an IME, a shortcut and another box are not', async () => {
    vi.useFakeTimers()
    vi.spyOn(document, 'hasFocus').mockReturnValue(true)
    const { log, bodies, ws, el } = setup()
    el.style.display = 'block'
    Object.defineProperty(el, 'offsetParent', { get: () => document.body, configurable: true })
    el.dispatchEvent(new FocusEvent('focusin'))
    const key = (init: KeyboardEventInit) => window.dispatchEvent(new KeyboardEvent('keydown', init))
    // Sent: fine.
    key({ key: 'a', code: 'KeyA' })
    ;(ws as unknown as WebSocket).send(JSON.stringify({ type: 'input', data: 'a', typed: true }))
    // IME, a shortcut, typing in another box: known reasons.
    key({ key: 'Process', code: 'KeyA', isComposing: true })
    key({ key: 'k', code: 'KeyK', ctrlKey: true })
    const box = document.createElement('input'); document.body.appendChild(box); box.focus()
    key({ key: 'x', code: 'KeyX' })
    box.blur(); box.remove()
    vi.advanceTimersByTime(400)
    // Lost: "#" with nothing sent.
    key({ key: '#', code: 'Digit3', shiftKey: true })
    vi.advanceTimersByTime(400)
    vi.useRealTimers()
    await log.flush()
    const row = JSON.parse(bodies[0]!).rows[0]
    const lost = (row.findings ?? []).filter((f: Finding) => f.kind === 'keys-lost')
    expect(lost).toHaveLength(1)
    expect(lost[0].what).toMatch(/^Shift\+3 printable · focus=body · tmux/)
    expect(bodies.join('')).not.toContain('#')
  })
})
