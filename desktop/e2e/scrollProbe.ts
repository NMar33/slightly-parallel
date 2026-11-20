import type { Page } from '@playwright/test'

/**
 * How the terminal's text moves under the wheel, frame by frame.
 *
 * The text is numbered lines (`L00001 …`). Each animation frame the probe
 * finds the topmost numbered line the operator can see in the terminal (the
 * element really on top at that point, whatever draws it: xterm's rows or a
 * layer over them) and turns its number and its pixel position into one
 * value: how far down the history the view stands, in pixels. The steps
 * between frames are what the eye sees: 0 is a frame where nothing moved,
 * a row height (or five) is a jump.
 *
 * Input comes two ways:
 * - `plan`: wheel events made in the page and sent to the element under the
 *   middle of the terminal, a list per frame — exact timing and any
 *   deltaMode (a touchpad's 2–8 px, a mouse's notch in pixels or lines);
 * - `trusted`: Chromium's own input (CDP, Playwright's mouse.wheel), the
 *   path a real wheel takes, with the timing node can keep.
 */

export type Wheel = { dy: number; mode?: 0 | 1 }
export type Sample = { t: number; off: number | null }
export type Measured = {
  samples: Sample[]
  /** Frame index of the first and the last frame that sent input. */
  first: number
  last: number
  /** Pixels asked for: the sum of the deltas (lines × row height). */
  asked: number
  rowH: number
}

/** The page side: installed once per page, then `__spProbe.run(plan, settle)`. */
const PAGE_PROBE = `(() => {
  if (window.__spProbe) return
  const area = () => document.querySelector('.aqua-screen') || document.querySelector('.xterm')?.parentElement
  const rowH = () => {
    const r = document.querySelector('.aqua-screen .xterm-rows > div')
    return r ? r.getBoundingClientRect().height : 0
  }
  const offset = () => {
    const box = area()
    if (!box) return null
    const b = box.getBoundingClientRect()
    const h = rowH()
    let best = null
    for (const el of box.querySelectorAll('.xterm-rows > div, [data-scroll-row]')) {
      const r = el.getBoundingClientRect()
      if (r.height === 0 || r.bottom <= b.top + 1 || r.top >= b.bottom - 1) continue
      const m = /^\\s*L(\\d{5})/.exec(el.textContent || '')
      if (!m) continue
      // Really seen: the element on top at the row's middle is this row.
      const y = Math.min(Math.max(r.top + r.height / 2, b.top + 1), b.bottom - 1)
      const hit = document.elementFromPoint(r.left + 4, y)
      if (!hit || !(hit === el || el.contains(hit))) continue
      if (best === null || r.top < best.top) best = { top: r.top, n: Number(m[1]) }
    }
    return best === null ? null : (best.n - 1) * h - (best.top - b.top)
  }
  const target = () => {
    const box = area()
    if (!box) return null
    const b = box.getBoundingClientRect()
    const x = b.left + b.width / 2, y = b.top + b.height / 2
    return { el: document.elementFromPoint(x, y), x, y }
  }
  const seen = { n: 0, sum: 0, modes: {} }
  window.addEventListener('wheel', (e) => { seen.n++; seen.sum += e.deltaMode === 1 ? e.deltaY * rowH() : e.deltaY; seen.modes[e.deltaMode] = (seen.modes[e.deltaMode] || 0) + 1 }, { capture: true, passive: true })
  window.__spProbe = {
    rowH, offset, seen,
    run(plan, settle) {
      return new Promise((resolve) => {
        const out = []
        let i = 0
        const frame = (ts) => {
          out.push({ t: ts, off: offset() })
          const evs = plan[i] || []
          if (evs.length) {
            for (const e of evs) {
              // Hit-tested per event, as real input is: the first event of a
              // frame can redraw xterm's rows and take the element away.
              const tg = target()
              tg.el.dispatchEvent(new WheelEvent('wheel', { deltaY: e.dy, deltaMode: e.mode || 0, clientX: tg.x, clientY: tg.y, bubbles: true, cancelable: true, composed: true, view: window }))
            }
          }
          i++
          if (window.__spProbe.stop) { window.__spProbe.stop = false; resolve(out) }
          else if (i < plan.length + settle) requestAnimationFrame(frame)
          else resolve(out)
        }
        requestAnimationFrame(frame)
      })
    },
    record(frames) { return this.run(Array.from({ length: frames }, () => []), 0) },
  }
})()`

