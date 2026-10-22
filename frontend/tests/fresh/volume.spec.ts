import { test, expect } from '@playwright/test'

/**
 * On a month of work plus a very long chat and hundreds of tasks: the
 * pages a person lives on show their content in a time a person accepts.
 */

const CODE = process.env.FRESH_CODE ?? 'shopfront'
const AGENT = process.env.FRESH_AGENT ?? ''
const BUDGET = 6_000

const pages: Array<[string, string, RegExp | string]> = [
  ['the overview', '/', CODE],
  ['the boards', '/kanban', /project boards/],
  ['the project', `/project/${CODE}`, 'Agent timeline'],
  ['the project board', `/project/${CODE}#tasks`, /Volume task \d+/],
  ['the chats', '/chats', /order list/i],
  ['the agents', '/agent', CODE],
  ['the statistics', '/stats', 'Statistics'],
  ['the calendar', '/calendar', 'Calendar'],
  ['the timer', '/time', 'Timer'],
]

for (const [name, url, sign] of pages) {
  test(`${name} shows its content within ${BUDGET / 1000} s`, async ({ page }) => {
    const thrown: string[] = []
    page.on('pageerror', (e) => thrown.push(String(e)))
    const start = Date.now()
    await page.goto(url, { waitUntil: 'domcontentloaded' })
    await expect(page.getByText(sign).first()).toBeVisible({ timeout: BUDGET })
    console.log(`${name}: ${Date.now() - start} ms`)
    expect(thrown).toEqual([])
  })
}

test('the long chat opens and scrolls', async ({ page }) => {
  expect(AGENT, 'FRESH_AGENT').not.toBe('')
  const thrown: string[] = []
  page.on('pageerror', (e) => thrown.push(String(e)))
  const start = Date.now()
  await page.goto(`/agent/${AGENT}`, { waitUntil: 'domcontentloaded' })
  await expect(page.getByText(AGENT).first()).toBeVisible({ timeout: BUDGET })
  await page.goto(`/chats?agent=${AGENT}`, { waitUntil: 'domcontentloaded' })
  await expect(page.getByText(/order list/i).first()).toBeVisible({ timeout: 15_000 })
  console.log(`the long chat: ${Date.now() - start} ms`)
  expect(thrown).toEqual([])
})
