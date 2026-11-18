import { test, expect, PROJECT, linksOut, ready, typeLine } from './fixtures'

/**
 * The window and the smart timer: working in a tab counts on that tab's
 * project. The sandbox server runs the timer (SP_SMART_TIMER=1 in
 * playwright.config.ts) and reads no idle time (no D-Bus session given to
 * it: "unknown" never pauses), so only the window's signals decide.
 */

type Auto = {
  working: Array<{ project: string; entry_id: string }>
  signals: Array<{ project: string; source: string; sec_ago: number }>
}

test.describe('smart timer', () => {
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

    // The window says so at the strip's end; a click opens the Timer page in the browser.
    const chip = page.locator('[data-timer]')
    await expect(chip).toHaveAttribute('data-timer', 'counting', { timeout: 40_000 })
    await expect(chip).toContainText(`${PROJECT} `)
    await expect(chip).toContainText('today')
    await chip.click()
    await expect.poll(() => linksOut(win.app)).toContain(`${server.url}/time`)

    await api.post('/api/time/auto/mode', { data: { project: PROJECT, mode: 'remind' } })
  })
})
