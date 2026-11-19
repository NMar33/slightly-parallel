import type { Page } from '@playwright/test'
import { test, expect, expectClickTarget, fullSize, HIDDEN, LW, mainBounds, ptySize, ready, RW, termWidth } from './fixtures'

async function chooseMode(page: Page, mode: 'outward' | 'inward') {
  await page.getByRole('button', { name: 'Sidebar settings' }).click()
  await page.getByRole('menuitemradio', { name: `Open sidebars ${mode}` }).click()
  await expect(page.locator('[data-aqua-frame]')).toHaveAttribute('data-sidebar-mode', mode)
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
  const tty = await ptySize(page)

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
  expect(await ptySize(page)).toEqual(tty)

  await chooseMode(page, 'inward')
  await expect.poll(outerWidth).toBe(start)
  await expect.poll(async () => (await termWidth(page)).frame).toBe(start - LW - RW)
  await expect(left).toHaveAttribute('aria-pressed', 'true')
  await expect(right).toHaveAttribute('aria-pressed', 'true')
  await expect(input).toBeFocused()
  expect((await ptySize(page))[1]).toBeLessThan(tty[1])

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
      const buttons = sidebarControls(page)
      for (const button of buttons) await button.click({ trial: true })
      const controls = folded ? buttons : [...buttons, page.getByRole('button', { name: 'Sidebar settings' })]
      const centers = () => Promise.all(controls.map(center))
      const initial = await centers()
      const bounds = await mainBounds(app)
      for (const [index, on] of [[0, true], [1, true], [0, false], [1, false]] as const) {
        await expectClickTarget(buttons[index]!, initial[index]!)
        await page.mouse.click(initial[index]!.x, initial[index]!.y)
        await expect(buttons[index]!).toHaveAttribute('aria-pressed', String(on))
        expect(await centers()).toEqual(initial)
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
