import type { Page } from '@playwright/test'
import { test, expect, expectClickTarget, fullSize, HIDDEN, LW, mainBounds, ptySize, ready, RW, termWidth } from './fixtures'

async function chooseMode(page: Page, mode: 'outward' | 'inward') {
  await page.getByRole('button', { name: 'Window settings' }).click()
  await page.getByRole('radio', { name: `Open sidebars ${mode}` }).click()
  await expect(page.locator('[data-aqua-frame]')).toHaveAttribute('data-sidebar-mode', mode)
  await page.getByRole('button', { name: 'Close window settings' }).click()
  await expect(page.getByRole('complementary', { name: 'Window settings' })).toHaveCount(0)
}

const sidebarControls = (page: Page) => (['left', 'right'] as const).map((side) => page.locator(`[data-toggle="${side}"]`))

async function center(button: ReturnType<typeof sidebarControls>[number]) {
  const box = await button.boundingBox()
  if (!box) throw new Error('Sidebar control is not visible')
  return { x: box.x + box.width / 2, y: box.y + box.height / 2 }
}

test('switching the sidebar mode with both panels open preserves the window and terminal state', async ({ win }) => {
  const { app, page } = win
  await ready(page)
  await fullSize(app, page)

  const outerWidth = async () => (await mainBounds(app)).width
  const input = page.getByRole('textbox', { name: 'Terminal input' })
  const left = page.getByRole('button', { name: 'Left sidebar', exact: true })
  const right = page.getByRole('button', { name: 'Right sidebar', exact: true })
  const start = await outerWidth()
  const screen = page.locator('.aqua-screen [data-rows][data-cols]')
  const tty = await screen.evaluate((element) => [Number(element.dataset.rows), Number(element.dataset.cols)])
  // The renderer can finish fitting before the resize reaches the shell.
  await expect.poll(() => ptySize(page), { message: 'the PTY has reached the starting window size' }).toEqual(tty)

  const termRelativeCenters = async () => {
    const terminal = (await page.locator('.aqua-screen').boundingBox())!
    return Promise.all(sidebarControls(page).map(async (control) => {
      const point = await center(control)
      return { x: Math.round(point.x - terminal.x), y: point.y }
    }))
  }
  const outwardControls = await termRelativeCenters()
  await left.click()
  await expect.poll(outerWidth).toBe(start + LW)
  await expect.poll(termRelativeCenters).toEqual(outwardControls)
  await right.click()
  await expect.poll(outerWidth).toBe(start + LW + RW)
  await expect.poll(termRelativeCenters).toEqual(outwardControls)
  await expect.poll(async () => (await termWidth(page)).frame).toBe(start)
  await expect.poll(() => ptySize(page)).toEqual(tty)

  await chooseMode(page, 'inward')
  await expect.poll(outerWidth).toBe(start)
  await expect.poll(async () => (await termWidth(page)).frame).toBe(start - LW - RW)
  await expect(left).toHaveAttribute('aria-pressed', 'true')
  await expect(right).toHaveAttribute('aria-pressed', 'true')
  await expect(input).toBeFocused()
  await expect.poll(async () => (await ptySize(page))[1]).toBeLessThan(tty[1]!)

  await chooseMode(page, 'outward')
  await expect.poll(outerWidth).toBe(start + LW + RW)
  await expect.poll(async () => (await termWidth(page)).frame).toBe(start)
  await chooseMode(page, 'inward')
  await left.click()
  await right.click()
  await expect.poll(outerWidth).toBe(start)

  await page.reload()
  await ready(page)
  await expect(page.locator('[data-aqua-frame]')).toHaveAttribute('data-sidebar-mode', 'inward')
  await left.click()
  await right.click()
  await expect.poll(outerWidth).toBe(start)
  await expect.poll(async () => (await termWidth(page)).frame).toBe(start - LW - RW)
  await chooseMode(page, 'outward')
})

