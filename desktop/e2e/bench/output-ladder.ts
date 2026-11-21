import { execFile } from 'node:child_process'
import fs from 'node:fs'
import path from 'node:path'
import { promisify } from 'node:util'
import type { APIRequestContext, ElectronApplication, Page } from '@playwright/test'
import { ROOT, WINDOWS, closeAll, openShell, ptySize, ready, typeLine } from '../fixtures'
import { makeData } from './data'

const exec = promisify(execFile)
const FIRST = 'SP_BENCH_OUTPUT_FIRST'
const LAST = 'SP_BENCH_OUTPUT_LAST'
const PROBE_TIMEOUT_MS = 330_000
const DISPLAY_TIMEOUT_MS = 420_000
const RESIZE_TIMEOUT_MS = 1800
const TARGET_COLS = 96
const TARGET_ROWS = 30
const RESIZE_ATTEMPTS = 6
const REPO = path.resolve(__dirname, '../../..')
const PYTHON = path.join(REPO, 'backend', '.venv', WINDOWS ? 'Scripts/python.exe' : 'bin/python')
const PROBE = path.join(__dirname, 'output_probe.py')
const ROOT_CASES = ['pipe', 'pty_program', 'ws_program', 'window_program', 'xterm_direct'] as const
const WINDOWS_CASES = [
  'pty_powershell', 'pty_cmd', 'ws_powershell', 'window_powershell',
  'pty_console_write', 'ws_console_write', 'window_console_write', 'conhost', 'windows_terminal',
] as const
type Case = (typeof ROOT_CASES)[number] | (typeof WINDOWS_CASES)[number]
type Timing = {
  reader_ms?: number
  reader_chunks?: number
  first_ms?: number
  stream_bytes?: number
  parsed_ms?: number
  visible_ms?: number
  measure_ms?: number
  shell?: string
  reason?: string
  profile_session?: string
  write_calls?: number
}
type Trial = Timing & {
  os: string; case: Case; round: number; order: number; warmup: boolean
  cols: number; rows: number; payload_bytes: number; status: 'ok' | 'failed' | 'unavailable'
}
type Server = { url: string; api: APIRequestContext }
type Window = { app: ElectronApplication; page: Page; close: () => Promise<void> }
type Write = (bytes: Uint8Array | string, callback?: () => void) => void
type Measure = {
  enter: number; first?: number; last?: number; parsed?: number; visible?: number; streamBytes?: number
  writes: number; restore: () => void
}
type BenchWindow = globalThis.Window & { spOutputBench?: Measure }

const csv = (field: unknown): string => '"' + String(field ?? '').replaceAll('"', '""') + '"'
const quotePS = (file: string) => "'" + file.replaceAll("'", "''") + "'"
const quoteSh = (word: string) => "'" + word.replaceAll("'", "'\"'\"'") + "'"

function save(trials: Trial[], out: string) {
  const fields: (keyof Trial)[] = [
    'os', 'case', 'round', 'order', 'warmup', 'cols', 'rows', 'payload_bytes', 'status',
    'reader_ms', 'reader_chunks', 'first_ms', 'stream_bytes', 'parsed_ms', 'visible_ms', 'measure_ms', 'shell', 'reason', 'profile_session', 'write_calls',
  ]
  fs.mkdirSync(out, { recursive: true })
  fs.writeFileSync(path.join(out, 'output-trials.json'), JSON.stringify(trials, null, 2) + '\n')
  fs.writeFileSync(path.join(out, 'output-trials.csv'), [
    fields.join(','), ...trials.map((trial) => fields.map((field) => csv(trial[field])).join(',')), '',
  ].join('\n'))
}

