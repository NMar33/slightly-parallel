import fs from 'node:fs'
import os from 'node:os'
import path from 'node:path'
import { execFileSync } from 'node:child_process'
import { _electron, type APIRequestContext, type ElectronApplication, type Page } from '@playwright/test'
import { descendants } from '../global-setup'
import {
  test, expect, ELECTRON, HEADLESS, HIDDEN, ROOT, WINDOWS, catchLinksOut, closeAll, echoCalc, expectLine,
  launchArgs, launchEnv, mainTerminalPage, openShell, printFile, ready, typeLine,
} from '../fixtures'
import { makeData } from './data'

/**
 * The terminal window measured, in the real app (desktop/, Electron) on the
 * sandbox server — run by run-bench.mjs, which merges what each test saves
 * into one JSON file and a table.
 *
 * - memory by windows: the main window and windows detached from it (op:
 *   detach, one Electron app, one session), each with a live terminal that
 *   has printed 12 000 lines;
 * - memory by tabs: N terminals as tabs of one window (the front one and the
 *   ones last in front are mounted, TermApp.tsx KEEP_SCREENS), each opened
 *   by "+" and filled the same way;
 * - speed: 20 MB of coloured output (data.ts) through the real path (`cat`
 *   in the terminal's shell; PowerShell on Windows), and written straight
 *   into the page's xterm (plain terminals only), plus scrolling.
 *
 * Memory: PSS of the Electron process tree (Linux, /proc/<pid>/smaps_rollup)
 * and the sums of app.getAppMetrics() (every system). The tmux server and
 * the Slightly Parallel server are not in the tree, and not counted.
 *
 * Knobs (env): SP_BENCH_REPEATS (3), SP_BENCH_WINDOWS (1,2,3,5,10,15,20),
 * SP_BENCH_TABS (1,5,10,20), SP_BENCH_MB (20), SP_BENCH_SETTLE_MS (5000),
 * SP_BENCH_MODES (tmux,plain), SP_BENCH_ONLY (machine,windows,tabs,speed),
 * SP_BENCH_SCALE (unset: the display's own device pixel ratio).
 */

const OUT = process.env.SP_BENCH_OUT || path.join(__dirname, 'out')
const PARTS = path.join(OUT, 'parts')
const nums = (v: string | undefined, d: string) => (v || d).split(',').map(Number).filter((x) => x > 0)
const REPEATS = Number(process.env.SP_BENCH_REPEATS) || 3
const WIN_N = nums(process.env.SP_BENCH_WINDOWS, '1,2,3,5,10,15,20')
const TAB_N = nums(process.env.SP_BENCH_TABS, '1,5,10,20')
const MB = Number(process.env.SP_BENCH_MB) || 20
const SETTLE = Number(process.env.SP_BENCH_SETTLE_MS) || 5000
const FILL_LINES = 12_000
const ONLY = (process.env.SP_BENCH_ONLY || 'machine,windows,tabs,speed').split(',')
const W = 1000, H = 640
/** SP_BENCH_SCALE=2.5: Chromium draws at that device pixel ratio (the laptop's screen) whatever the display's own scale. */
const SCALE = process.env.SP_BENCH_SCALE || ''

const BENCH_DIR = path.join(ROOT, 'work', 'bench')
const BIG = path.join(BENCH_DIR, 'out20.txt')
const FILL = path.join(BENCH_DIR, 'fill.txt')

function save(name: string, data: unknown) {
  fs.mkdirSync(PARTS, { recursive: true })
  fs.writeFileSync(path.join(PARTS, `${name}.json`), JSON.stringify(data, null, 1))
}

function files() {
  if (fs.existsSync(BIG) && fs.existsSync(FILL)) return
  fs.mkdirSync(BENCH_DIR, { recursive: true })
  // \n only: the pty turns it into \r\n, the bytes the page writes directly.
  const text = makeData(MB * 1e6, '\n')
  fs.writeFileSync(BIG, text)
  fs.writeFileSync(FILL, text.split('\n').slice(0, FILL_LINES).join('\n') + '\n')
}