export async function install(page: Page) {
  await page.evaluate(PAGE_PROBE)
}

export const rowHeight = (page: Page) => page.evaluate(() => (window as unknown as { __spProbe: { rowH: () => number } }).__spProbe.rowH())
export const offsetNow = async (page: Page) => { await install(page); return page.evaluate(() => (window as unknown as { __spProbe: { offset: () => number | null } }).__spProbe.offset()) }

/** Send `plan` (a list of wheel events per frame), then watch `settle` more frames. */
export async function runPlan(page: Page, plan: Wheel[][], settle = 45): Promise<Measured> {
  await install(page)
  const h = await rowHeight(page)
  const samples = await page.evaluate(([p, s]) => (window as unknown as { __spProbe: { run: (p: Wheel[][], s: number) => Promise<Sample[]> } }).__spProbe.run(p as Wheel[][], s as number), [plan, settle] as const)
  const sent = plan.map((f, i) => (f.length ? i : -1)).filter((i) => i >= 0)
  const asked = plan.flat().reduce((a, e) => a + (e.mode === 1 ? e.dy * h : e.dy), 0)
  return { samples, first: sent[0] ?? 0, last: sent[sent.length - 1] ?? 0, asked, rowH: h }
}

/** Chromium's own wheel input (CDP): `deltas` px, one every `everyMs`, the pointer over the terminal's middle. */
export async function runTrusted(page: Page, deltas: number[], everyMs: number, settleMs = 800): Promise<Measured> {
  await install(page)
  const h = await rowHeight(page)
  const box = await page.locator('.aqua-screen').boundingBox()
  if (!box) throw new Error('no terminal on the page')
  await page.mouse.move(box.x + box.width / 2, box.y + box.height / 2)
  // Recorded until stopped: each mouse.wheel takes its own time, more than everyMs.
  const frames = 100_000
  const rec = page.evaluate((n) => (window as unknown as { __spProbe: { record: (n: number) => Promise<Sample[]> } }).__spProbe.record(n), frames)
  await page.waitForTimeout(50)
  const t0 = await page.evaluate(() => { const g = (window as unknown as { __spProbe: { seen: { n: number; sum: number } } }).__spProbe.seen; g.n = 0; g.sum = 0; return performance.now() })
  for (const d of deltas) {
    await page.mouse.wheel(0, d)
    await page.waitForTimeout(everyMs)
  }
  const t1 = await page.evaluate(() => performance.now())
  await page.waitForTimeout(settleMs)
  await page.evaluate(() => { (window as unknown as { __spProbe: { stop: boolean } }).__spProbe.stop = true })
  const samples = await rec
  const seen = await page.evaluate(() => (window as unknown as { __spProbe: { seen: unknown } }).__spProbe.seen)
  if (process.env.SP_SCROLL_DEBUG) console.log('trusted wheel seen by the page:', JSON.stringify(seen), 'sent', deltas.length, deltas.reduce((a, b) => a + b, 0))
  const first = samples.findIndex((s) => s.t >= t0)
  let last = samples.findIndex((s) => s.t >= t1)
  if (last < 0) last = samples.length - 1
  return { samples, first: Math.max(0, first), last, asked: deltas.reduce((a, b) => a + b, 0), rowH: h }
}

export type Stats = {
  /** Frames from the first input to one frame after the last. */
  activeFrames: number
  /** Frames in that window where the text stood still (after the first frame of latency). */
  stalls: number
  /** The longest run of still frames in that window. */
  longestStall: number
  /** The biggest move between two frames, px. */
  maxJump: number
  /** Where the view ended up against where it was asked to go: moved / asked. */
  ratio: number
  moved: number
  asked: number
  /** Share of the moves that were whole rows (snapped to the row grid). */
  wholeRows: number
  /** Frames from the first input to the first move. */
  latency: number
  frameMaxMs: number
  frameP95Ms: number
  rowH: number
  /** Frames where no numbered line was seen (the probe could not read the view). */
  blind: number
  /** Frames on which the text moved at all. */
  movingFrames: number
}