function powerShellBody(payload: string, result: string, kind: Case, size: [number, number]): string {
  const [rows, cols] = size
  const raw = kind.endsWith('console_write')
  // Measure-Command captures pipeline output. Out-Host sends every line to
  // the terminal, the same producer in all Get-Content cases and hosts.
  const action = raw
    ? `[Console]::Out.Write([IO.File]::ReadAllText(${quotePS(payload)}))`
    : `Get-Content -LiteralPath ${quotePS(payload)} -Encoding UTF8 | Out-Host`
  const setup = kind === 'conhost'
    ? `[Console]::SetWindowSize([Math]::Min([Console]::WindowWidth,${cols}),[Math]::Min([Console]::WindowHeight,${rows}))
[Console]::SetBufferSize(${cols},[Math]::Max([Console]::BufferHeight,${rows}))
[Console]::SetWindowSize(${cols},${rows})`
    : ''
  const hostCheck = kind === 'windows_terminal'
    ? "if (!$env:WT_SESSION) { throw 'No Windows Terminal session' }"
    : kind === 'conhost' ? "if ($env:WT_SESSION) { throw 'Console was delegated to Windows Terminal' }" : ''
  return `$ErrorActionPreference = 'Stop'
try {
  [Console]::OutputEncoding = [System.Text.UTF8Encoding]::new($false)
  ${setup}
  ${hostCheck}
  if ([Console]::WindowWidth -ne ${cols} -or [Console]::WindowHeight -ne ${rows}) {
    throw "Viewport is $([Console]::WindowWidth)x$([Console]::WindowHeight), expected ${cols}x${rows}"
  }
  [Console]::WriteLine('${FIRST}')
  $elapsed = Measure-Command { ${action} }
  [Console]::WriteLine('${LAST}')
  @{ measure_ms = $elapsed.TotalMilliseconds; shell = $PSVersionTable.PSVersion.ToString() } |
    ConvertTo-Json -Compress | Set-Content -LiteralPath ${quotePS(result)} -Encoding UTF8
} catch {
  @{ error = $_.Exception.Message } | ConvertTo-Json -Compress |
    Set-Content -LiteralPath ${quotePS(result)} -Encoding UTF8
  throw
}
`
}

async function probe(config: object): Promise<Timing> {
  try {
    const { stdout } = await exec(PYTHON, [PROBE, JSON.stringify(config)], { timeout: PROBE_TIMEOUT_MS })
    const result = JSON.parse(stdout)
    if (result.error) throw new Error(result.error)
    return result
  } catch (error) {
    const e = error as Error & { stdout?: string }
    let reason: string | undefined
    try { reason = JSON.parse(e.stdout ?? '').error } catch { /* process could not emit JSON */ }
    // A WS command carries the sandbox's session credentials internally.
    // The stable error message never includes execFile's entire argv.
    throw new Error(reason || (e.stdout === undefined ? e.message : 'reader exited without a measurement'))
  }
}

async function armWindow(page: Page, find: string) {
  await page.evaluate(({ find, firstMarker, lastMarker }) => {
    const term = (0, eval)(find) as { write: Write } | null
    if (!term) throw new Error('xterm.js instance missing')
    const original = term.write
    const state: Measure = { enter: 0, writes: 0, restore: () => {} }
    ;(window as BenchWindow).spOutputBench = state
    let tail = ''
    let raf = 0
    let bytes = 0
    let firstEnd = 0
    const decoder = new TextDecoder()
    const encoder = new TextEncoder()
    const onKey = (event: KeyboardEvent) => {
      if (event.key === 'Enter' && !state.enter) state.enter = performance.now()
    }
    window.addEventListener('keydown', onKey, true)
    state.restore = () => {
      term.write = original
      window.removeEventListener('keydown', onKey, true)
      cancelAnimationFrame(raf)
    }
    term.write = (chunk, callback) => {
      if (!state.enter || state.last !== undefined) return original.call(term, chunk, callback)
      state.writes++
      const text = tail + (typeof chunk === 'string' ? chunk : decoder.decode(chunk, { stream: true }))
      const base = bytes - encoder.encode(tail).length
      bytes += typeof chunk === 'string' ? encoder.encode(chunk).length : chunk.length
      const first = text.indexOf(firstMarker)
      if (state.first === undefined && first >= 0) {
        state.first = performance.now()
        firstEnd = base + encoder.encode(text.slice(0, first + firstMarker.length)).length
      }
      const last = text.indexOf(lastMarker)
      if (state.first !== undefined && last >= 0) {
        state.last = performance.now()
        state.streamBytes = base + encoder.encode(text.slice(0, last)).length - firstEnd
        return original.call(term, chunk, () => {
          state.parsed = performance.now()
          callback?.()
        })
      }
      tail = text.slice(-Math.max(firstMarker.length, lastMarker.length))
      return original.call(term, chunk, callback)
    }
    const frame = () => {
      if (state.parsed !== undefined && [...document.querySelectorAll('.aqua-screen .xterm-rows > div')]
        .some((row) => row.textContent?.trim() === lastMarker)) {
        state.visible = performance.now()
      } else {
        raf = requestAnimationFrame(frame)
      }
    }
    raf = requestAnimationFrame(frame)
  }, { find, firstMarker: FIRST, lastMarker: LAST })
}

