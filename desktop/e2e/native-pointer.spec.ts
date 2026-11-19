import { execFile } from 'node:child_process'
import fs from 'node:fs'
import path from 'node:path'
import { promisify } from 'node:util'
import type { Locator } from '@playwright/test'
import { expect, HIDDEN, printFile, ready, ROOT, test, typeLine } from './fixtures'
import { descendants } from './global-setup'
import { offsetNow } from './scrollProbe'

const run = promisify(execFile)
const enabled = process.env.SP_E2E_NATIVE_POINTER === '1'

/** Use the hidden monitor's bus, never the bus of the operator's desktop. */
function isolatedBus(): string {
  const runner = Number(process.env.SP_E2E_DISPLAY_PID)
  if (!runner || !HIDDEN.startsWith('sp-e2e-')) throw new Error('Native pointer tests need the isolated GNOME display.')
  const compositor = descendants(runner).find((pid) => {
    try {
      const args = fs.readFileSync(`/proc/${pid}/cmdline`, 'utf8').split('\0')
      return path.basename(args[0] ?? '') === 'gnome-shell' && args.includes(`--wayland-display=${HIDDEN}`)
    } catch { return false }
  })
  const prefix = 'DBUS_SESSION_BUS_ADDRESS='
  const bus = compositor && fs.readFileSync(`/proc/${compositor}/environ`, 'utf8').split('\0')
    .find((env) => env.startsWith(prefix))?.slice(prefix.length)
  if (!bus || bus === process.env.DBUS_SESSION_BUS_ADDRESS) throw new Error('Could not identify the isolated GNOME bus.')
  return bus
}

test('the yellow timer keeps compositor clicks and short bidirectional scroll gestures usable', async ({ win }) => {
  test.skip(!enabled, 'SP_E2E_NATIVE_POINTER=1 opts in on an isolated GNOME compositor with python3-gi')
  const { app, page } = win
  await ready(page)
  const bus = isolatedBus()
  const pointer = async (x: number, y: number, action: 'activate' | 'click' | 'scroll', deltas: number[] = []) => {
    await run('/usr/bin/python3', [path.join(__dirname, 'bin', 'wayland-pointer.py'), x, y, action, ...deltas].map(String),
      { env: { ...process.env, DBUS_SESSION_BUS_ADDRESS: bus } })
  }
  const center = await app.evaluate(({ screen }) => {
    const { width, height } = screen.getPrimaryDisplay().bounds
    return { x: Math.round(width / 2), y: Math.round(height / 2) }
  })
  await page.evaluate(() => {
    document.addEventListener('pointerdown', (event) => {
      if (event.isTrusted) document.body.dataset.nativeCalibration = JSON.stringify({ x: event.clientX, y: event.clientY })
    }, true)
  })
  const body = page.locator('body')
  const calibrate = async (x: number, y: number, action: 'activate' | 'click') => {
    await body.evaluate((el) => el.removeAttribute('data-native-calibration'))
    await pointer(x, y, action)
    await expect(body, 'native click reaches the green window').toHaveAttribute('data-native-calibration', /"x":\d+/)
    return JSON.parse((await body.getAttribute('data-native-calibration'))!) as { x: number; y: number }
  }
  // Wayland hides the window origin. Two real points also measure the ratio
  // of compositor to page coordinates on a fractional-scale display.
  const local = await calibrate(center.x, center.y, 'activate')
  const step = 60
  const second = await calibrate(center.x + step, center.y + step, 'click')
  const scale = { x: (second.x - local.x) / step, y: (second.y - local.y) / step }
  expect(scale.x).toBeGreaterThan(0)
  expect(scale.y).toBeGreaterThan(0)

  await page.addInitScript(() => {
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
  await page.evaluate(() => {
    document.addEventListener('wheel', (event) => {
      if (event.isTrusted && event.deltaY)
        document.body.dataset.nativeWheel = event.deltaY < 0 ? 'up' : 'down'
    }, true)
  })
  const screenPoint = async (locator: Locator) => {
    const box = (await locator.boundingBox())!
    return {
      x: center.x + (box.x + box.width / 2 - local.x) / scale.x,
      y: center.y + (box.y + box.height / 2 - local.y) / scale.y,
    }
  }
  const at = async (locator: Locator, action: 'click' | 'scroll', deltas?: number[]) => {
    const { x, y } = await screenPoint(locator)
    await pointer(x, y, action, deltas)
  }
  const shell = page.locator('.aqua-screen')
  const label = page.locator('[data-health-label="yellow"]')
  const today = page.getByRole('dialog', { name: 'Time today' })
  await expect(label).toBeVisible()
  await at(label, 'click')
  await expect(today).toBeVisible()
  await at(today.getByRole('button', { name: 'Close' }), 'click')
  await expect(today).toHaveCount(0)

  await at(page.getByRole('button', { name: 'Sidebar settings' }), 'click')
  const menu = page.getByRole('menu', { name: 'Sidebar settings' })
  await expect(menu).toBeVisible()
  await at(menu.getByRole('menuitemradio', { name: 'Open sidebars inward' }), 'click')
  await expect(page.locator('[data-aqua-frame]')).toHaveAttribute('data-sidebar-mode', 'inward')

  const controls = ['Left sidebar', 'Right sidebar'].map((name) => page.getByRole('button', { name, exact: true }))
  const centers = () => Promise.all(controls.map(screenPoint))
  const points = await centers()
  for (const [i, on] of [[0, true], [1, true], [0, false], [1, false]] as const) {
    await pointer(points[i]!.x, points[i]!.y, 'click')
    await expect(controls[i]!).toHaveAttribute('aria-pressed', String(on))
    expect(await centers()).toEqual(points)
  }

  const file = path.join(ROOT, 'work', 'native-pointer-history.txt')
  fs.writeFileSync(file, Array.from({ length: 400 }, (_, index) => `L${String(index + 1).padStart(5, '0')} history`).join('\n') + '\n')
  await typeLine(page, printFile(file))
  await expect(shell.locator('.xterm-rows')).toContainText('L00400')
  const end = (await offsetNow(page))!
  await at(shell, 'scroll', Array(36).fill(-3))
  await expect(body).toHaveAttribute('data-native-wheel', 'up')
  await expect.poll(async () => (await offsetNow(page)) ?? end).toBeLessThan(end - 12)
  const earlier = (await offsetNow(page))!
  await at(shell, 'scroll', Array(20).fill(3))
  await expect(body).toHaveAttribute('data-native-wheel', 'down')
  await expect.poll(async () => (await offsetNow(page)) ?? earlier).toBeGreaterThan(earlier + 12)
})