const sleep = (ms: number) => new Promise((r) => setTimeout(r, ms))

/** A step of the bench that did not end in time, or failed: kept in the
 *  JSON (`failures`), and the bench goes on with the next repeat. The
 *  Windows bench once waited 57 minutes on one step, until the CI job's
 *  limit cancelled it and nothing was saved. */
type Failure = { test: string; mode?: string; repeat?: number; phase: string; error: string; at: string }
const failures: Failure[] = []
class PhaseTimeout extends Error {}

/** `fn`, or a PhaseTimeout after `ms`. What it was doing goes on in the
 *  background; the caller kills the app, which ends it. */
async function phase<T>(name: string, ms: number, fn: () => Promise<T>): Promise<T> {
  let timer: NodeJS.Timeout | undefined
  const late = new Promise<never>((_, reject) => {
    timer = setTimeout(() => reject(new PhaseTimeout(`${name}: no end in ${Math.round(ms / 1000)} s`)), ms)
  })
  try { return await Promise.race([fn(), late]) } finally { clearTimeout(timer) }
}

function failed(where: Omit<Failure, 'error' | 'at'>, e: unknown) {
  const error = (e instanceof Error ? e.message : String(e)).split('\n')[0].slice(0, 400)
  failures.push({ ...where, error, at: new Date().toISOString() })
  console.log(`bench: ${where.test}${where.mode ? ` ${where.mode}` : ''}${where.repeat ? ` #${where.repeat}` : ''}: ${where.phase} failed: ${error}`)
}

/** A test's failures, saved in its part of the JSON (a failed test restarts the worker: nothing is shared). */
const failuresOf = (test: string) => failures.filter((f) => f.test === test)

/** Terminals that failed to open on the first try. Right after the last
 *  tmux terminal closes, tmux's server is going away, and a new-session
 *  sent to it then fails (exit 1): seen in 1 of 6 rounds on the laptop. The
 *  bench tries again and counts it (`open_retries` in the JSON). */
let openRetries = 0
async function shell(api: APIRequestContext, label: string) {
  for (let i = 0; ; i++) {
    try { return await openShell(api, label) } catch (e) {
      if (i >= 4) throw e
      openRetries++
      await sleep(1000)
    }
  }
}

type App = { app: ElectronApplication; page: Page; close: () => Promise<void> }
async function launch(test: string): Promise<App> {
  const userData = fs.mkdtempSync(path.join(os.tmpdir(), 'sp-desktop-e2e-profile-'))
  const app = await _electron.launch({ executablePath: ELECTRON, args: [...launchArgs(userData), ...(SCALE ? [`--force-device-scale-factor=${SCALE}`] : [])], env: launchEnv(), timeout: 30_000 })
  await catchLinksOut(app)
  const page = await mainTerminalPage(app)
  await page.waitForLoadState('domcontentloaded')
  const close = async () => {
    // A quit that does not end (a window that will not close) is killed: the bench goes on.
    try { await phase('quit the app', 60_000, () => app.close()) } catch (e) {
      failed({ test, phase: 'quit the app' }, e)
      try { app.process().kill() } catch { /* gone */ }
    }
    fs.rmSync(userData, { recursive: true, force: true, maxRetries: 5, retryDelay: 500 })
  }
  return { app, page, close }
}

/** Which terminals this server can keep: tmux where it is installed (never Windows), plain everywhere. */
async function modes(api: APIRequestContext): Promise<string[]> {
  const st = await (await api.get('/api/terminal/state')).json()
  const all = (process.env.SP_BENCH_MODES || 'tmux,plain').split(',')
  return all.filter((m) => m === 'plain' || (m === 'tmux' && st.tmux && !WINDOWS))
}

async function setMode(api: APIRequestContext, keep: string) {
  const r = await api.post('/api/settings', { data: { values: { 'terminal.keep': keep, 'terminal.scrollback': '10000' } } })
  expect(r.ok(), await r.text()).toBeTruthy()
}

/** The terminal in front prints the fill file; done when its last line is drawn. */
async function fill(page: Page, k: number) {
  await typeLine(page, `${printFile(FILL)}; ${echoCalc(`fill${k}-`, '2+3', '-done')}`)
  await expectLine(page, `fill${k}-5-done`, 60_000)
}

const pssKb = (pid: number) => {
  try {
    const m = /^Pss:\s+(\d+)/m.exec(fs.readFileSync(`/proc/${pid}/smaps_rollup`, 'utf-8'))
    return m ? Number(m[1]) : 0
  } catch { return 0 }
}

type Mem = { pss_mb: number | null; procs: number; ws_mb: number; private_mb: number | null; by_type: Record<string, { n: number; ws_mb: number; pss_mb?: number }> }

/** The whole app's memory now: PSS of its process tree (Linux) and getAppMetrics' sums. */
async function memory(app: ElectronApplication): Promise<Mem> {
  const metrics = await app.evaluate(({ app: a }) => a.getAppMetrics().map((m) => ({
    pid: m.pid, type: m.type, ws: m.memory.workingSetSize, priv: (m.memory as { privateBytes?: number }).privateBytes,
  })))
  const root = app.process().pid!
  const linux = process.platform === 'linux'
  const tree = linux ? [root, ...descendants(root)] : []
  const pss = new Map(tree.map((p) => [p, pssKb(p)]))
  const by: Mem['by_type'] = {}
  for (const m of metrics) {
    const b = by[m.type] ??= { n: 0, ws_mb: 0, ...(linux ? { pss_mb: 0 } : {}) }
    b.n++; b.ws_mb += m.ws / 1024
    if (linux) b.pss_mb! += (pss.get(m.pid) ?? 0) / 1024
  }
  for (const b of Object.values(by)) { b.ws_mb = Math.round(b.ws_mb); if (b.pss_mb !== undefined) b.pss_mb = Math.round(b.pss_mb) }
  const privs = metrics.map((m) => m.priv).filter((v): v is number => typeof v === 'number')
  return {
    pss_mb: linux ? Math.round([...pss.values()].reduce((a, b) => a + b, 0) / 1024) : null,
    procs: linux ? tree.length : metrics.length,
    ws_mb: Math.round(metrics.reduce((a, m) => a + m.ws, 0) / 1024),
    private_mb: privs.length ? Math.round(privs.reduce((a, b) => a + b, 0) / 1024) : null,
    by_type: by,
  }
}

function sh(cmd: string, args: string[]): string {
  try { return execFileSync(cmd, args, { encoding: 'utf-8', timeout: 5000 }).trim() } catch { return '' }
}

test.beforeAll(() => files())

test('machine', async ({ server }) => {
  test.skip(!ONLY.includes('machine'))
  const w = await launch('machine')
  try {
    const main = await w.app.evaluate(async ({ app }) => {
      const info = await app.getGPUInfo('complete').catch(() => null) as { auxAttributes?: Record<string, unknown>; gpuDevice?: unknown[] } | null
      return {
        versions: { electron: process.versions.electron, chrome: process.versions.chrome, node: process.versions.node, v8: process.versions.v8 },
        gpu_status: app.getGPUFeatureStatus(),
        gl_renderer: info?.auxAttributes?.glRenderer ?? null,
        gl_vendor: info?.auxAttributes?.glVendor ?? null,
        gpu_devices: info?.gpuDevice ?? null,
        sandbox_off: app.commandLine.hasSwitch('no-sandbox'),
        session_type: process.env.XDG_SESSION_TYPE ?? '',
        wayland_display: process.env.WAYLAND_DISPLAY ?? '',
        x11_display: process.env.DISPLAY ?? '',
        scale_forced: app.commandLine.getSwitchValue('force-device-scale-factor') || null,
      }
    })
    const page = await w.page.evaluate(() => {
      let webgl = 'none'
      try {
        const c = document.createElement('canvas').getContext('webgl2')!
        const e = c.getExtension('WEBGL_debug_renderer_info')
        webgl = e ? String(c.getParameter(e.UNMASKED_RENDERER_WEBGL)) : 'webgl2'
      } catch { /* none */ }
      return { dpr: devicePixelRatio, inner: [innerWidth, innerHeight], webgl, ua: navigator.userAgent }
    })
    const cpus = os.cpus()
    const osName = process.platform === 'linux'
      ? (/^PRETTY_NAME="?([^"\n]*)/m.exec(fs.existsSync('/etc/os-release') ? fs.readFileSync('/etc/os-release', 'utf-8') : '')?.[1] ?? 'Linux')
      : process.platform === 'darwin' ? `macOS ${sh('sw_vers', ['-productVersion'])}` : `Windows ${os.release()}`
    save('machine', {
      platform: process.platform, arch: process.arch, os: osName, kernel: os.release(),
      cpu: cpus[0]?.model?.trim() ?? '?', cores: cpus.length, ram_gb: Math.round(os.totalmem() / 2 ** 30),
      ci: !!process.env.CI,
      display: HIDDEN ? `hidden GNOME Shell (${sh('gnome-shell', ['--version'])}, headless Wayland, virtual monitor ${process.env.SP_E2E_MONITOR || '1600x1000'})`
        : HEADLESS ? "Chromium's headless Ozone (no display)" : process.env.DISPLAY && process.platform === 'linux' ? `X11 ${process.env.DISPLAY}` : 'the system display',
      server: server.url,
      ...main, page,
    })
  } finally { await w.close() }
})