async function windowTrial(page: Page, find: string, command: string): Promise<Timing> {
  await armWindow(page, find)
  try {
    await typeLine(page, command)
    await page.waitForFunction(() => (window as BenchWindow).spOutputBench?.visible,
      null, { timeout: DISPLAY_TIMEOUT_MS, polling: 200 })
    return await page.evaluate(() => {
      const { enter, first, last, parsed, visible, streamBytes, writes } = (window as BenchWindow).spOutputBench!
      return {
        first_ms: first! - enter,
        reader_ms: last! - first!, // at the same markers, immediately before xterm.write()
        parsed_ms: parsed! - first!,
        visible_ms: visible! - enter,
        stream_bytes: streamBytes,
        write_calls: writes,
      }
    })
  } finally {
    await page.evaluate(() => (window as BenchWindow).spOutputBench?.restore())
  }
}

async function directTrial(page: Page, find: string, bytes: number): Promise<Timing> {
  return page.evaluate(async ({ find, generator, bytes }) => {
    const make = (0, eval)(`(${generator})`) as (bytes: number, eol: string) => string
    const term = (0, eval)(find) as { write: Write } | null
    if (!term) throw new Error('xterm.js instance missing')
    const payload = new TextEncoder().encode(make(bytes, '\n').replaceAll('\n', '\r\n'))
    const chunkBytes = 64 * 1024
    const start = performance.now()
    for (let offset = 0; offset < payload.length; offset += chunkBytes) {
      const chunk = payload.subarray(offset, offset + chunkBytes)
      await new Promise<void>((resolve) => term.write(chunk, resolve))
    }
    return { parsed_ms: performance.now() - start, stream_bytes: payload.length }
  }, { find, generator: makeData.toString(), bytes })
}

async function fitViewport(window: Window, find: string) {
  const { page, app } = window
  for (let attempt = 0; attempt < RESIZE_ATTEMPTS; attempt++) {
    const screen = await page.evaluate((source) => {
      const term = (0, eval)(source) as { cols: number; rows: number }
      const { width, height } = document.querySelector('.aqua-screen .xterm-screen')!.getBoundingClientRect()
      return { cols: term.cols, rows: term.rows, width, height }
    }, find)
    if (screen.cols === TARGET_COLS && screen.rows === TARGET_ROWS) {
      const actual = await ptySize(page)
      if (actual[1] === TARGET_COLS && actual[0] === TARGET_ROWS) return
    }
    const delta = [
      Math.round((TARGET_COLS - screen.cols) * screen.width / screen.cols),
      Math.round((TARGET_ROWS - screen.rows) * screen.height / screen.rows),
    ]
    await app.evaluate(({ BrowserWindow }, [dx, dy]) => {
      const window = BrowserWindow.getAllWindows()[0]
      const [w, h] = window.getContentSize()
      window.setContentSize(w + dx, h + dy)
    }, delta)
    await page.waitForFunction(({ find, cols, rows }) => {
      const term = (0, eval)(find) as { cols: number; rows: number }
      return term.cols === cols && term.rows === rows
    }, { find, cols: TARGET_COLS, rows: TARGET_ROWS }, { timeout: RESIZE_TIMEOUT_MS }).catch(() => {})
  }
  throw new Error(`Cannot set the terminal viewport to ${TARGET_COLS}×${TARGET_ROWS}`)
}

