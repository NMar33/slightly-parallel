import fs from 'node:fs'
import path from 'node:path'
import type { ElectronApplication, Page } from '@playwright/test'
import { test, expect, ROOT, URL_, WINDOWS, printFile, ready, typeLine, lines } from './fixtures'
import { runPlan, touchpad } from './scrollProbe'

/**
 * The terminal log (tk_f89e84c4) in the real window.
 *
 * Full on: a paste that reaches the socket twice (two paste events 0 ms
 * apart, as Ctrl+Shift+V did when the page and Chromium both pasted) and a
 * scroll stall (a 300 ms task in the middle of a touchpad scroll, as the
 * freeze after a click on a path) both show up on /monitor as findings.
 * What was typed and printed is in no file of the log.
 *
 * Light on: the scroll workload of scroll.spec.ts (3000 lines printed, a
 * touchpad up and down) run with the log off, light and full; the log's own
 * time stays under 1% of the run, its minute under 64 KB. CPU time of the
 * page's process and its heap are printed for each mode (notes/2611-18-terminal-log.md).
 */

const OUT = process.env.SP_TERMLOG_OUT
const SECRET = 'sp-secret-7f3q'
const SHOTS = process.env.SP_TERMLOG_SHOTS

type Log = {
  mode: string
  flush: (hiding?: boolean, rowDue?: boolean) => Promise<void>
  events: () => unknown[]
  row: () => Record<string, unknown> | null
}
const log = <T>(page: Page, fn: (l: Log) => T | Promise<T>) =>
  page.evaluate(`(${fn.toString()})(window.__spTermLog)`) as Promise<T>

async function setMode(page: Page, mode: string) {
  await page.evaluate(async (m) => {
    const r = await fetch('/api/terminal/log/mode', { method: 'POST', headers: { 'content-type': 'application/json' }, body: JSON.stringify(m === 'full' ? { mode: m, hours: 1 } : { mode: m }) })
    const got = await r.json() as { mode: string }
    ;(window as unknown as { __spTermLog: { setMode: (x: string) => void } }).__spTermLog.setMode(got.mode)
  }, mode)
  await expect.poll(() => log(page, (l) => l.mode)).toBe(mode)
}

function numbered(): string {
  const file = path.join(ROOT, 'work', 'numbered.txt')
  if (!fs.existsSync(file)) {
    fs.writeFileSync(file, Array.from({ length: 3000 }, (_, i) => `L${String(i + 1).padStart(5, '0')} the quick brown fox jumps over the lazy dog ${i % 10}`).join('\n') + '\n')
  }
  return file
}

async function fill(page: Page) {
  await typeLine(page, printFile(numbered()))
  await expect.poll(async () => (await lines(page)).some((l) => l.startsWith('L03000')), { timeout: 30_000 }).toBe(true)
  await page.waitForTimeout(300)
}

const logFiles = () => {
  const d = path.join(ROOT, 'data', 'terminal', 'log')
  return fs.existsSync(d) ? fs.readdirSync(d).map((f) => path.join(d, f)) : []
}

/** CPU seconds of the window's page process so far (Linux: /proc). */
async function pageCpu(app: ElectronApplication): Promise<number | null> {
  const pid = await app.evaluate(({ BrowserWindow }) => BrowserWindow.getAllWindows()[0]!.webContents.getOSProcessId())
  try {
    const f = fs.readFileSync(`/proc/${pid}/stat`, 'utf-8')
    const parts = f.slice(f.lastIndexOf(')') + 2).split(' ')
    return (Number(parts[11]) + Number(parts[12])) / 100
  } catch { return null }
}

