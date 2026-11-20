import { execFile } from 'node:child_process'
import fs from 'node:fs'
import path from 'node:path'
import { promisify } from 'node:util'
import type { Locator } from '@playwright/test'
import { expect, LW, ROOT, RW, mainBounds, printFile, ready, test, typeLine } from './fixtures'
import { offsetNow } from './scrollProbe'

const run = promisify(execFile)
const sendX11 = `
import ctypes as c
import sys
import time
x11, xtst = c.CDLL("libX11.so.6"), c.CDLL("libXtst.so.6")
x11.XOpenDisplay.argtypes = [c.c_char_p]
x11.XOpenDisplay.restype = c.c_void_p
x11.XSync.argtypes = [c.c_void_p, c.c_int]
x11.XCloseDisplay.argtypes = [c.c_void_p]
xtst.XTestFakeMotionEvent.argtypes = [c.c_void_p, c.c_int, c.c_int, c.c_int, c.c_ulong]
xtst.XTestFakeButtonEvent.argtypes = [c.c_void_p, c.c_uint, c.c_int, c.c_ulong]
display = x11.XOpenDisplay(sys.argv[1].encode())
if not display:
    raise RuntimeError("Could not open the isolated X11 display")
try:
    x, y, button, repetitions = map(int, sys.argv[2:])
    xtst.XTestFakeMotionEvent(display, -1, x, y, 0)
    x11.XSync(display, 0)
    time.sleep(0.08)
    for _ in range(repetitions):
        xtst.XTestFakeButtonEvent(display, button, 1, 0)
        xtst.XTestFakeButtonEvent(display, button, 0, 0)
        x11.XSync(display, 0)
        time.sleep(0.02)
finally:
    x11.XCloseDisplay(display)
`

test('native X11 clicks and wheel reach the terminal in the yellow zone', async ({ win }) => {
  const display = process.env.SP_E2E_X11_DISPLAY
  test.skip(!display, 'requires an explicitly isolated Xvfb display')
  const server = Number(process.env.SP_E2E_X11_PID)
  expect(display).toMatch(/^:\d+$/)
  expect(process.env.DISPLAY).toBe(display)
  expect(server).toBeGreaterThan(0)
  expect(path.basename(fs.readlinkSync(`/proc/${server}/exe`))).toBe('Xvfb')
  const { page, app } = win
  await ready(page)
  await page.addInitScript(() => {
    if (sessionStorage.getItem('sp-e2e-seeded')) return
    sessionStorage.setItem('sp-e2e-seeded', '1')
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
  const screenPoint = async (locator: Locator) => {
    const box = (await locator.boundingBox())!
    const origin = await app.evaluate(({ BrowserWindow }) => BrowserWindow.getAllWindows()[0].getContentBounds())
    return { x: Math.round(origin.x + box.x + box.width / 2), y: Math.round(origin.y + box.y + box.height / 2) }
  }
  const sendAt = ({ x, y }: Awaited<ReturnType<typeof screenPoint>>, button: number, steps = 1) =>
    run('/usr/bin/python3', ['-c', sendX11, display!, String(x), String(y), String(button), String(steps)])
  const send = async (locator: Locator, button: number, steps = 1) => sendAt(await screenPoint(locator), button, steps)
  const label = page.locator('[data-health-label="yellow"]')
  const today = page.getByRole('dialog', { name: 'Time today' })
  await expect(label).toBeVisible()
  await send(label, 1)
  await expect(today).toBeVisible()
  await send(today.getByRole('button', { name: 'Close' }), 1)
  await expect(today).toHaveCount(0)
  await send(page.getByRole('button', { name: 'Window settings' }), 1)
  const choice = page.getByRole('radio', { name: 'Open sidebars inward' })
  await expect(choice).toBeVisible()
  await send(choice, 1)
  await expect(page.locator('[data-aqua-frame]')).toHaveAttribute('data-sidebar-mode', 'inward')
  await send(page.getByRole('button', { name: 'Close window settings' }), 1)
  await expect(page.getByRole('complementary', { name: 'Window settings' })).toHaveCount(0)

  const file = path.join(ROOT, 'work', 'x11-pointer-history.txt')
  fs.writeFileSync(file, Array.from({ length: 400 }, (_, i) => `L${String(i + 1).padStart(5, '0')} history`).join('\n') + '\n')
  await typeLine(page, printFile(file))
  const terminal = page.locator('.aqua-screen')
  await expect(terminal.locator('.xterm-rows')).toContainText('L00400')
  const end = (await offsetNow(page))!
  await send(terminal, 4, 3)
  await expect.poll(async () => (await offsetNow(page)) ?? end).toBeLessThan(end - 12)
  const earlier = (await offsetNow(page))!
  await send(terminal, 5, 6)
  await expect.poll(async () => (await offsetNow(page)) ?? earlier).toBeGreaterThan(earlier + 12)

  const controls = ['Left sidebar', 'Right sidebar'].map((name) => page.getByRole('button', { name, exact: true }))
  const centers = () => Promise.all(controls.map(screenPoint))
  const toggleAtFixedPoints = async (mode: string, outward = false) => {
    const points = await centers()
    let width = (await mainBounds(app)).width
    for (const [i, on] of [[0, true], [1, true], [0, false], [1, false]] as const) {
      await sendAt(points[i]!, 1)
      await expect(controls[i]!).toHaveAttribute('aria-pressed', String(on))
      if (outward) width += (on ? 1 : -1) * (i === 0 ? LW : RW)
      await expect.poll(async () => (await mainBounds(app)).width).toBe(width)
      await expect.poll(centers, { message: `${mode} controls stay at the same screen points` }).toEqual(points)
    }
  }
  await toggleAtFixedPoints('Inward')

  await send(page.getByRole('button', { name: 'Window settings' }), 1)
  await send(page.getByRole('radio', { name: 'Open sidebars outward' }), 1)
  await expect(page.locator('[data-aqua-frame]')).toHaveAttribute('data-sidebar-mode', 'outward')
  await send(page.getByRole('button', { name: 'Close window settings' }), 1)
  await expect(page.getByRole('complementary', { name: 'Window settings' })).toHaveCount(0)
  const bounds = await mainBounds(app)
  await toggleAtFixedPoints('Outward', true)
  await expect.poll(() => mainBounds(app)).toEqual(bounds)

  await send(page.getByRole('button', { name: 'Window settings' }), 1)
  await send(page.getByRole('radio', { name: 'Open sidebars inward' }), 1)
  await expect(page.locator('[data-aqua-frame]')).toHaveAttribute('data-sidebar-mode', 'inward')
  await send(page.getByRole('button', { name: 'Close window settings' }), 1)
  await expect(page.getByRole('complementary', { name: 'Window settings' })).toHaveCount(0)
  await app.evaluate(({ BrowserWindow }) => { BrowserWindow.getAllWindows()[0].setSize(420, 320) })
  await expect.poll(() => page.evaluate(() => window.innerWidth)).toBe(420)
  await send(page.getByRole('button', { name: /Fold the title row/ }), 1)
  await expect(page.locator('[data-aqua-frame][data-folded]')).toHaveCount(1)
  for (const button of controls) await button.click({ trial: true })
  await toggleAtFixedPoints('Narrow folded inward')
})
