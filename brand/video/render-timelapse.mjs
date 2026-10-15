// Render a Timelapse film from the running dev server to a VP8 .webm, frame by
// frame, with Playwright's bundled ffmpeg. Run from frontend/ (playwright is there):
//   node ../brand/video/render-timelapse.mjs "<studio url>" out/dir [seconds] [fps]
import { chromium } from 'playwright'
import { spawnSync } from 'node:child_process'
import { mkdirSync, readdirSync, writeFileSync, appendFileSync, unlinkSync, existsSync } from 'node:fs'
import { resolve, join } from 'node:path'
import { homedir } from 'node:os'

const [,, url, out, secondsArg, fpsArg] = process.argv
const seconds = Number(secondsArg || 24), fps = Number(fpsArg || 25)
const dir = resolve(out); mkdirSync(dir, { recursive: true })
const ffDir = readdirSync(join(homedir(), '.cache/ms-playwright')).find((d) => d.startsWith('ffmpeg'))
const ffmpeg = join(homedir(), '.cache/ms-playwright', ffDir, 'ffmpeg-linux')

const browser = await chromium.launch()
const page = await browser.newPage({ viewport: { width: 1500, height: 1000 }, deviceScaleFactor: 1.5 })
await page.goto(url)
await page.waitForSelector('input[type=range]', { timeout: 30000 })
await page.waitForTimeout(3000)
const canvas = await page.$('canvas')
const slider = await page.$('input[type=range]')
const max = Number(await slider.getAttribute('max')) || 1000
const box = await canvas.boundingBox()
const clip = { x: Math.round(box.x), y: Math.round(box.y), width: Math.round(box.width), height: Math.round(box.height) }
const n = Math.round(seconds * fps)
const all = join(dir, 'all.mjpeg'); if (existsSync(all)) unlinkSync(all); writeFileSync(all, '')
for (let i = 0; i < n; i++) {
  const v = (i / (n - 1)) * max
  await slider.evaluate((el, v) => {
    const set = Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value').set
    set.call(el, String(v)); el.dispatchEvent(new Event('input', { bubbles: true }))
  }, v)
  await page.waitForTimeout(40)
  let shot = null
  for (let tries = 0; tries < 3 && !shot; tries++) {
    try { shot = await page.screenshot({ type: 'jpeg', quality: 94, clip, timeout: 60000 }) }
    catch (e) { console.error(`frame ${i}: ${String(e.message).split('\n')[0]} (try ${tries + 1})`) }
  }
  if (!shot) { console.error(`frame ${i}: given up`); process.exit(1) }
  appendFileSync(all, shot)
  if (i % 50 === 0) console.log(`frame ${i}/${n}`)
  if (i === Math.round(n * 0.5)) await page.screenshot({ path: join(dir, 'poster.png'), clip, timeout: 120000 })
}
await browser.close()
const r = spawnSync(ffmpeg, ['-hide_banner', '-loglevel', 'error', '-y', '-f', 'image2pipe', '-framerate', String(fps), '-c:v', 'mjpeg', '-i', all,
  '-c:v', 'libvpx', '-b:v', '10M', '-deadline', 'good', '-cpu-used', '2', '-pix_fmt', 'yuv420p', join(dir, 'film.webm')], { stdio: 'inherit' })
unlinkSync(all)
console.log(r.status === 0 ? `${n} frames → ${join(dir, 'film.webm')}` : 'encode failed')
