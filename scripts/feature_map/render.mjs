// Feature map renderer: one PNG per `.sheet` at 2x.
// build.py copies this file into frontend/ (where Playwright is installed),
// runs it and deletes it. Args: "<html>::<out prefix>" ...
// Prints one JSON line: [{file, width, height}] in css px.
import { chromium } from 'playwright'
import { pathToFileURL } from 'node:url'

const browser = await chromium.launch()
const shots = []
try {
  const page = await browser.newPage({ viewport: { width: 1560, height: 1200 }, deviceScaleFactor: 2 })
  for (const arg of process.argv.slice(2)) {
    const [html, prefix] = arg.split('::')
    await page.goto(pathToFileURL(html).href, { waitUntil: 'networkidle', timeout: 60000 })
    await page.evaluate(() => document.fonts.ready)
    const w = await page.evaluate(() => document.body.scrollWidth)
    await page.setViewportSize({ width: Math.max(1560, w), height: 1200 })
    await page.waitForFunction(() => window.__drawn !== false, null, { timeout: 30000 })
    const ids = await page.$$eval('section.sheet', (els) => els.map((el) => el.id))
    for (const id of ids) {
      const el = await page.$(`#${id}`)
      const box = await el.boundingBox()
      const file = `${prefix}-${id}.png`
      await el.screenshot({ path: file })
      shots.push({ file, width: Math.round(box.width), height: Math.round(box.height) })
    }
  }
} finally {
  await browser.close()
}
console.log(JSON.stringify(shots))