test('memory by windows (one app, detached windows)', async ({ server }) => {
  test.skip(!ONLY.includes('windows'))
  const { api } = server
  const runs: unknown[] = []
  for (const mode of await modes(api)) {
    for (let r = 1; r <= REPEATS; r++) {
      const points: unknown[] = []
      const where = { test: 'windows', mode, repeat: r }
      let step = 'close the terminals'
      try {
        await phase(step, 120_000, () => closeAll(api))
        step = 'open the first terminal'
        const first = await phase(step, 120_000, async () => { await setMode(api, mode); return shell(api, 'bench-1') })
        expect(first.backend).toBe(mode)
        step = 'launch the app'
        const w = await phase(step, 90_000, () => launch(where.test))
        const pages: Page[] = [w.page]
        try {
          step = 'fill the first window'
          await phase(step, 180_000, async () => { await ready(w.page); await fill(w.page, 1) })
          for (const n of WIN_N) {
            step = `n=${n}`
            await phase(step, 150_000 * Math.max(1, n - pages.length) + SETTLE + 60_000, async () => {
              while (pages.length < n) {
                const s = await shell(api, `bench-${pages.length + 1}`)
                const opened = w.app.waitForEvent('window')
                await w.page.evaluate(([u, ww, hh]) => (window as unknown as { spWindow: { postMessage: (m: unknown) => void } })
                  .spWindow.postMessage({ op: 'detach', url: u, width: ww, height: hh }), [`/term?detached=${encodeURIComponent(s.id)}`, W, H] as const)
                const p = await opened
                await p.waitForLoadState('domcontentloaded')
                await ready(p)
                await fill(p, pages.length + 1)
                pages.push(p)
              }
              await sleep(SETTLE)
              const windows = await w.app.evaluate(({ BrowserWindow }) => BrowserWindow.getAllWindows().length)
              const mounted = (await Promise.all(pages.map((p) => p.locator('.xterm').count()))).reduce((a, b) => a + b, 0)
              const m = await memory(w.app)
              console.log(`windows ${mode} #${r} n=${n}: PSS ${m.pss_mb} MB, working set ${m.ws_mb} MB, ${m.procs} processes`)
              points.push({ n, windows, terminals_mounted: mounted, ...m })
            })
          }
        } finally { await w.close() }
      } catch (e) { failed({ ...where, phase: step }, e) }
      runs.push({ mode, repeat: r, points })
      save('windows', { open_retries: openRetries, runs, failures: failuresOf('windows') })
    }
  }
  await phase('close the terminals', 120_000, () => closeAll(api)).catch((e) => failed({ test: 'windows', phase: 'close the terminals' }, e))
  save('windows', { open_retries: openRetries, runs, failures: failuresOf('windows') })
  expect(failuresOf('windows'), 'steps of the bench that failed (in the JSON)').toEqual([])
})

