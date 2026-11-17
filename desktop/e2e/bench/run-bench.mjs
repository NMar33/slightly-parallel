// `npm run bench` in desktop/: the terminal window measured (terminal.bench.ts)
// on a sandbox server of its own, on a free port; then one JSON file with
// every measurement and its repeats, and a short Markdown table, in
// e2e/bench/out/ (SP_BENCH_OUT elsewhere): bench-<os>.json, bench-<os>.md.
// A bench, not a test: no number fails it. Knobs: terminal.bench.ts.
// Arguments pass through to Playwright: npm run bench -- -g speed
import { spawnSync } from 'node:child_process'
import fs from 'node:fs'
import net from 'node:net'
import path from 'node:path'
import { fileURLToPath } from 'node:url'

const here = path.dirname(fileURLToPath(import.meta.url))
const modules = path.resolve(here, '..', '..', '..', 'frontend', 'node_modules')
const cli = path.join(modules, '@playwright', 'test', 'cli.js')
if (!fs.existsSync(cli)) {
  console.error(`no Playwright at ${cli}: run npm install in frontend/ first`)
  process.exit(2)
}
const out = path.resolve(process.env.SP_BENCH_OUT || path.join(here, 'out'))
const parts = path.join(out, 'parts')
fs.rmSync(parts, { recursive: true, force: true })

/** A port nobody listens on now: another run (or helper) may hold the suite's 8131. */
const freePort = () => new Promise((resolve, reject) => {
  const s = net.createServer().once('error', reject)
  s.listen(0, '127.0.0.1', () => { const { port } = s.address(); s.close(() => resolve(port)) })
})
const port = process.env.SP_DESKTOP_E2E_PORT || String(await freePort())

const started = new Date()
const r = spawnSync(process.execPath, [cli, 'test', '-c', path.join(here, 'bench.config.ts'), ...process.argv.slice(2)], {
  stdio: 'inherit',
  env: {
    ...process.env, SP_DESKTOP_E2E_PORT: port, SP_BENCH_OUT: out,
    // A forced scale needs a hidden display big enough for a 1000x640 window at it.
    ...(process.env.SP_BENCH_SCALE && !process.env.SP_E2E_MONITOR ? { SP_E2E_MONITOR: '3072x1920' } : {}),
    NODE_PATH: [modules, process.env.NODE_PATH].filter(Boolean).join(path.delimiter),
  },
})
const ended = new Date()

const read = (n) => { try { return JSON.parse(fs.readFileSync(path.join(parts, `${n}.json`), 'utf-8')) } catch { return null } }
const machine = read('machine') ?? { platform: process.platform }
const runsOf = (n) => read(n)?.runs ?? []
const windows = runsOf('windows')
const tabs = runsOf('tabs')
const speed = runsOf('speed')
const openRetries = Math.max(0, ...['windows', 'tabs', 'speed'].map((n) => read(n)?.open_retries ?? 0))

const stat = (xs) => {
  const v = xs.filter((x) => typeof x === 'number')
  if (!v.length) return null
  const s = [...v].sort((a, b) => a - b), m = s.length >> 1
  return { median: s.length % 2 ? s[m] : Math.round((s[m - 1] + s[m]) / 2 * 10) / 10, min: s[0], max: s[s.length - 1], n: s.length }
}
/** Memory runs → per mode and N: median, min, max of each measure. */
function memSummary(runs) {
  const by = new Map()
  for (const run of runs) for (const p of run.points) {
    const k = `${run.mode}|${p.n}`
    if (!by.has(k)) by.set(k, { mode: run.mode, n: p.n, pss: [], ws: [], priv: [] })
    const e = by.get(k); e.pss.push(p.pss_mb); e.ws.push(p.ws_mb); e.priv.push(p.private_mb)
  }
  return [...by.values()].map((e) => ({ mode: e.mode, n: e.n, pss_mb: stat(e.pss), ws_mb: stat(e.ws), private_mb: stat(e.priv) }))
}
function speedSummary(runs) {
  const modes = [...new Set(runs.map((x) => x.mode))]
  return modes.map((mode) => {
    const rs = runs.filter((x) => x.mode === mode)
    const pick = (f) => stat(rs.map(f))
    return {
      mode,
      cat: { ms: pick((x) => x.cat.ms), mb_s: pick((x) => x.cat.mb_s), fps: pick((x) => x.cat.fps), worst_frame_ms: pick((x) => x.cat.worst_frame_ms), wheel_ms: pick((x) => x.scroll.ms_median) },
      direct: { ms: pick((x) => x.direct?.ms), mb_s: pick((x) => x.direct?.mb_s), fps: pick((x) => x.direct?.fps), worst_frame_ms: pick((x) => x.direct?.worst_frame_ms), scroll_ms_per_step: pick((x) => x.direct?.scroll_ms_per_step) },
    }
  })
}

