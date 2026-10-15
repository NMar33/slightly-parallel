import fs from 'node:fs'
import path from 'node:path'
import { test, expect } from '@playwright/test'

/**
 * Pictures of the pages at one moment of the fresh-user test, saved for a
 * person to look at. A page that throws fails the step; what it looks like
 * is yours to judge.
 */

const OUT = process.env.FRESH_SHOTS ?? ''
const MOMENT = process.env.FRESH_MOMENT ?? 'now'
const ROUTES = (process.env.FRESH_ROUTES ?? '/').split('\n').filter(Boolean)

test(`pictures: ${MOMENT}`, async ({ page }) => {
  test.setTimeout(30_000 + ROUTES.length * 15_000)
  expect(OUT, 'FRESH_SHOTS').not.toBe('')
  fs.mkdirSync(OUT, { recursive: true })
  await page.setViewportSize({ width: 1440, height: 1000 })
  const thrown: string[] = []
  page.on('pageerror', (e) => thrown.push(`${page.url()}: ${e}`))
  for (const [i, route] of ROUTES.entries()) {
    await page.goto(route, { waitUntil: 'domcontentloaded' })
    await page.waitForLoadState('networkidle').catch(() => {})
    await page.waitForTimeout(700)
    const name = route.replace(/^\//, '').replace(/[^a-z0-9]+/gi, '-').replace(/-$/, '') || 'overview'
    await page.screenshot({ path: path.join(OUT, `${MOMENT}-${String(i + 1).padStart(2, '0')}-${name}.png`) })
  }
  expect(thrown).toEqual([])
})
