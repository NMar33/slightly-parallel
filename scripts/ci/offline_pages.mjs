// CI: the pages with the network off (scripts/ci/offline_check.py runs this
// while the firewall blocks). Each page opens within its time-out, no page
// asks for anything from another host (a font, a script, an image: offline
// it would hang or fail), and Monitor shows "No connection".
// Run from the repository folder: node scripts/ci/offline_pages.mjs
import { serverUrl } from './server_address.mjs'
import { createRequire } from 'node:module'
import path from 'node:path'

const require = createRequire(path.resolve('frontend/package.json'))
const { chromium } = require('playwright')

const OFFLINE_PAGE_TIMEOUT_MS = 20000
const CONNECTION_STATUS_TIMEOUT_MS = 30000

const base = serverUrl()
const routes = ['/', '/kanban', '/usage', '/settings', '/monitor']
const outside = []
const failed = []

const browser = await chromium.launch()
const page = await browser.newPage()
page.on('request', (req) => {
  const host = new URL(req.url()).hostname
  if (!['127.0.0.1', 'localhost'].includes(host) && !req.url().startsWith('data:')) outside.push(req.url())
})
for (const route of routes) {
  const t = Date.now()
  try {
    await page.goto(base + route, { waitUntil: 'load', timeout: OFFLINE_PAGE_TIMEOUT_MS })
    await page.locator('#root > *').first().waitFor({ timeout: OFFLINE_PAGE_TIMEOUT_MS })
    console.log(`  ok   ${route} opens (${((Date.now() - t) / 1000).toFixed(1)} s)`)
  } catch (err) {
    console.log(`  FAIL ${route} did not open: ${String(err).split('\n')[0]}`)
    failed.push(route)
  }
}
// The last page is Monitor: its health word reads the open events.
try {
  await page.getByText('No connection').first().waitFor({ timeout: CONNECTION_STATUS_TIMEOUT_MS })
  console.log('  ok   Monitor shows "No connection"')
} catch {
  console.log('  FAIL Monitor does not show "No connection"')
  failed.push('monitor')
}
await browser.close()
if (outside.length) {
  console.log(`  FAIL the pages asked another host: ${[...new Set(outside)].slice(0, 10).join(', ')}`)
  failed.push('outside')
} else {
  console.log('  ok   no page asked another host')
}
process.exit(failed.length ? 1 : 0)
