import type { Page } from '@playwright/test'
import { test, expect, WINDOWS, ready, typeLine, expectLine } from './fixtures'

/**
 * The terminal's colour schemes (tk_83077846) in the real window.
 *
 * Settings › Terminal › Colour scheme writes `terminal.scheme` and
 * `terminal.scheme_scope`. Here the route sets them, and the window, told
 * the way it is told when the operator comes back to it (it reads the
 * settings again on focus), takes the scheme without a reload: xterm's
 * ground and a printed red change to the scheme's; "whole window" turns the
 * tab strip to the scheme's colours; sp-now brings back the colours as they
 * were. The window's own quick switch (the palette in the title row) picks a
 * scheme in one click.
 */

/** SP_SCHEME_SHOTS=<folder>: pictures of the window in each step, to look at. */
const SHOTS = process.env.SP_SCHEME_SHOTS
const shot = async (page: Page, name: string) => { if (SHOTS) await page.screenshot({ path: `${SHOTS}/${name}.png` }) }

const rgb = (hex: string) => `rgb(${[1, 3, 5].map((i) => parseInt(hex.slice(i, i + 2), 16)).join(', ')})`

/** xterm's ground (the viewport) and the colour of the printed word `word`. */
const colours = (page: Page, word: string) => page.evaluate((w) => {
  const viewport = document.querySelector('.aqua-screen .xterm-viewport') as HTMLElement | null
  const span = [...document.querySelectorAll('.aqua-screen .xterm-rows span')].find((s) => s.textContent === w) as HTMLElement | undefined
  return {
    ground: viewport ? getComputedStyle(viewport).backgroundColor : '',
    word: span ? getComputedStyle(span).color : '',
    wordClass: span?.className ?? '',
  }
}, word)

/** The tab strip's own background: the first non-transparent box from the tab list up. */
const strip = (page: Page) => page.evaluate(() => {
  let el = document.querySelector('[role="tablist"]') as HTMLElement | null
  while (el) {
    const bg = getComputedStyle(el).backgroundColor
    if (bg && bg !== 'rgba(0, 0, 0, 0)' && bg !== 'transparent') return bg
    el = el.parentElement
  }
  return ''
})

async function pick(page: Page, api: { post: (u: string, o: { data: unknown }) => Promise<{ ok: () => boolean; text: () => Promise<string> }> }, values: Record<string, string>) {
  const r = await api.post('/api/settings', { data: { values } })
  expect(r.ok(), await r.text()).toBeTruthy()
  // The operator comes back to the window: it reads the settings again.
  await page.evaluate(() => window.dispatchEvent(new Event('focus')))
}

test.describe('colour schemes', () => {
  test.afterEach(async ({ server }) => {
    await server.api.post('/api/settings', { data: { values: { 'terminal.scheme': 'sp-now', 'terminal.scheme_scope': 'terminal' } } })
  })

  test('a scheme recolours the live terminal, the whole window its chrome, and sp-now brings back the old colours', async ({ win, server }) => {
    test.skip(WINDOWS, 'printf with escapes is sh')
    const { page } = win
    await ready(page)
    await typeLine(page, "printf '\\033[31mschemered\\033[0m\\n'")
    await expectLine(page, 'schemered')

    const before = await colours(page, 'schemered')
    const stripBefore = await strip(page)
    expect(before.ground).toBe(rgb('#0E1013'))
    expect(before.word).toBe(rgb('#EF6B73'))
    expect(before.wordClass).toContain('xterm-fg-1')

    // Catppuccin Latte, the terminal only: xterm's ground and its red change, the strip does not.
    await pick(page, server.api, { 'terminal.scheme': 'catppuccin-latte', 'terminal.scheme_scope': 'terminal' })
    await expect.poll(async () => (await colours(page, 'schemered')).ground).toBe(rgb('#EFF1F5'))
    expect((await colours(page, 'schemered')).word).toBe(rgb('#D20F39'))
    await expect(page.locator('.aq[data-scheme="catppuccin-latte"]')).toHaveCount(1)
    expect(await strip(page)).toBe(stripBefore)

    // The whole window: the tab strip takes the scheme's panel colour.
    await pick(page, server.api, { 'terminal.scheme_scope': 'window' })
    await expect.poll(() => strip(page)).not.toBe(stripBefore)
    const latteStrip = await strip(page)
    await shot(page, 'latte-window')
    expect(latteStrip).toBe(await page.evaluate(() => getComputedStyle(document.querySelector('.aq')!).getPropertyValue('--r2-strip').trim())
      .then((hex) => rgb(hex)))

    // Dracula, from the window's own quick switch, one click.
    await page.getByRole('button', { name: /^(Colour scheme|Цветовая схема)$/ }).click()
    const dialog = page.getByRole('dialog', { name: /^(Colour scheme|Цветовая схема)$/ })
    await shot(page, 'picker-in-window')
    await dialog.locator('[data-scheme="dracula"]').click()
    await expect.poll(async () => (await colours(page, 'schemered')).ground).toBe(rgb('#282A36'))
    expect((await colours(page, 'schemered')).word).toBe(rgb('#FF5555'))
    await page.keyboard.press('Escape')
    await expect(dialog).toHaveCount(0)
    await shot(page, 'dracula-window')
    expect(await strip(page)).not.toBe(latteStrip)

    // Back to sp-now on the terminal only: the colours as they were.
    await pick(page, server.api, { 'terminal.scheme': 'sp-now', 'terminal.scheme_scope': 'terminal' })
    await expect.poll(async () => (await colours(page, 'schemered')).ground).toBe(before.ground)
    expect((await colours(page, 'schemered')).word).toBe(before.word)
    await expect.poll(() => strip(page)).toBe(stripBefore)
  })

  test('Settings › Terminal shows the twelve schemes; a pick there is saved', async ({ bare, server }) => {
    const { page } = bare
    await page.goto(`${server.url}/settings#terminal`)
    const grid = page.getByRole('radiogroup', { name: /^(Colour scheme|Цветовая схема)$/ })
    await expect(grid.getByRole('radio')).toHaveCount(12)
    await expect(grid.locator('[data-scheme="sp-now"]')).toHaveAttribute('aria-checked', 'true')
    await expect(grid.locator('[data-low]')).toHaveCount(1)
    await grid.locator('[data-scheme="sp-paper"]').scrollIntoViewIfNeeded()
    await shot(page, 'settings')
    await grid.locator('[data-scheme="sp-paper"]').click()
    await expect(grid.locator('[data-scheme="sp-paper"]')).toHaveAttribute('aria-checked', 'true')
    await expect.poll(async () => {
      const body = await (await server.api.get('/api/settings')).json() as { groups: Array<{ settings: Array<{ key: string; value: unknown }> }> }
      return body.groups.flatMap((g) => g.settings).find((x) => x.key === 'terminal.scheme')?.value
    }).toBe('sp-paper')
  })
})
