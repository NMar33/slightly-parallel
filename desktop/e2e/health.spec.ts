import { test, expect, PROJECT, ready, typeLine } from './fixtures'

/**
 * Health and time in the window, variant a «quiet» (tk_810245f2,
 * tk_caf2b06a): the time label sits in the title row (folded too), the
 * suggestion shows on hover, and «Перерыв» stops the project's time on the
 * server — the smart timer's span closes and a running manual timer pauses
 * — until «Готово» resumes them (POST /api/time/auto/break).
 *
 * The sandbox server runs the smart timer (SP_SMART_TIMER=1) and reads no
 * idle time, so only the window's signals decide.
 */

type Auto = { working: Array<{ project: string; entry_id: string }> }
type Running = { running: Array<{ id: string; project: string; paused_at?: string | null; ended_at?: string | null; source?: string | null }> }
type Brk = { on: boolean; paused?: string[]; today: Array<{ note: string }> }

/** A day already 95 minutes into work: the yellow zone, a suggestion due. */
async function seedYellow(page: import('@playwright/test').Page) {
  // Written as the reloaded page starts: the page being left saves its own day on beforeunload, over anything written before.
  await page.addInitScript(() => {
    if (sessionStorage.getItem('sp-e2e-seeded')) return
    sessionStorage.setItem('sp-e2e-seeded', '1')
    const now = Date.now()
    const d = new Date(now)
    const date = `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`
    localStorage.setItem('sp-term-health-day', JSON.stringify({
      date, run: 95, wk: 95, pomo: 0, inYellow: 5, inRed: 0, at: now, input: now, away: null, nextAt: 0,
      rem: { r1: { next: 999, count: 0, paused: false }, r2: { next: 999, count: 0, paused: false } }, breaks: [], done: [],
    }))
  })
  await page.reload()
  await ready(page)
}

test.describe('health and time', () => {
  test.afterEach(async ({ server }) => {
    // Never leave a break or a mode behind for the next spec.
    await server.api.post('/api/time/auto/break', { data: { on: false } })
    await server.api.post('/api/time/auto/mode', { data: { project: PROJECT, mode: 'remind' } })
    // Nor a manual timer: a failed run left it, and the next start was refused (409).
    const open = ((await (await server.api.get('/api/time/running')).json()) as Running).running
    for (const e of open) if (e.project === PROJECT && e.source !== 'auto') await server.api.post(`/api/time/${e.id}/stop`)
  })

  test('the time label is in the title row, folded too; hover shows the suggestion and its buttons', async ({ win }) => {
    const { page } = win
    await ready(page)
    await seedYellow(page)
    const frame = page.locator('[data-aqua-frame]')
    const label = page.locator('[data-health-label]')
    await expect(label).toHaveAttribute('data-health-label', 'yellow')
    await expect(label).toHaveText(/^1:3\d$/)
    await expect(page.locator('[data-health-tint="yellow"]')).toHaveCount(1)
    const top = (await frame.boundingBox())!.y
    expect((await label.boundingBox())!.y - top, 'the label in the title row').toBeLessThan(34)

    // Nothing shows until the pointer is on the label.
    await expect(page.locator('[data-health-hover]')).toHaveCount(0)
    await label.hover()
    await expect(page.locator('[data-health-suggestion="yellow"]')).toBeVisible()
    await expect(page.locator('[data-health-did]')).toBeVisible()
    await expect(page.locator('[data-health-later]')).toBeVisible()
    // The terminal keeps the keyboard: a click on «Позже» leaves the focus in it.
    await page.locator('.aqua-screen .xterm-screen').click()
    await label.hover()
    await page.locator('[data-health-later]').click()
    expect(await page.evaluate(() => !!document.activeElement?.closest('.aqua-screen'))).toBe(true)
    await page.mouse.move(5, 400)
    await expect(page.locator('[data-health-hover]')).toHaveCount(0)

    // Folded: still there, in the thin row.
    await page.keyboard.press('Alt+KeyT')
    await expect(frame).toHaveAttribute('data-folded', 'true')
    await expect(label).toBeVisible()
    expect((await label.boundingBox())!.y - (await frame.boundingBox())!.y, 'the label in the folded row').toBeLessThan(14)
    await page.keyboard.press('Alt+KeyT')
    await expect(frame).not.toHaveAttribute('data-folded', 'true')
  })

  test('a break from the window stops the project\'s time on the server; «Готово» starts it again', async ({ win, server }) => {
    test.setTimeout(150_000)
    const { page } = win
    const api = server.api
    expect((await api.post('/api/time/auto/mode', { data: { project: PROJECT, mode: 'auto' } })).ok()).toBeTruthy()
    await ready(page)
    const auto = async () => (await (await api.get('/api/time/auto')).json()) as Auto
    const running = async () => ((await (await api.get('/api/time/running')).json()) as Running).running
    const brk = async () => (await (await api.get('/api/time/auto/break')).json()) as Brk

    // A manual timer on the project, and the smart timer counting from typing.
    const manual = await api.post('/api/time/start', { data: { project: PROJECT, sprint_id: 'sp_health_e2e', share_pct: 10 } })
    expect(manual.ok(), await manual.text()).toBeTruthy()
    const manualId = ((await manual.json()) as { id: string }).id
    await typeLine(page, 'echo before-break')
    await expect.poll(async () => (await auto()).working.map((w) => w.project), { timeout: 40_000, message: 'an auto span on the project' })
      .toContain(PROJECT)

    // «Перерыв» from the label's hover card.
    await page.locator('[data-health-label]').hover()
    await page.locator('[data-health-start]').click()
    await expect(page.locator('[data-health-break]')).toBeVisible()
    await expect(page.locator('[data-health-label]')).toHaveAttribute('data-health-label', 'break')
    await expect.poll(async () => (await brk()).on).toBe(true)
    await expect.poll(async () => (await auto()).working.map((w) => w.project)).not.toContain(PROJECT)
    await expect.poll(async () => (await running()).find((e) => e.id === manualId)?.paused_at || '').not.toBe('')

    // Typing during the break counts nothing: a full tick (15 s) later there is still no span.
    await typeLine(page, 'echo on-break')
    await page.waitForTimeout(17_000)
    expect((await auto()).working.map((w) => w.project)).not.toContain(PROJECT)
    expect((await running()).some((e) => e.project === PROJECT && e.source === 'auto')).toBe(false)

    // «Готово» with a note: the manual timer runs again, typing opens a span again.
    await page.locator('[data-health-note]').fill('e2e tea')
    await page.locator('[data-health-done]').click()
    await expect(page.locator('[data-health-break]')).toHaveCount(0)
    await expect.poll(async () => (await brk()).on).toBe(false)
    expect((await brk()).today.map((b) => b.note)).toContain('e2e tea')
    // Running again: still listed, its pause cleared (the server answers null for an empty column).
    await expect.poll(async () => {
      const e = (await running()).find((r) => r.id === manualId)
      return e ? (e.paused_at || 'running') : 'missing'
    }).toBe('running')
    await page.locator('.aqua-screen .xterm-screen').click()
    await typeLine(page, 'echo after-break')
    await expect.poll(async () => (await auto()).working.map((w) => w.project), { timeout: 40_000, message: 'the auto span again' })
      .toContain(PROJECT)
    await expect(page.locator('[data-health-label]')).toHaveText(/^0:0\d$/)
  })
})