export async function runOutputLadder(server: Server, launch: () => Promise<Window>, find: string) {
  const out = process.env.SP_BENCH_OUT || path.join(__dirname, 'out')
  const bytes = Number(process.env.SP_BENCH_OUTPUT_MB || 20) * 1e6
  const profile = process.env.SP_BENCH_OUTPUT_PROFILE
  const repeats = Number(process.env.SP_BENCH_OUTPUT_REPEATS || (profile ? 2 : 5))
  const dir = path.join(ROOT, 'work', 'output-ladder')
  fs.mkdirSync(dir, { recursive: true })
  const payload = path.join(dir, 'out20.txt')
  fs.writeFileSync(payload, makeData(bytes, '\n'))
  const payloadBytes = fs.statSync(payload).size
  const { api, url } = server
  const cases: Case[] = WINDOWS ? [...ROOT_CASES, ...WINDOWS_CASES] : [...ROOT_CASES]
  const profileCases: Case[] = profile === 'get-content'
    ? ['pty_powershell', 'ws_powershell', 'window_powershell', 'conhost', 'windows_terminal']
    : ['pty_console_write', 'ws_console_write', 'window_console_write']
  if (WINDOWS && profile) cases.splice(0, cases.length, ...profileCases)
  const trials: Trial[] = []
  const unavailable = new Map<Case, string>()
  await closeAll(api)
  const initial = await openShell(api, 'output-ladder-size')
  if (initial.backend !== 'plain') throw new Error('Use SP_E2E_KEEP=plain for matching PTY paths')
  const setup = await launch()
  const size: [number, number] = [TARGET_ROWS, TARGET_COLS]
  try {
    await ready(setup.page)
    await fitViewport(setup, find)
  } finally {
    await setup.close()
    await closeAll(api)
  }
  const [rows, cols] = size

  async function one(kind: Case, round: number): Promise<Timing> {
    const result = path.join(dir, `${kind}-${round}.json`)
    const script = path.join(dir, `${kind}.ps1`)
    if (WINDOWS) fs.writeFileSync(script, powerShellBody(payload, result, kind, size))
    const config = { kind, payload, cols, rows, script, result }
    const useProgram = kind.endsWith('_program')
    const command = WINDOWS
      ? useProgram ? `& ${quotePS(PYTHON)} -u ${quotePS(PROBE)} emit ${quotePS(payload)}`
        : `& ([scriptblock]::Create([IO.File]::ReadAllText(${quotePS(script)})))`
      : [PYTHON, '-u', PROBE, 'emit', payload].map(quoteSh).join(' ')
    if (kind === 'pty_cmd') {
      const cmd = path.join(dir, 'print.cmd')
      fs.writeFileSync(cmd, `@echo off\r\nchcp 65001 >nul\r\necho ${FIRST}\r\ntype out20.txt\r\necho ${LAST}\r\n`)
      return probe({ ...config, script: cmd })
    }
    if (kind.startsWith('ws_')) {
      const shell = await openShell(api, 'output-ladder-reader')
      try {
        const timing = await probe({ ...config, url, session: shell.id, command,
          token_file: path.join(ROOT, 'data', 'operator.token') })
        return { ...timing, ...await readMeasure(result, WINDOWS && !useProgram),
          profile_session: profile ? shell.id : undefined }
      } finally { await closeAll(api) }
    }
    if (kind.startsWith('window_') || kind === 'xterm_direct') {
      const shell = await openShell(api, 'output-ladder-window')
      const window = await launch()
      try {
        await ready(window.page)
        await fitViewport(window, find)
        if (kind === 'xterm_direct') return await directTrial(window.page, find, bytes)
        const timing = await windowTrial(window.page, find, command)
        return { ...timing, ...await readMeasure(result, WINDOWS && !useProgram),
          profile_session: profile ? shell.id : undefined }
      } finally {
        await window.close()
        await closeAll(api)
      }
    }
    const timing = await probe(config)
    return { ...timing, ...await readMeasure(result) }
  }

  async function readMeasure(file: string, required = false): Promise<Timing> {
    if (!required) return {}
    const deadline = Date.now() + 5000
    while (Date.now() < deadline) {
      if (fs.existsSync(file)) {
        let value: { error?: string } & Timing
        try { value = JSON.parse(fs.readFileSync(file, 'utf-8').replace(/^\uFEFF/, '')) }
        catch (error) {
          if (!(error instanceof SyntaxError)) throw error
          await new Promise((resolve) => setTimeout(resolve, 50))
          continue
        }
        if (value.error) throw new Error(value.error)
        return value
      }
      await new Promise((resolve) => setTimeout(resolve, 50))
    }
    throw new Error('PowerShell did not write its timing file')
  }

  // Rotate and reverse the order between rounds. Every path runs on this
  // same runner, with exactly one warm-up at round zero.
  for (let round = 0; round <= repeats; round++) {
    const rotated = [...cases.slice(round % cases.length), ...cases.slice(0, round % cases.length)]
    if (round % 2) rotated.reverse()
    for (const [order, kind] of rotated.entries()) {
      const base = { os: process.platform, case: kind, round, order: order + 1, warmup: round === 0,
        cols, rows, payload_bytes: payloadBytes }
      let record: Trial
      try {
        if (unavailable.has(kind)) record = { ...base, status: 'unavailable', reason: unavailable.get(kind) }
        else {
          const timing = await one(kind, round)
          if (timing.reader_ms !== undefined && (timing.stream_bytes ?? 0) < payloadBytes) {
            record = { ...base, ...timing, status: 'failed', reason: 'Reader received fewer bytes than the input fixture' }
          } else record = { ...base, ...timing, status: 'ok' }
        }
      } catch (error) {
        const reason = (error instanceof Error ? error.message : String(error)).split('\n')[0]
        record = { ...base, status: 'failed', reason }
        // A native terminal that cannot open on this runner is optional.
        if (kind === 'windows_terminal' || kind === 'conhost') {
          unavailable.set(kind, reason)
          record.status = 'unavailable'
        }
      }
      trials.push(record)
      console.log(`output ladder ${kind} #${round} ${record.status} ${JSON.stringify(record)}`)
      save(trials, out)
    }
  }
  if (trials.some((trial) => trial.status === 'failed')) throw new Error('Output ladder has missing required measurements; see CSV')
}
