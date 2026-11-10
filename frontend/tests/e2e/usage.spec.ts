import fs from 'node:fs'
import path from 'node:path'
import { fileURLToPath } from 'node:url'
import { expect, test, type Locator } from '@playwright/test'

/**
 * The Usage page and the line under a turn, on the server's golden usage
 * data (testdata/usage/root), which playwright.config.ts copies beside the
 * demo projects with the usage clock fixed (SP_NOW). The numbers are the
 * strings the server's tests list for that data (expected/strings.json).
 * Without the golden data only the page's shape is checked.
 */

const here = path.dirname(fileURLToPath(import.meta.url))
const STRINGS = path.resolve(here, '../../../testdata/usage/expected/strings.json')
const golden = fs.existsSync(STRINGS)
  ? JSON.parse(fs.readFileSync(STRINGS, 'utf8')) as {
    today: { tiles: Record<string, string>; limits: Record<string, { five_hour: { pct: string } }> }
    lines: Record<string, Record<string, string>>
  }
  : null

/** The moment the golden data describes (playwright.config.ts USAGE_NOW). */
const NOW = '2026-11-01T14:48:00'

/** The text a reader sees: without the hidden description. */
const seen = (el: Locator) => el.evaluate((n) => {
  const c = n.cloneNode(true) as HTMLElement
  c.querySelectorAll('.sr-only').forEach((x) => x.remove())
  return c.textContent ?? ''
})

test.describe('usage', () => {
  test('the page opens with its limits, its range and its guide', async ({ page }) => {
    await page.goto('/usage')
    await expect(page.getByRole('heading', { name: 'Usage', level: 1 })).toBeVisible()
    await expect(page.getByRole('region', { name: 'Plan limits' })).toBeVisible()
    await expect(page.getByRole('radio', { name: 'Today' })).toBeVisible()
    await expect(page.getByTestId('crash-screen')).toHaveCount(0)
  })

  test('the golden numbers: limits, tiles, the Codex filter and the line under a turn', async ({ page }) => {
    expect(golden, 'testdata/usage is in the tree; a missing file fails').toBeTruthy()
    const g = golden!
    // The page's own clock at the server's fixed moment: a reset the server
    // still counts must not have passed on the page.
    await page.clock.setFixedTime(new Date(NOW))
    await page.goto('/usage')
    await expect(page.getByTestId('limits-claude-code').getByText(g.today.limits['claude-code']!.five_hour.pct, { exact: true })).toBeVisible()
    for (const [label, key] of [['new + output', 'new_output'], ['cache', 'cache'], ['cache share', 'share'], ['turns', 'turns']] as const) {
      // A tile: its label and its value, each a line of its own.
      await expect(page.locator(`xpath=//div[div[normalize-space()="${label}"] and div[normalize-space()="${g.today.tiles[key]}"]]`)).toBeVisible()
    }
    await page.getByRole('button', { name: 'Codex', exact: true }).click()
    await expect(page.getByTestId('usage-filter')).toContainText('Showing Codex')
    await expect(page.locator('table a[href^="/agent/"]')).toHaveCount(1)

    // The chat reader on the agent page: each drawn turn's line is the server's for that turn.
    await page.goto('/agent/cc-golden')
    await page.getByRole('tab', { name: /chats/ }).click()
    const first = page.getByTestId('usage-line').first()
    await expect(first).toBeVisible()
    const turn = await first.evaluate((n) => n.closest('article')?.getAttribute('aria-label') ?? '')
    const n = /^turn (\d+)$/.exec(turn)?.[1]
    expect(n, turn).toBeTruthy()
    expect(await seen(first)).toBe(g.lines['cc-golden']![n!])
  })
})