const os = { linux: 'linux', darwin: 'macos', win32: 'windows' }[machine.platform] ?? machine.platform
const result = {
  bench: 'slightly-parallel terminal window', version: 1,
  started: started.toISOString(), seconds: Math.round((ended - started) / 1000), exit_code: r.status,
  note: machine.ci ? 'A CI runner: a VM without a GPU. Compare across systems, not with a laptop.' : undefined,
  machine,
  open_retries: openRetries,
  method: {
    output_mb: Number(process.env.SP_BENCH_MB) || 20, window: '1000x640', scrollback: 10000, fill_lines: 12000,
    settle_ms: Number(process.env.SP_BENCH_SETTLE_MS) || 5000, repeats: Number(process.env.SP_BENCH_REPEATS) || 3,
    memory: 'PSS of the Electron process tree (Linux only) and sums of app.getAppMetrics() workingSetSize / privateBytes; tmux and the server are not counted',
    windows: 'one app: the main window plus windows opened by the bridge op detach, added one by one within each repeat',
    tabs: 'one window, terminals opened by "+", each filled while in front; only the front one is mounted',
  },
  summary: { windows: memSummary(windows), tabs: memSummary(tabs), speed: speedSummary(speed) },
  runs: { windows, tabs, speed },
}
fs.mkdirSync(out, { recursive: true })
const json = path.join(out, `bench-${os}.json`)
fs.writeFileSync(json, JSON.stringify(result, null, 1) + '\n')

const f = (s) => s ? (s.min === s.max ? `${s.median}` : `${s.median} (${s.min}–${s.max})`) : '—'
const md = [`# Terminal window bench — ${os}, ${started.toISOString().slice(0, 16).replace('T', ' ')}`, '',
  `${machine.cpu ?? '?'}, ${machine.cores ?? '?'} threads, ${machine.ram_gb ?? '?'} GB; ${machine.os ?? ''}; GPU: ${machine.gl_renderer ?? machine.page?.webgl ?? '?'} (${machine.gpu_status?.gpu_compositing ?? '?'}); display: ${machine.display ?? '?'}`,
  `Electron ${machine.versions?.electron ?? '?'}, Chromium ${machine.versions?.chrome ?? '?'}; sandbox ${machine.sandbox_off ? 'off (--no-sandbox)' : 'on'}. Median (min–max) of ${result.method.repeats} repeats; took ${result.seconds} s.`,
  ...(result.note ? ['', `**${result.note}**`] : []), '']
for (const [title, rows] of [['Memory by windows (MB)', result.summary.windows], ['Memory by tabs in one window (MB)', result.summary.tabs]]) {
  if (!rows.length) continue
  md.push(`## ${title}`, '', '| Terminals | Keep | PSS | Working set | Private |', '|---|---|---|---|---|')
  for (const x of rows) md.push(`| ${x.n} | ${x.mode} | ${f(x.pss_mb)} | ${f(x.ws_mb)} | ${f(x.private_mb)} |`)
  md.push('')
}
if (result.summary.speed.length) {
  md.push(`## Speed: ${result.method.output_mb} MB of coloured output`, '', '| Keep | Path | ms | MB/s | fps | Worst frame, ms | Scroll, ms/step |', '|---|---|---|---|---|---|---|')
  for (const x of result.summary.speed) {
    md.push(`| ${x.mode} | cat in the shell | ${f(x.cat.ms)} | ${f(x.cat.mb_s)} | ${f(x.cat.fps)} | ${f(x.cat.worst_frame_ms)} | ${f(x.cat.wheel_ms)} (wheel) |`)
    if (x.direct.ms) md.push(`| ${x.mode} | written into xterm | ${f(x.direct.ms)} | ${f(x.direct.mb_s)} | ${f(x.direct.fps)} | ${f(x.direct.worst_frame_ms)} | ${f(x.direct.scroll_ms_per_step)} (scrollLines) |`)
  }
  md.push('')
}
fs.writeFileSync(path.join(out, `bench-${os}.md`), md.join('\n'))
console.log(`\n${md.join('\n')}\nbench: ${json}`)
process.exit(r.status ?? 1)