test('memory by tabs (one window)', async ({ server }) => {
  test.skip(!ONLY.includes('tabs'))
  const { api } = server
  const runs: unknown[] = []
  for (const mode of await modes(api)) {
    for (let r = 1; r <= REPEATS; r++) {
      const points: unknown[] = []
      const where = { test: 'tabs', mode, repeat: r }
      let step = 'close the terminals'
      try {
        await phase(step, 120_000, () => closeAll(api))
        step = 'open the first terminal'
        await phase(step, 120_000, async () => { await setMode(api, mode); await shell(api, 'bench-1') })
        step = 'launch the app'
        const w = await phase(step, 90_000, () => launch(where.test))
        const { page } = w
        try {
          step = 'fill the first tab'
          await phase(step, 180_000, async () => { await ready(page); await fill(page, 1) })
          const strip = page.getByRole('tablist', { name: 'Chats' })
          for (const n of TAB_N) {
            step = `n=${n}`
            const have = await strip.getByRole('tab').count()
            await phase(step, 150_000 * Math.max(1, n - have) + SETTLE + 60_000, async () => {
              for (let k = await strip.getByRole('tab').count(); k < n; k++) {
                // "+"'s list, 3: a plain terminal (1 would start an agent; tabs.spec.ts)
                await page.getByRole('button', { name: 'Choose what to open' }).click()
                await page.keyboard.press('3')
                await expect(strip.getByRole('tab')).toHaveCount(k + 1)
                await ready(page)
                await fill(page, k + 1)
              }
              await sleep(SETTLE)
              const m = await memory(w.app)
              const mounted = await page.locator('.xterm').count()
              console.log(`tabs ${mode} #${r} n=${n}: PSS ${m.pss_mb} MB, working set ${m.ws_mb} MB, ${mounted} mounted`)
              points.push({ n, tabs: await strip.getByRole('tab').count(), terminals_mounted: mounted, ...m })
            })
          }
        } finally { await w.close() }
      } catch (e) { failed({ ...where, phase: step }, e) }
      runs.push({ mode, repeat: r, points })
      save('tabs', { open_retries: openRetries, runs, failures: failuresOf('tabs') })
    }
  }
  await phase('close the terminals', 120_000, () => closeAll(api)).catch((e) => failed({ test: 'tabs', phase: 'close the terminals' }, e))
  save('tabs', { open_retries: openRetries, runs, failures: failuresOf('tabs') })
  expect(failuresOf('tabs'), 'steps of the bench that failed (in the JSON)').toEqual([])
})

