import { spawn, type ChildProcess } from 'node:child_process'
import { test, expect, echoCalc, KEEP_PLAIN, openShell, ready, typeLine, WINDOWS } from './fixtures'
import { tmuxSockets } from './sockets'

/**
 * Switching tabs (tk_74f2d3ba). The operator: a switch was not instant — the
 * cursor's line blinked alone for a while before the tab's text came — and
 * the text sometimes filled only two thirds of the width.
 *
 * Measured frame by frame from the click on the tab to the first frame that
 * shows the tab's own text, and the size the program in the terminal gets
 * (`stty size`) against the columns the window drew.
 */

const strip = (page: import('@playwright/test').Page) => page.getByRole('tablist', { name: 'Chats' })
const tabOf = (page: import('@playwright/test').Page, label: string) => strip(page).getByRole('tab', { name: new RegExp(`^${label} `) })

type Switch = { ms: number; frames: number; blank: number; cols: number; widthRatio: number }

/** Click the tab, and on every frame after the press look for `mark` in the terminal in front. */
async function measureSwitch(page: import('@playwright/test').Page, label: string, mark: string): Promise<Switch> {
  await page.evaluate((m) => {
    const w = window as unknown as { __sw: { t0: number; seen: number; frames: number; blank: number; cols: number; widthRatio: number; done: boolean } }
    w.__sw = { t0: 0, seen: 0, frames: 0, blank: 0, cols: 0, widthRatio: 0, done: false }
    addEventListener('pointerdown', (e) => {
      if (!(e.target as HTMLElement).closest('[role=tab]')) return
      w.__sw.t0 = performance.now()
      const loop = () => {
        const s = w.__sw
        const screen = document.querySelector<HTMLElement>('.aqua-screen')
        const rows = screen?.querySelector('.xterm-rows')
        const text = rows?.textContent ?? ''
        s.frames += 1
        if (!text.replace(/\s/g, '')) s.blank += 1
        if (text.includes(m)) {
          s.seen = performance.now()
          const xs = screen!.querySelector<HTMLElement>('.xterm-screen')!
          s.widthRatio = xs.getBoundingClientRect().width / screen!.getBoundingClientRect().width
          s.cols = Number(screen!.querySelector<HTMLElement>('[data-cols]')?.dataset.cols ?? 0)
          s.done = true
          return
        }
        if (performance.now() - s.t0 > 10_000) { s.done = true; return }
        requestAnimationFrame(loop)
      }
      requestAnimationFrame(loop)
    }, { capture: true, once: true })
  }, mark)
  await tabOf(page, label).click()
  await page.waitForFunction(() => (window as unknown as { __sw: { done: boolean } }).__sw.done, null, { timeout: 15_000 })
  const s = await page.evaluate(() => (window as unknown as { __sw: { t0: number; seen: number; frames: number; blank: number; cols: number; widthRatio: number } }).__sw)
  return { ms: s.seen ? Math.round(s.seen - s.t0) : -1, frames: s.frames, blank: s.blank, cols: s.cols, widthRatio: Math.round(s.widthRatio * 1000) / 1000 }
}

/** The program's own idea of the width: `stty size` → cols. */
async function sttyCols(page: import('@playwright/test').Page): Promise<number> {
  const mark = `sz${Math.random().toString(36).slice(2, 7)}`
  await typeLine(page, `echo ${mark}-$(stty size | tr ' ' x)`)
  let cols = 0
  await expect.poll(async () => {
    const all = await page.locator('.aqua-screen .xterm-rows > div').evaluateAll((els) => els.map((e) => (e.textContent ?? '').replace(/ /g, ' ').trim()))
    // (The mark is random letters and may hold an x itself.)
    for (const x of all) { const m = new RegExp(`^${mark}-(\\d+)x(\\d+)$`).exec(x); if (m) cols = Number(m[2]) }
    return cols
  }).toBeGreaterThan(0)
  return cols
}

/** A second view of a tmux session, at a smaller size: a control-mode client (another page, a detached window). */
function smallClient(sid: string, cols: number, rows: number): ChildProcess {
  const [sock] = tmuxSockets(process.env.SP_DESKTOP_E2E_TMUX!)
  const c = spawn('tmux', ['-S', sock, '-C', 'attach', '-t', `mk-${sid}`], { stdio: ['pipe', 'ignore', 'ignore'] })
  c.stdin!.write(`refresh-client -C ${cols}x${rows}\n`)
  return c
}

test.describe('switching tabs', () => {
  test('the tab\'s text shows at once, at the window\'s width, also with a smaller view of it attached', async ({ win, shell, server }) => {
    test.skip(WINDOWS, 'sh')
    test.setTimeout(120_000)
    const { page } = win
    const second = await openShell(server.api, 'e2e-second')
    await page.reload()
    await ready(page)
    const marks: Record<string, string> = {}
    for (const [label, m] of [[shell.label, 'a'], [second.label, 'b']] as const) {
      await tabOf(page, label).click()
      await ready(page)
      await typeLine(page, echoCalc(`sw-${m}-`, '6*7', '-mark'))
      marks[label] = `sw-${m}-42-mark`
      await expect(page.locator('.aqua-screen .xterm-rows')).toContainText(marks[label])
    }

    const runs: Switch[] = []
    for (let i = 0; i < 8; i++) {
      const label = i % 2 === 0 ? shell.label : second.label
      runs.push(await measureSwitch(page, label, marks[label]))
      await page.waitForTimeout(300)
    }
    console.log(`switch ${KEEP_PLAIN ? 'plain' : 'tmux'}: ${JSON.stringify(runs)}`)
    // Each switch shows the tab's text; the first view of a tab may connect, every later one is in place.
    for (const r of runs) expect(r.ms, JSON.stringify(r)).toBeGreaterThanOrEqual(0)
    const later = runs.slice(2)
    for (const r of later) expect.soft(r.frames, `frames until the tab's text, ${JSON.stringify(r)}`).toBeLessThanOrEqual(3)
    for (const r of runs) expect(r.widthRatio, 'the text across the whole width').toBeGreaterThan(0.95)

    // The program in the terminal gets the columns the window drew.
    const cols = Number(await page.locator('.aqua-screen [data-cols]').getAttribute('data-cols'))
    expect(cols).toBeGreaterThan(40)
    expect(await sttyCols(page)).toBe(cols)

    if (KEEP_PLAIN) return
    // A second view of this tab at 60 columns: the window still gets its own width after a switch away and back.
    const other = smallClient(shell.id, 60, 20)
    try {
      await page.waitForTimeout(500)
      await measureSwitch(page, second.label, marks[second.label])
      // The smaller view is the latest now: tmux sized the terminal to it.
      const paneCols = async () => ((await (await server.api.get(`/api/terminal/sessions/${shell.id}/pos`)).json()) as { cols: number }).cols
      await other.stdin!.write(`refresh-client -C 60x20\n`)
      await expect.poll(paneCols, { message: 'the small view took the terminal' }).toBe(60)
      const back = await measureSwitch(page, shell.label, marks[shell.label])
      expect(back.ms).toBeGreaterThanOrEqual(0)
      // Back in front, before a key is typed: the window's view is the latest again, at its own width.
      await expect.poll(paneCols, { message: 'the window took its terminal back' }).toBe(cols)
      expect(await sttyCols(page)).toBe(cols)
    } finally { other.kill() }
  })
})
