import fs from 'node:fs'
import path from 'node:path'
import { test, expect, KEEP_PLAIN, PROJECT, ROOT, linksOut, ready, typeLine } from './fixtures'

/**
 * The window and the smart timer: working in a tab counts on that tab's
 * project. The sandbox server runs the timer (SP_SMART_TIMER=1 in
 * playwright.config.ts) and reads no host idle time, so the test can
 * exercise the window's activity signals independently of the desktop.
 */

type Auto = {
  idle_sec: number | null
  working: Array<{ project: string; entry_id: string }>
  signals: Array<{ project: string; source: string; sec_ago: number }>
}

/** typing.csv rows of the project: one per tick of keys the window sent. */
const typingRows = () => {
  try {
    return fs.readFileSync(path.join(ROOT, 'data', 'terminal', 'typing.csv'), 'utf8')
      .split('\n').filter((l) => l.split(',')[2] === PROJECT).length
  } catch { return 0 }
}

test.describe('smart timer', () => {
  test('clicks in a terminal are not typing: the window beats, the socket does not, and no keys are counted', async ({ win, server }) => {
    const { page } = win
    const api = server.api
    await ready(page)
    const auto = async () => (await (await api.get('/api/time/auto')).json()) as Auto
    expect((await auto()).idle_sec).toBeNull()
    const before = typingRows()
    const screen = page.locator('.aqua-screen .xterm-screen')
    const clickedAt = Date.now() - 1000
    // In tmux (mouse on) each click is a press and a release report, and
    // focus reports come with it; xterm answered tmux's questions on attach.
    for (const [x, y] of [[40, 30], [200, 60], [120, 90], [300, 40], [60, 120]]) {
      await screen.click({ position: { x, y } })
      await page.waitForTimeout(150)
    }
    const focused = await page.evaluate(() => document.hasFocus())
    if (focused) {
      await expect.poll(async () => (await auto()).signals.find((s) => s.project === PROJECT)?.source,
        { message: 'a beat from the window' }).toBe('window')
    }
    // Long enough for the socket's messages and a first typing tick (sent at once).
    await page.waitForTimeout(2_000)
    // A beat from typing in an earlier spec may still be listed: only one
    // newer than the first click would be the clicks'.
    const signal = (await auto()).signals.find((s) => s.project === PROJECT)
    const sinceClicks = (Date.now() - clickedAt) / 1000
    const fromClicks = signal?.source === 'terminal' && signal.sec_ago <= sinceClicks
    expect(fromClicks, `clicks beat the timer through the socket (${KEEP_PLAIN ? 'plain' : 'tmux'}): ${JSON.stringify(signal)}`).toBe(false)
    expect(typingRows(), 'clicks counted as keys').toBe(before)
  })

  test('a click in the tab is a window beat; typing there starts the project\'s auto time, it grows, and the strip shows it', async ({ win, server }) => {
    test.setTimeout(120_000)
    const { page } = win
    const api = server.api
    const mode = await api.post('/api/time/auto/mode', { data: { project: PROJECT, mode: 'auto' } })
    expect(mode.ok(), await mode.text()).toBeTruthy()
    await ready(page)

    // A click in the terminal sends no bytes to the shell: only the window's beat can carry it.
    const focused = await page.evaluate(() => document.hasFocus())
    console.log(`window focused: ${focused}`)
    await page.locator('.aqua-screen .xterm-screen').click()
    const auto = async () => (await (await api.get('/api/time/auto')).json()) as Auto
    if (focused) {
      await expect.poll(async () => (await auto()).signals.find((s) => s.project === PROJECT)?.source,
        { message: 'a beat from the window' }).toBe('window')
    }

    // Typing: the auto span opens on the next tick (every 15 s).
    await typeLine(page, 'echo counting')
    await expect.poll(async () => (await auto()).working.map((w) => w.project), { timeout: 40_000, message: 'an auto span on the project' })
      .toContain(PROJECT)
    const entryId = (await auto()).working.find((w) => w.project === PROJECT)!.entry_id
    const elapsed = async () => {
      const r = (await (await api.get('/api/time/running')).json()) as { running: Array<{ id: string; source?: string; elapsed_sec: number }> }
      return r.running.find((e) => e.id === entryId)
    }
    const first = await elapsed()
    expect(first?.source).toBe('auto')
    await typeLine(page, 'echo still-here')
    await expect.poll(async () => (await elapsed())?.elapsed_sec ?? 0, { timeout: 20_000 }).toBeGreaterThan(first!.elapsed_sec)
    // Still the same span: the typing kept it open.
    expect((await auto()).working.find((w) => w.project === PROJECT)?.entry_id).toBe(entryId)

    // The timers live above the tabs; a click opens the Timer page in the browser.
    const chip = page.locator('[data-window-title] [data-timer]')
    await expect(chip).toHaveAttribute('data-timer', 'counting', { timeout: 40_000 })
    await expect(chip).toContainText(`${PROJECT} `)
    await expect(chip).toContainText('today')
    await chip.click()
    await expect.poll(() => linksOut(win.app)).toContain(`${server.url}/time`)
    await expect(page.locator('[data-window-tabs] [data-timer]')).toHaveCount(0)

    await api.post('/api/time/auto/mode', { data: { project: PROJECT, mode: 'remind' } })
  })
})