/* ------------------------------------------------------------ speed */

type Win = Window & { __b: { t0: number; end: number; frames: number[]; done: boolean } }

/** In the page: frame times from the Enter that starts the command to the frame that shows `marker`. */
async function recordUntil(page: Page, marker: string) {
  await page.evaluate((mk) => {
    const g: Win['__b'] = { t0: 0, end: 0, frames: [], done: false }
    ;(window as unknown as Win).__b = g
    const rows = () => document.querySelectorAll('.aqua-screen .xterm-rows > div')
    const seen = () => { for (const r of rows()) if ((r.textContent ?? '').replace(/ /g, ' ').trim() === mk) return true; return false }
    window.addEventListener('keydown', (e) => { if (e.key === 'Enter' && !g.t0) g.t0 = performance.now() }, true)
    let last = 0
    const tick = (now: number) => {
      if (g.t0) {
        if (last) g.frames.push(now - last)
        last = now
        if (seen()) { g.end = performance.now(); g.done = true; return }
      }
      requestAnimationFrame(tick)
    }
    requestAnimationFrame(tick)
  }, marker)
}

/** One wheel notch up over the terminal: ms from the wheel to the frame where the screen's text changed (-1: no change in 2 s). */
async function wheelStep(page: Page): Promise<number> {
  await page.evaluate(() => {
    const text = () => [...document.querySelectorAll('.aqua-screen .xterm-rows > div')].map((r) => r.textContent).join('\n')
    const g = { t0: 0, ms: 0 }
    ;(window as unknown as { __w: typeof g }).__w = g
    const before = text()
    window.addEventListener('wheel', () => { g.t0 = performance.now() }, { capture: true, once: true })
    const loop = () => {
      if (g.t0) {
        if (text() !== before) { g.ms = performance.now() - g.t0; return }
        if (performance.now() - g.t0 > 2000) { g.ms = -1; return }
      }
      requestAnimationFrame(loop)
    }
    requestAnimationFrame(loop)
  })
  await page.mouse.wheel(0, -100)
  const h = await page.waitForFunction(() => (window as unknown as { __w: { ms: number } }).__w.ms || null, null, { timeout: 10_000 })
  return Number(await h.jsonValue())
}

