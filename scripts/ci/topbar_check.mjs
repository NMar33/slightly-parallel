// CI: the monitor in the top bar, in a real browser, on the runner's system.
//
// Opens the running server's page (sp.py up), waits for the top bar's
// readings — processor and memory as percents, the ping in milliseconds —
// and saves a picture of the bar to .sp/ci/topbar.png for the run's
// artifacts. Run from the repository folder: node scripts/ci/topbar_check.mjs
import { createRequire } from 'node:module'
import { mkdirSync } from 'node:fs'
import path from 'node:path'

const require = createRequire(path.resolve('frontend/package.json'))
const { chromium } = require('playwright')

const TOPBAR_TEXT_TIMEOUT_MS = 5000
const TOPBAR_POLL_INTERVAL_MS = 1000
const TOPBAR_POLL_ATTEMPTS = 90

const base = `http://127.0.0.1:${process.env.SP_PORT || 8123}`
const out = path.resolve('.sp/ci')
mkdirSync(out, { recursive: true })

const browser = await chromium.launch()
const page = await browser.newPage({ viewport: { width: 1440, height: 400 } })
await page.goto(base + '/')
const bar = page.locator('header a[href="/monitor"]').first()
const wanted = [/CPU\s*\d+%/, /MEM\s*\d+%/, /PING\s*\d+\s*ms/]
let text = ''
for (let i = 0; i < TOPBAR_POLL_ATTEMPTS; i++) {
  text = ((await bar.textContent({ timeout: TOPBAR_TEXT_TIMEOUT_MS }).catch(() => '')) || '').replace(/\s+/g, ' ')
  if (wanted.every((re) => re.test(text))) break
  await page.waitForTimeout(TOPBAR_POLL_INTERVAL_MS)
}
await page.locator('header').first().screenshot({ path: path.join(out, 'topbar.png') })
await browser.close()
console.log('top bar:', text)
const missing = wanted.filter((re) => !re.test(text)).map(String)
if (missing.length) {
  console.error('the top bar did not show:', missing.join(', '))
  process.exit(1)
}
console.log('the top bar shows the readings; picture in .sp/ci/topbar.png')