test('inward sidebar controls can be clicked again at the same points in wide, narrow and folded windows', async ({ win }) => {
  const { app, page } = win
  await ready(page)
  await fullSize(app, page)
  await chooseMode(page, 'inward')

  for (const width of [1000, 420]) {
    await app.evaluate(({ BrowserWindow }, size) => { BrowserWindow.getAllWindows()[0].setSize(size, 400) }, width)
    await expect.poll(() => page.evaluate(() => window.innerWidth)).toBe(width)
    // The renderer can report the requested width before Mutter finishes configuring the height.
    await expect.poll(async () => {
      const before = await mainBounds(app)
      await page.evaluate(() => new Promise<void>((resolve) => requestAnimationFrame(() => requestAnimationFrame(() => resolve()))))
      const after = await mainBounds(app)
      return before.width === after.width && before.height === after.height
    }).toBe(true)
    for (const folded of [false, true]) {
      if (folded) await page.keyboard.press('Alt+KeyT')
      await expect(page.locator('[data-aqua-frame][data-folded]')).toHaveCount(folded ? 1 : 0)
      // The folded buttons are below the animated title row. Measure after
      // the row reaches its final height, before changing either sidebar.
      await expect(page.locator('[data-window-title]')).toHaveCSS('height', folded ? '12px' : '34px')
      const buttons = sidebarControls(page)
      for (const button of buttons) await button.click({ trial: true })
      const controls = folded ? buttons : [...buttons, page.getByRole('button', { name: 'Window settings' })]
      const centers = () => Promise.all(controls.map(center))
      const initial = await centers()
      const bounds = await mainBounds(app)
      for (const [index, on] of [[0, true], [1, true], [0, false], [1, false]] as const) {
        await expectClickTarget(buttons[index]!, initial[index]!)
        await page.mouse.click(initial[index]!.x, initial[index]!.y)
        await expect(buttons[index]!).toHaveAttribute('aria-pressed', String(on))
        const after = await centers()
        for (const [control, point] of initial.entries()) {
          // macOS and Windows Chromium can round off fractions of a CSS pixel.
          expect(Math.abs(after[control]!.x - point.x)).toBeLessThanOrEqual(0.125)
          expect(Math.abs(after[control]!.y - point.y)).toBeLessThanOrEqual(0.125)
        }
        const frame = await mainBounds(app)
        expect({ x: frame.x, y: frame.y, width: frame.width }).toEqual({ x: bounds.x, y: bounds.y, width: bounds.width })
        // Mutter can round the requested height by one DIP after setSize.
        expect(Math.abs(frame.height - bounds.height)).toBeLessThanOrEqual(HIDDEN ? 1 : 0)
        if (folded && on) {
          const panel = page.locator(`aside[aria-label="${index === 0 ? 'Left' : 'Right'} sidebar"] > :first-child`)
          const control = (await buttons[index]!.boundingBox())!
          expect((await panel.boundingBox())!.y).toBeGreaterThan(control.y + control.height)
        }
        if (index === 1 && on) await expect.poll(async () => (await termWidth(page)).frame).toBe(width === 420 ? 210 : width - LW - RW)
      }
      if (folded) await page.getByRole('button', { name: /Unfold the title row/ }).click()
    }
  }
  await chooseMode(page, 'outward')
})

test('focusing an overflowing control does not scroll the window header sideways', async ({ win }) => {
  const { app, page } = win
  await ready(page)
  await app.evaluate(({ BrowserWindow }) => { BrowserWindow.getAllWindows()[0].setSize(420, 400) })
  await expect.poll(() => page.evaluate(() => innerWidth)).toBe(420)
  await chooseMode(page, 'inward')
  const [left, right] = sidebarControls(page)
  await left!.click()
  await expect(left!).toHaveAttribute('aria-pressed', 'true')
  const initial = await center(right!)
  // Force the overflow that a narrow native window can encounter during layout.
  await left!.evaluate((element) => { element.style.left = 'calc(100% + 24px)' })
  await left!.focus()
  await expect(left!).toBeFocused()
  expect(await center(right!)).toEqual(initial)
})

