import { test, expect, fullSize, openShell, ready } from './fixtures'

test('dragging tabs saves their order across reload without switching terminals', async ({ win, shell, server }) => {
  const { app, page } = win
  const other = await openShell(server.api, 'movable-shell')
  await page.reload()
  await fullSize(app, page)
  await ready(page)
  const strip = page.getByRole('tablist', { name: 'Chats' })
  const first = strip.locator(`[data-tab="${shell.id}"]`).getByRole('tab')
  const second = strip.locator(`[data-tab="${other.id}"]`).getByRole('tab')
  await first.click()
  await expect(first).toHaveAttribute('aria-selected', 'true')
  await second.dragTo(first, { targetPosition: { x: 4, y: 12 } })
  const order = () => strip.locator('[data-tab]').evaluateAll((tabs) => tabs.map((tab) => tab.getAttribute('data-tab')))
  await expect.poll(order).toEqual([other.id, shell.id])
  await expect(first).toHaveAttribute('aria-selected', 'true')
  await page.reload()
  await expect.poll(order).toEqual([other.id, shell.id])
})