/** `fromMove`: count still frames from the first move on (the tmux reader takes a few frames to open). */
export function stats(m: Measured, latencyFrames = 1, fromMove = false): Stats {
  const s = m.samples
  const offs = s.map((x) => x.off)
  const moves: number[] = []
  for (let i = 1; i < offs.length; i++) moves.push(offs[i] != null && offs[i - 1] != null ? offs[i]! - offs[i - 1]! : 0)
  // moves[i-1] is the change seen at frame i: input sent at frame k shows at frame k+1 at best.
  const firstMove = moves.findIndex((d, i) => i + 1 > m.first && Math.abs(d) > 0.01)
  const latency = firstMove < 0 ? -1 : firstMove + 1 - m.first
  const from = fromMove && firstMove >= 0 ? firstMove + 2 : m.first + 1 + latencyFrames
  const to = m.last + 1
  let stalls = 0, run = 0, longest = 0
  for (let i = from; i <= to && i < s.length; i++) {
    const d = moves[i - 1] ?? 0
    if (Math.abs(d) < 0.01) { stalls++; run++; longest = Math.max(longest, run) } else run = 0
  }
  const real = moves.filter((d) => Math.abs(d) > 0.01)
  const whole = real.filter((d) => m.rowH > 0 && Math.abs(Math.abs(d) / m.rowH - Math.round(Math.abs(d) / m.rowH)) < 0.02).length
  const start = offs.find((x) => x != null) ?? 0
  const end = [...offs].reverse().find((x) => x != null) ?? 0
  const dts = s.slice(1).map((x, i) => x.t - s[i].t).sort((a, b) => a - b)
  return {
    activeFrames: to - m.first,
    stalls, longestStall: longest,
    maxJump: Math.max(0, ...moves.map(Math.abs)),
    moved: end - start, asked: m.asked,
    ratio: m.asked ? (end - start) / m.asked : 0,
    wholeRows: real.length ? whole / real.length : 0,
    latency,
    frameMaxMs: dts.length ? dts[dts.length - 1] : 0,
    frameP95Ms: dts.length ? dts[Math.floor(dts.length * 0.95)] : 0,
    rowH: m.rowH,
    blind: offs.filter((x) => x == null).length,
    movingFrames: real.length,
  }
}

/* --------------------------------------------------------------- input plans */

/** A touchpad: two events a frame (120 Hz), 2–8 px each, `frames` frames, up (negative) or down. */
export function touchpad(frames: number, dir: -1 | 1 = -1): Wheel[][] {
  const d = [2, 3, 5, 8, 4, 6]
  return Array.from({ length: frames }, (_, i) => [{ dy: dir * d[(2 * i) % 6] }, { dy: dir * d[(2 * i + 1) % 6] }])
}
/** A slow finger: one 2 px event a frame. */
export function slowFinger(frames: number, dir: -1 | 1 = -1): Wheel[][] {
  return Array.from({ length: frames }, () => [{ dy: dir * 2 }])
}
/** Mouse notches: `n` of them, one every `gap` frames, each `dy` (pixels) or `dy` lines. */
export function notches(n: number, gap: number, dy: number, mode: 0 | 1 = 0): Wheel[][] {
  const out: Wheel[][] = []
  for (let i = 0; i < n * gap; i++) out.push(i % gap === 0 ? [{ dy, mode }] : [])
  return out
}

export const fmt = (s: Stats) =>
  `frames ${s.activeFrames}, still ${s.stalls} (longest ${s.longestStall}), max jump ${s.maxJump.toFixed(1)} px (row ${s.rowH.toFixed(1)}), ` +
  `moved ${s.moved.toFixed(0)}/${s.asked.toFixed(0)} px (${(s.ratio * 100).toFixed(0)}%), whole rows ${(s.wholeRows * 100).toFixed(0)}%, ` +
  `latency ${s.latency} fr, frame max ${s.frameMaxMs.toFixed(1)} / p95 ${s.frameP95Ms.toFixed(1)} ms${s.blind ? `, blind ${s.blind}` : ''}`