test('window settings replace the left sidebar and resize the two rows independently', async ({ win, server }) => {
  const { app, page } = win
  await ready(page)
  await fullSize(app, page)
  await chooseMode(page, 'inward')
  await page.getByRole('button', { name: 'Left sidebar', exact: true }).click()
  const left = page.getByRole('navigation', { name: 'Workspaces' })
  await expect(left).toBeVisible()
  const bounds = await mainBounds(app)

  await page.getByRole('button', { name: 'Window settings' }).click()
  const settings = page.getByRole('complementary', { name: 'Window settings' })
  await expect(settings).toBeVisible()
  await expect(left).toBeHidden()
  await settings.getByLabel('Title row height').selectOption('2')
  await expect(page.locator('[data-window-title]')).toHaveCSS('height', '17px')
  await expect(page.locator('[data-window-tabs]')).toHaveCSS('height', '32px')
  await settings.getByLabel('Tab row height').selectOption('1.5')
  await expect(page.locator('[data-window-tabs]')).toHaveCSS('height', '21px')
  await settings.getByRole('button', { name: 'Close window settings' }).click()
  await expect(left).toBeVisible()
  await expect.poll(() => mainBounds(app)).toEqual(bounds)

  const stale = await server.api.post('/api/prefs', { data: {
    values: { 'sp-aqua-window-layout': JSON.stringify({ titleScale: 1, tabsScale: 1 }) },
  } })
  expect(stale.ok(), await stale.text()).toBe(true)
  await page.reload()
  await ready(page)
  await expect(page.locator('[data-window-title]')).toHaveCSS('height', '17px')
  await expect(page.locator('[data-window-tabs]')).toHaveCSS('height', '21px')
  await app.evaluate(({ BrowserWindow }) => { BrowserWindow.getAllWindows()[0].setSize(420, 400) })
  await expect.poll(() => page.evaluate(() => innerWidth)).toBe(420)
  for (const name of ['Left sidebar', 'Window settings', 'Fold the title row (alt+T)', 'Dashboard', 'Minimise', 'Enter fullscreen', 'Close the window', 'Right sidebar']) {
    const button = page.getByRole('button', { name, exact: true })
    await expectClickTarget(button, await center(button))
  }
})

test('the title row can fold immediately after the native window narrows', async ({ win }) => {
  const { app, page } = win
  await page.addInitScript(() => {
    window.addEventListener('resize', (event) => {
      if (document.documentElement.hasAttribute('data-e2e-defer-resize')) event.stopImmediatePropagation()
    }, true)
  })
  await page.reload()
  await ready(page)
  await fullSize(app, page)
  await chooseMode(page, 'inward')
  const frame = page.locator('[data-aqua-frame]')
  const wide = await page.evaluate(() => innerWidth)
  expect(wide).toBeGreaterThan(420)
  await expect(frame).toHaveCSS('width', `${wide}px`)

  // Reproduce the interval between the compositor resize and the renderer
  // receiving it. The next pointer click can land during that interval.
  await page.evaluate(() => document.documentElement.setAttribute('data-e2e-defer-resize', ''))
  try {
    await app.evaluate(({ BrowserWindow }) => { BrowserWindow.getAllWindows()[0].setSize(420, 320) })
    await expect.poll(() => page.evaluate(() => innerWidth)).toBe(420)
    const fold = page.getByRole('button', { name: /Fold the title row/ })
    const point = await center(fold)
    await expectClickTarget(fold, point)
    await page.mouse.click(point.x, point.y)
    await expect(frame).toHaveAttribute('data-folded', 'true')
  } finally {
    await page.evaluate(() => {
      document.documentElement.removeAttribute('data-e2e-defer-resize')
      window.dispatchEvent(new Event('resize'))
    })
  }
})
