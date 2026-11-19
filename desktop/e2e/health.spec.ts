import fs from 'node:fs'
import path from 'node:path'
import { test, expect, PROJECT, ROOT, ready, typeLine, printFile, fullSize, lines } from './fixtures'

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

/** A day already in a work-time zone, with a suggestion due. */
async function seedYellow(page: import('@playwright/test').Page, minutes = 95) {
  // Written as the reloaded page starts: the page being left saves its own day on beforeunload, over anything written before.
  await page.addInitScript((run) => {
    if (sessionStorage.getItem('sp-e2e-seeded')) return
    sessionStorage.setItem('sp-e2e-seeded', '1')
    const now = Date.now()
    const d = new Date(now)
    const date = `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`
    localStorage.setItem('sp-term-health-day', JSON.stringify({
      date, run, wk: run, pomo: 0, inYellow: 5, inRed: 0, at: now, input: now, away: null, nextAt: 0,
      rem: { r1: { next: 999, count: 0, paused: false }, r2: { next: 999, count: 0, paused: false } }, breaks: [], done: [],
    }))
  }, minutes)
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

  for (const { zone, minutes } of [{ zone: 'yellow', minutes: 95 }, { zone: 'red', minutes: 185 }]) {
    test(`the ${zone} window border does not turn the content into a drag region`, async ({ win }) => {
      const { app, page } = win
      await ready(page)
      await seedYellow(page, minutes)
      await fullSize(app, page)
      await expect(page.locator('[data-health-label]')).toHaveAttribute('data-health-label', zone)
      const edge = page.locator('[data-health-edge]')
      await expect(edge).toHaveCount(1)
      expect(await edge.evaluate((el) => getComputedStyle(el).getPropertyValue('-webkit-app-region'))).toBe('none')
      expect(await edge.evaluate((el) => el.closest('.aq-app-drag') !== null)).toBe(false)

      const label = page.locator('[data-health-label]')
      await label.click()
      const today = page.getByRole('dialog', { name: 'Time today' })
      const close = today.getByRole('button', { name: 'Close', exact: true })
      await expect(today).toBeVisible()
      await expect(page.locator('[data-health-hover]')).toHaveCount(0)
      const box = (await close.boundingBox())!
      await page.mouse.move(box.x + box.width / 2, box.y + box.height / 2, { steps: 9 })
      await page.mouse.down()
      await page.mouse.up()
      await expect(today).toHaveCount(0)

      await page.getByRole('button', { name: 'Sidebar settings' }).click()
      const inward = page.getByRole('menuitemradio', { name: 'Open sidebars inward' })
      const option = (await inward.boundingBox())!
      await page.mouse.move(option.x + option.width / 2, option.y + option.height / 2, { steps: 9 })
      await page.mouse.down()
      await page.mouse.up()
      await expect(page.locator('[data-aqua-frame]')).toHaveAttribute('data-sidebar-mode', 'inward')
    })
  }

  for (const mode of ['smooth', 'rows']) test(`the yellow suggestion passes the wheel to the terminal (${mode})`, async ({ win, shell, server }) => {
    const { app, page } = win
    await ready(page)
    const url = new URL(page.url())
    url.searchParams.set('scroll', mode)
    await page.goto(url.toString())
    await seedYellow(page)
    await fullSize(app, page)
    const file = path.join(ROOT, 'work', 'health-scroll.txt')
    fs.writeFileSync(file, Array.from({ length: 180 }, (_, i) => `health-scroll-${String(i + 1).padStart(4, '0')}`).join('\n') + '\n')
    await typeLine(page, printFile(file))
    await expect.poll(() => lines(page)).toEqual(expect.arrayContaining([expect.stringContaining('health-scroll-0180')]))
    const numbers = (rows: string[]) => rows.flatMap((row) => {
      const value = /health-scroll-(\d+)/.exec(row)?.[1]
      return value ? [Number(value)] : []
    })
    const first = Math.min(...numbers(await lines(page)))

    const label = page.locator('[data-health-label="yellow"]')
    const card = page.locator('[data-health-hover]')
    await label.hover()
    await expect(card).toBeVisible()
    const cardBox = (await card.boundingBox())!
    const screen = (await page.locator('.aqua-screen .xterm-screen').boundingBox())!
    const x = Math.max(cardBox.x, screen.x) + 24
    const y = Math.max(cardBox.y, screen.y) + 12
    expect(y).toBeLessThan(cardBox.y + cardBox.height)
    await page.evaluate(() => {
      document.addEventListener('wheel', (event) => {
        if (document.body.dataset.testWheelTarget || !event.isTrusted || !(event.target instanceof Element)) return
        document.body.dataset.testWheelTarget = event.target.closest('[data-health-hover]') ? 'suggestion' : 'terminal'
      }, { capture: true })
    })
    await page.mouse.move(x, y)
    await expect(card).toBeVisible()
    await page.mouse.wheel(0, mode === 'smooth' ? -550 : -100)
    await expect(page.locator('body')).toHaveAttribute('data-test-wheel-target', 'suggestion')
    await expect(card).toHaveCount(0)
    const reader = page.locator('.aqua-screen .sp-reader')
    if (shell.backend === 'tmux' && mode === 'smooth') await expect(reader).toBeVisible()
    if (shell.backend === 'tmux' && mode === 'rows') {
      // The first report enters tmux's copy mode. Its next report scrolls.
      await expect.poll(async () => {
        const pos = await server.api.get(`/api/terminal/sessions/${shell.id}/pos`)
        return (await pos.json()).in_mode
      }).toBe(true)
      await page.mouse.wheel(0, -100)
    }
    const rows = () => (shell.backend === 'tmux' && mode === 'smooth' ? reader.locator('.xterm-rows > div').allTextContents() : lines(page))
    await expect.poll(async () => Math.min(...numbers(await rows()))).toBeLessThan(first)
    // In row mode tmux scrolls by a fixed number of rows per wheel report.
    for (let i = 0; i < 4; i++) await page.mouse.wheel(0, 500)
    if (shell.backend === 'tmux' && mode === 'smooth') await expect(reader).toHaveCount(0)
    await expect.poll(() => lines(page)).toEqual(expect.arrayContaining([expect.stringContaining('health-scroll-0180')]))
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
    // Inside the window, also a narrow one (headless opens it at 420×240, the label near the left edge).
    const card = (await page.locator('[data-health-hover]').boundingBox())!
    expect(card.x, 'the card\'s left edge in the window').toBeGreaterThanOrEqual(0)
    expect(card.x + card.width, 'the card\'s right edge in the window').toBeLessThanOrEqual(await page.evaluate(() => innerWidth))
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