const median = (xs: number[]) => { const s = [...xs].sort((a, b) => a - b); const m = s.length >> 1; return s.length % 2 ? s[m] : (s[m - 1] + s[m]) / 2 }
const r1 = (x: number) => Math.round(x * 10) / 10

/** The terminal object the page made (Screen.tsx's termRef), reached through React's fiber of its box: no product code changed for it. */
const FIND_TERM = `(() => {
  let n = document.querySelector('.aqua-screen .xterm')
  for (; n; n = n.parentElement) {
    const k = Object.keys(n).find((x) => x.startsWith('__reactFiber$'))
    if (!k) continue
    for (let f = n[k]; f; f = f.return) {
      for (let h = f.memoizedState; h && typeof h === 'object' && 'next' in h; h = h.next) {
        const v = h.memoizedState
        if (v && v.current && typeof v.current.write === 'function' && typeof v.current.scrollLines === 'function' && v.current.buffer) return v.current
      }
    }
    return null
  }
  return null
})()`

test('speed', async ({ server }) => {
  test.skip(!ONLY.includes('speed'))
  const { api } = server
  const bytes = fs.statSync(BIG).size
  const runs: unknown[] = []
  for (const mode of await modes(api)) {
    for (let r = 1; r <= REPEATS; r++) {
      const where = { test: 'speed', mode, repeat: r }
      let step = 'close the terminals'
      try {
        await phase(step, 120_000, () => closeAll(api))
        step = 'open the terminal'
        await phase(step, 120_000, async () => { await setMode(api, mode); await shell(api, 'bench-speed') })
        step = 'launch the app'
        const w = await phase(step, 90_000, () => launch(where.test))
        const { page } = w
        try {
          step = 'measure'
          await phase(step, 15 * 60_000, async () => {
            await ready(page)
            const size = await page.evaluate(() => {
              const s = document.querySelector('.aqua-screen .xterm-screen')!.getBoundingClientRect()
              return { w: Math.round(s.width), h: Math.round(s.height), dpr: devicePixelRatio }
            })
            // (a) the real path: the shell prints the file through the pty (and tmux).
            const marker = `bench${r}-42-end`
            await recordUntil(page, marker)
            await typeLine(page, `${printFile(BIG)}; ${echoCalc(`bench${r}-`, '6*7', '-end')}`)
            await page.waitForFunction(() => (window as unknown as Win).__b.done, null, { timeout: 300_000, polling: 250 })
            const b = await page.evaluate(() => (window as unknown as Win).__b)
            const ms = b.end - b.t0
            const cat = {
              ms: Math.round(ms), mb_s: r1(bytes / 1e6 / (ms / 1000)), fps: r1(b.frames.length / (ms / 1000)),
              worst_frame_ms: Math.round(Math.max(0, ...b.frames)),
              frames_over_50ms: b.frames.filter((f) => f > 50).length,
            }
            await sleep(1000)
            const box = (await page.locator('.aqua-screen .xterm-screen').boundingBox())!
            await page.mouse.move(box.x + box.width / 2, box.y + box.height / 2)
            const steps: number[] = []
            for (let i = 0; i < 60; i++) steps.push(await wheelStep(page))
            const moved = steps.filter((s) => s >= 0)
            const scroll = { steps: steps.length, unchanged: steps.length - moved.length, ms_median: moved.length ? r1(median(moved)) : null, ms_worst: moved.length ? Math.round(Math.max(...moved)) : null }
            console.log(`speed ${mode} #${r} cat: ${cat.ms} ms, ${cat.mb_s} MB/s, ${cat.fps} fps, worst frame ${cat.worst_frame_ms} ms; wheel ${scroll.ms_median} ms/step`)

            // (b) straight into the page's xterm, as the engine comparison did:
            // plain terminals only — under tmux the page's xterm is on tmux's
            // alternate screen, which keeps no history.
            let direct: unknown = { skipped: mode === 'plain' ? 'the page\'s terminal was not found' : 'tmux: the page\'s xterm is on the alternate screen (no history there); measured on plain' }
            if (mode === 'plain') {
              await page.keyboard.press('End').catch(() => {})
              const got = await page.evaluate(async ([find, gen, n]) => {
                const term = (0, eval)(find)
                if (!term) return null
                const make = (0, eval)(`(${gen})`) as (b: number, e: string) => string
                const buf = new TextEncoder().encode(make(n, '\r\n'))
                term.scrollToBottom()
                await new Promise((res) => setTimeout(res, 1500))
                let frames = 0, last = performance.now(), worst = 0, run = true
                const tick = () => { const t = performance.now(); frames++; worst = Math.max(worst, t - last); last = t; if (run) requestAnimationFrame(tick) }
                requestAnimationFrame(tick)
                const CH = 65536, t0 = performance.now()
                for (let i = 0; i < buf.length; i += CH) await new Promise<void>((res) => term.write(buf.subarray(i, i + CH), res))
                await new Promise((res) => requestAnimationFrame(() => requestAnimationFrame(res)))
                const ms = performance.now() - t0; run = false
                const s0 = performance.now(); let sf = 0
                for (let i = 0; i < 300; i++) { term.scrollLines(-3); await new Promise((res) => requestAnimationFrame(res)); sf++ }
                const scrollMs = performance.now() - s0
                term.scrollToBottom()
                return { bytes: buf.length, ms: Math.round(ms), mb_s: Math.round(buf.length / 1e6 / (ms / 1000) * 10) / 10, fps: Math.round(frames / (ms / 1000) * 10) / 10,
                  worst_frame_ms: Math.round(worst), scroll_ms_per_step: Math.round(scrollMs / sf * 10) / 10, cols: term.cols, rows: term.rows, scrollback: term.options.scrollback }
              }, [FIND_TERM, makeData.toString(), MB * 1e6] as const)
              if (got) direct = got
              console.log(`speed ${mode} #${r} direct: ${JSON.stringify(direct)}`)
            }
            runs.push({ mode, repeat: r, bytes, screen: size, cat, scroll, direct })
          })
        } finally { await w.close() }
      } catch (e) { failed({ ...where, phase: step }, e) }
      save('speed', { open_retries: openRetries, runs, failures: failuresOf('speed') })
    }
  }
  await phase('close the terminals', 120_000, () => closeAll(api)).catch((e) => failed({ test: 'speed', phase: 'close the terminals' }, e))
  save('speed', { open_retries: openRetries, runs, failures: failuresOf('speed') })
  expect(failuresOf('speed'), 'steps of the bench that failed (in the JSON)').toEqual([])
})
