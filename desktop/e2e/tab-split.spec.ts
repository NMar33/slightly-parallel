import { test, expect, echoCalc, expectLine, fullSize, openShell, ready, sessions } from './fixtures'

test('opening a tab on the right keeps the left shell and puts keyboard input in the right shell', async ({ win, shell, server }, testInfo) => {
  const { app, page } = win
  const other = await openShell(server.api, 'right-hand-shell')
  await page.reload()
  await fullSize(app, page)
  await ready(page)
  const tab = (id: string) => page.locator(`[data-tab="${id}"]`).getByRole('tab')
  await tab(shell.id).click()
  await tab(other.id).click({ button: 'right' })
  await page.getByRole('menuitem', { name: 'Open on the right' }).click()
  const main = page.locator('.aqua-screen')
  const right = page.getByRole('region', { name: 'Terminal on the right' })
  const input = (pane: typeof right) => pane.getByRole('textbox', { name: 'Terminal input' })
  await expect(input(main)).toBeVisible()
  await expect(input(right)).toBeFocused()
  expect((await right.boundingBox())!.x).toBeGreaterThan((await main.boundingBox())!.x)
  await page.keyboard.type(echoCalc('right-pane-', '6*7'))
  await page.keyboard.press('Enter')
  await expect(right.locator('.xterm-rows > div').filter({ hasText: /^right-pane-42\s*$/ })).toBeVisible()
  await expect(main.locator('.xterm-rows')).not.toContainText('right-pane-42')
  await right.getByRole('button', { name: 'Close the right pane' }).click()
  await expect(right).toHaveCount(0)
  await expect(input(main)).toBeFocused()
  await page.keyboard.type(echoCalc('left-pane-', '6*7'))
  await page.keyboard.press('Enter')
  try {
    await expectLine(page, 'left-pane-42')
  } catch (error) {
    if (shell.backend === 'tmux') {
      // On macOS the command was visible, but the reply never reached the DOM.
      // The pane's own text separates execution from rendering on the next failure.
      const capture = await server.api.post(`/api/terminal/sessions/${shell.id}/capture`, {
        data: { mode: 'screen' }, timeout: 3000,
      }).then(async (response) => response.ok() ? (await response.json()).text : `HTTP ${response.status()}`)
        .catch(() => 'The tmux capture request did not finish.')
      await testInfo.attach('left tmux pane after closing the split', {
        body: String(capture), contentType: 'text/plain',
      })
    }
    throw error
  }
  await expect.poll(async () => (await sessions(server.api)).length).toBe(2)

  await tab(other.id).click({ button: 'right' })
  await page.getByRole('menuitem', { name: 'Open on the right' }).click()
  await expect(right).toBeVisible()
  const slept = await server.api.post(`/api/terminal/sessions/${other.id}/sleep`, { data: { actor: 'operator' } })
  expect(slept.ok(), await slept.text()).toBeTruthy()
  await expect(right).toHaveCount(0)
  await tab(other.id).click()
  await expect(tab(other.id)).toHaveAttribute('aria-selected', 'true')
})

test('a tab starts a new shell immediately to its right without splitting the window', async ({ win, shell, server }) => {
  const { app, page } = win
  const other = await openShell(server.api, 'another-shell')
  await page.reload()
  await fullSize(app, page)
  await ready(page)
  const strip = page.getByRole('tablist', { name: 'Chats' })
  const tab = (id: string) => strip.locator(`[data-tab="${id}"]`).getByRole('tab')
  const order = () => strip.locator('[data-tab]').evaluateAll((tabs) => tabs.map((item) => item.getAttribute('data-tab')))
  const original = tab(shell.id)
  await original.click()
  await expect.poll(order).toEqual([shell.id, other.id])
  await original.click({ button: 'right' })
  await page.getByRole('menuitem', { name: 'Open a new terminal on the right' }).click()
  await expect.poll(async () => (await sessions(server.api)).length).toBe(3)
  const opened = (await sessions(server.api)).find(({ id }) => id !== shell.id && id !== other.id)!
  await expect.poll(order).toEqual([shell.id, opened.id, other.id])
  await expect(tab(opened.id)).toHaveAttribute('aria-selected', 'true')
  await expect(page.getByRole('region', { name: 'Terminal on the right' })).toHaveCount(0)
  await expect(page.getByRole('textbox', { name: 'Terminal input' })).toBeFocused()
  await page.keyboard.type(echoCalc('new-right-shell-', '6*7'))
  await page.keyboard.press('Enter')
  await expectLine(page, 'new-right-shell-42')
  await page.reload()
  await expect.poll(order).toEqual([shell.id, opened.id, other.id])
  await expect(tab(opened.id)).toHaveAttribute('aria-selected', 'true')
})