test.describe('the terminal log', () => {
  test.afterEach(async ({ server }) => {
    await server.api.post('/api/terminal/log/mode', { data: { mode: 'light' } })
  })

  test('Full: a doubled paste and a scroll stall are found and shown on the Monitor; no text is kept', async ({ win, server }) => {
    test.skip(WINDOWS, 'the stall needs the sh workload')
    const { page } = win
    await ready(page)
    await expect.poll(() => page.evaluate(() => !!(window as unknown as { __spTermLog?: unknown }).__spTermLog)).toBe(true)
    await setMode(page, 'full')

    // Typed and printed: must be in no file of the log.
    await typeLine(page, `echo ${SECRET}-$((6*7))`)
    await expect.poll(async () => (await lines(page)).some((l) => l.trim() === `${SECRET}-42`)).toBe(true)

    // A paste reaching the socket twice: two paste events on xterm's textarea at once.
    await page.evaluate((text) => {
      const ta = document.querySelector('.aqua-screen .xterm-helper-textarea') as HTMLTextAreaElement
      for (let i = 0; i < 2; i++) {
        const dt = new DataTransfer()
        dt.setData('text/plain', text)
        ta.dispatchEvent(new ClipboardEvent('paste', { clipboardData: dt, bubbles: true, cancelable: true }))
      }
    }, `# ${SECRET}-pasted`)
    await page.keyboard.press('Control+C')

    // A scroll stall: a 300 ms task in the middle of a touchpad scroll.
    await fill(page)
    await page.evaluate(() => new Promise<void>((done) => {
      const screen = document.querySelector('.aqua-screen .xterm-screen') as HTMLElement
      const r = screen.getBoundingClientRect()
      let f = 0
      const step = () => {
        const at = document.elementFromPoint(r.left + r.width / 2, r.top + r.height / 2) ?? screen
        at.dispatchEvent(new WheelEvent('wheel', { deltaY: -6, deltaMode: 0, bubbles: true, cancelable: true, clientX: r.left + r.width / 2, clientY: r.top + r.height / 2 }))
        if (f === 15) { const end = performance.now() + 300; while (performance.now() < end) { /* the stall */ } }
        if (++f < 40) requestAnimationFrame(step); else done()
      }
      requestAnimationFrame(step)
    }))
    const found = await log(page, async (l) => { const r = l.row(); await l.flush(); return r })
    const kinds = ((found?.findings ?? []) as Array<{ kind: string }>).map((f) => f.kind)
    expect(kinds, JSON.stringify(found?.findings)).toContain('paste-twice')
    expect(kinds).toContain('scroll-stall')

    // The files of the log: events kept, no text.
    const files = logFiles()
    expect(files.some((f) => path.basename(f).startsWith('full-'))).toBe(true)
    for (const f of files) expect(fs.readFileSync(f, 'utf-8'), path.basename(f)).not.toContain(SECRET)

    // The Monitor shows both, in the same window.
    await page.goto(`${URL_}/monitor`)
    const list = page.getByTestId('term-log-findings')
    await expect(list.locator('[data-kind="paste-twice"]').first()).toBeVisible({ timeout: 15_000 })
    await expect(list.locator('[data-kind="scroll-stall"]').first()).toBeVisible()
    await expect(page.getByTestId('term-log-mode')).toContainText(/full|полный/)
    await page.getByTestId('term-log-findings').scrollIntoViewIfNeeded()
    if (SHOTS) {
      await win.app.evaluate(({ BrowserWindow }) => BrowserWindow.getAllWindows()[0]!.setSize(1440, 1100))
      await page.waitForTimeout(400)
      await page.locator('section[aria-label="Terminal"]').first().evaluate((el) => el.scrollIntoView({ block: 'start' }))
      await page.waitForTimeout(300)
      await page.screenshot({ path: path.join(SHOTS, 'monitor-terminal.png') })
    }
    // The report: a file, no text.
    const rep = await server.api.get('/api/terminal/log/report')
    expect(rep.ok()).toBeTruthy()
    const body = await rep.text()
    expect(body).not.toContain(SECRET)
    expect(JSON.parse(body).full_last_hour.length).toBeGreaterThan(10)
  })

  test('Light: the log costs under 1% of the time of a scroll workload', async ({ win }) => {
    test.skip(WINDOWS, 'the workload needs sh')
    const { page, app } = win
    await ready(page)
    await expect.poll(() => page.evaluate(() => !!(window as unknown as { __spTermLog?: unknown }).__spTermLog)).toBe(true)
    await fill(page)
    const plan = [...touchpad(90, -1), ...touchpad(90, 1)]
    const results: Record<string, Array<Record<string, number | null>>> = { off: [], light: [], full: [] }
    for (let round = 0; round < 2; round++) {
      for (const mode of ['off', 'light', 'full'] as const) {
        await setMode(page, mode)
        // A fresh minute: the counters of the run alone.
        await log(page, (l) => l.flush(false, true))
        const heap0 = await page.evaluate(() => (performance as unknown as { memory?: { usedJSHeapSize: number } }).memory?.usedJSHeapSize ?? 0)
        const cpu0 = await pageCpu(app)
        // The tmux reader the last scroll opened steps aside: one live terminal to type in.
        await page.keyboard.press('Escape')
        await expect(page.getByRole('textbox', { name: 'Terminal input' })).toHaveCount(1)
        const t0 = Date.now()
        await typeLine(page, printFile(numbered()))
        await page.waitForTimeout(800)
        await runPlan(page, plan)
        const wall = Date.now() - t0
        const cpu1 = await pageCpu(app)
        const heap1 = await page.evaluate(() => (performance as unknown as { memory?: { usedJSHeapSize: number } }).memory?.usedJSHeapSize ?? 0)
        const row = await log(page, (l) => l.row())
        const self = (row?.self as { ms?: number; events?: number } | undefined) ?? {}
        results[mode]!.push({
          wall_ms: wall, cpu_s: cpu0 != null && cpu1 != null ? Math.round((cpu1 - cpu0) * 100) / 100 : null,
          self_ms: self.ms ?? 0, self_pct: Math.round(((self.ms ?? 0) / wall) * 10000) / 100,
          events: self.events ?? 0, row_bytes: row ? JSON.stringify(row).length : 0, heap_mb: Math.round((heap1 - heap0) / 1e4) / 100,
        })
      }
    }
    console.log('termlog overhead', JSON.stringify(results))
    if (OUT) fs.writeFileSync(OUT, JSON.stringify(results, null, 1))
    // Over both rounds: one round on a busy machine is noise.
    const sum = (k: string) => results.light!.reduce((a, r) => a + Number(r[k] ?? 0), 0)
    expect(100 * sum('self_ms') / sum('wall_ms'), 'the light log’s own time, % of the run').toBeLessThan(1)
    for (const r of results.light!) expect(r.row_bytes!, 'a light minute').toBeLessThan(64_000)
    for (const r of results.off!) expect(r.self_ms).toBe(0)
  })
})
