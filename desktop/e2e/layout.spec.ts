import type { Page } from '@playwright/test'
import { test, expect, LW, RW, mainBounds, ptySize, ready, termWidth, uncovered } from './fixtures'

/**
 * The window's layout: the sidebars grow the window and leave the terminal
 * alone, the title row folds, the workspaces button goes round.
 */

const toggle = (side: 'left' | 'right') => `[data-toggle="${side}"]`
const innerW = (page: Page) => page.evaluate(() => window.innerWidth)

test.describe('sidebars', () => {
  for (const how of ['buttons', 'keys'] as const) {
    test(`sidebars by ${how}: the window grows by the panel and back; the terminal keeps its width and columns`, async ({ win }) => {
      const { app, page } = win
      await ready(page)
      const w0 = (await mainBounds(app)).width
      const t0 = await termWidth(page)
      const pty0 = await ptySize(page)
      const press = async (side: 'left' | 'right') => {
        if (how === 'buttons') await page.locator(toggle(side)).click()
        else await page.keyboard.press(side === 'left' ? 'Alt+BracketLeft' : 'Alt+BracketRight')
      }
      const check = async (grownBy: number, open: { left: boolean; right: boolean }) => {
        await expect.poll(async () => (await mainBounds(app)).width, { message: 'the window width' }).toBe(w0 + grownBy)
        await expect.poll(() => innerW(page)).toBe(w0 + grownBy)
        await expect(page.getByRole('complementary', { name: 'Left sidebar' })).toHaveCount(open.left ? 1 : 0)
        await expect(page.getByRole('complementary', { name: 'Right sidebar' })).toHaveCount(open.right ? 1 : 0)
        await expect(page.locator(toggle('left'))).toHaveAttribute('aria-pressed', String(open.left))
        await expect(page.locator(toggle('right'))).toHaveAttribute('aria-pressed', String(open.right))
        await expect.poll(() => termWidth(page), { message: 'the terminal width' }).toEqual(t0)
        expect(await uncovered(page, toggle('left')), 'the left button is covered').toBe(true)
        expect(await uncovered(page, toggle('right')), 'the right button is covered').toBe(true)
      }
      await press('left')
      await check(LW, { left: true, right: false })
      await press('right')
      await check(LW + RW, { left: true, right: true })
      // The shell's own size did not change while the window grew.
      expect(await ptySize(page)).toEqual(pty0)
      await press('left')
      await check(RW, { left: false, right: true })
      await press('right')
      await check(0, { left: false, right: false })
      // The page gives a window that never answered half a second, then takes
      // the room for the sidebar itself. That wait must not outlive the keys:
      // fast presses on Windows left the terminal 236 px short (107 columns of
      // 141) once the first press's wait ran out. Past it, nothing moves.
      await page.waitForTimeout(700)
      expect(await termWidth(page), 'the terminal width after the wait').toEqual(t0)
      expect(await ptySize(page)).toEqual(pty0)
    })
  }
})

test.describe('title row', () => {
  for (const how of ['alt+T', 'chevron'] as const) {
    test(`folds by ${how}: a thin row, the sidebar buttons in the tab strip at 12 px and working; one click unfolds it`, async ({ win }) => {
      const { app, page } = win
      await ready(page)
      const frame = page.locator('[data-aqua-frame]')
      const unfold = page.getByRole('button', { name: /^Unfold the title row/ })
      const t0 = await termWidth(page)
      if (how === 'alt+T') await page.keyboard.press('Alt+KeyT')
      else await page.getByRole('button', { name: /^Fold the title row/ }).click()
      await expect(frame).toHaveAttribute('data-folded', 'true')
      await expect.poll(async () => (await unfold.boundingBox())?.height).toBe(12)

      for (const side of ['left', 'right'] as const) {
        const b = page.locator(`${toggle(side)}[data-in="strip"]`)
        await expect(b).toHaveCount(1)
        expect((await b.boundingBox())?.width).toBe(12)
        // Inside the tab strip, below the thin row.
        const box = (await b.boundingBox())!
        expect(box.y).toBeGreaterThanOrEqual(12)
        expect(box.y + box.height).toBeLessThanOrEqual(12 + 32)
        expect(await uncovered(page, toggle(side)), `the ${side} button is covered`).toBe(true)
      }
      const w0 = (await mainBounds(app)).width
      await page.locator(toggle('right')).click()
      await expect.poll(async () => (await mainBounds(app)).width).toBe(w0 + RW)
      await expect(page.getByRole('complementary', { name: 'Right sidebar' })).toHaveCount(1)
      expect(await uncovered(page, toggle('right')), 'the right button is covered with its panel open').toBe(true)
      await page.locator(toggle('left')).click()
      await expect.poll(async () => (await mainBounds(app)).width).toBe(w0 + RW + LW)
      expect(await uncovered(page, toggle('left')), 'the left button is covered with its panel open').toBe(true)
      await page.locator(toggle('left')).click()
      await page.locator(toggle('right')).click()
      await expect.poll(async () => (await mainBounds(app)).width).toBe(w0)
      await expect.poll(() => termWidth(page)).toEqual(t0)

      await unfold.click()
      await expect(frame).not.toHaveAttribute('data-folded', 'true')
      await expect(page.getByRole('button', { name: /^Fold the title row/ })).toBeVisible()
      await expect(page.locator('[data-toggle][data-in="strip"]')).toHaveCount(0)
      await expect(page.locator('[data-toggle]')).toHaveCount(2)
    })
  }
})

test.describe('workspaces', () => {
  const level = (page: Page) => page.locator('[data-level]').getAttribute('data-level')

  test('the workspaces button goes round: chat → workspace → every workspace → chat', async ({ win }) => {
    const { page } = win
    await ready(page)
    const btn = page.getByRole('button', { name: 'Workspaces', exact: true })
    expect(await level(page)).toBe('chat')
    await expect(btn).toHaveAttribute('aria-pressed', 'false')
    for (const want of ['ws', 'all', 'chat']) {
      await btn.click()
      await expect.poll(() => level(page)).toBe(want)
      await expect(btn).toHaveAttribute('aria-pressed', String(want !== 'chat'))
    }
    // Back on the terminal, the keys go to it again.
    await expect(page.getByRole('textbox', { name: 'Terminal input' })).toBeFocused()
  })

  test('Ctrl+Shift+↑ steps out, Ctrl+Shift+↓ and Esc step back in', async ({ win }) => {
    const { page } = win
    await ready(page)
    await page.getByRole('textbox', { name: 'Terminal input' }).focus()
    const out = 'ControlOrMeta+Shift+ArrowUp'
    const into = 'ControlOrMeta+Shift+ArrowDown'
    await page.keyboard.press(out)
    await expect.poll(() => level(page)).toBe('ws')
    await page.keyboard.press(out)
    await expect.poll(() => level(page)).toBe('all')
    await page.keyboard.press(out)               // the top: it stays
    await expect.poll(() => level(page)).toBe('all')
    await page.keyboard.press('Escape')
    await expect.poll(() => level(page)).toBe('ws')
    await page.keyboard.press('Escape')
    await expect.poll(() => level(page)).toBe('chat')
    await page.keyboard.press(out)
    await page.keyboard.press(out)
    await expect.poll(() => level(page)).toBe('all')
    await page.keyboard.press(into)
    await expect.poll(() => level(page)).toBe('ws')
    await page.keyboard.press(into)
    await expect.poll(() => level(page)).toBe('chat')
    // At the terminal, Esc is the terminal's own key (vi, less): the window lets it through.
    await page.keyboard.press('Escape')
    expect(await level(page)).toBe('chat')
  })
})
