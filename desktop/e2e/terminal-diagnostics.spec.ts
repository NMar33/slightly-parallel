import fs from 'node:fs'
import path from 'node:path'
import { expect, expectLine, ROOT, test, typeLine } from './fixtures'
import { runPlan, touchpad } from './scrollProbe'

test('the terminal menu saves diagnostics without changing the displayed rows', async ({ win, shell }) => {
  const { page } = win
  await typeLine(page, 'echo diagnostic-42')
  await expectLine(page, 'diagnostic-42')
  const rows = page.locator('.aqua-screen .xterm-rows > div')
  const before = await rows.allTextContents()

  await page.locator('.aqua-screen .xterm-screen').click({ button: 'right', position: { x: 12, y: 12 } })
  await page.getByRole('menuitem', { name: 'Terminal menu…' }).click()
  const [response] = await Promise.all([
    page.waitForResponse((response) => response.url().endsWith(`/${shell.id}/diagnostics`)),
    page.getByRole('menuitem', { name: /Capture terminal state/ }).click(),
  ])
  expect(response.status()).toBe(201)
  const file = (await response.json() as { path: string }).path
  expect(path.dirname(file)).toBe(path.join(ROOT, 'data', 'diagnostics'))
  const body = JSON.parse(fs.readFileSync(file, 'utf8'))
  expect(body.browser.dom.live).toEqual(before)
  expect(body.browser.xterm.live.rowsByIndex.some(({ text }: { text: string }) => text.trim() === 'diagnostic-42')).toBe(true)
  expect(body.browser.scrollLayer.live.pos).toBe(0)
  await expect(page.getByText(file, { exact: false })).toBeVisible()
  expect(await rows.allTextContents()).toEqual(before)
})

test('the diagnostic shortcut leaves the tmux history reader where it was', async ({ win, shell }) => {
  test.skip(shell.backend !== 'tmux' || process.platform === 'darwin', 'tmux reader and shortcut')
  const { page } = win
  await typeLine(page, 'i=0; while [ "$i" -lt 100 ]; do echo diagnostic-history-$i; i=$((i + 1)); done')
  await expectLine(page, 'diagnostic-history-99')
  await runPlan(page, touchpad(85), 15)
  const reader = page.locator('.sp-reader')
  const rows = reader.locator('.xterm-rows > div')
  await expect(reader).toBeVisible()
  await reader.locator('textarea').focus()
  await expect.poll(async () => (await rows.allTextContents()).join(' ')).not.toContain('diagnostic-history-99')
  const before = await rows.allTextContents()
  const [response] = await Promise.all([
    page.waitForResponse((response) => response.url().endsWith(`/${shell.id}/diagnostics`)),
    page.keyboard.press('Control+Alt+Shift+d'),
  ])
  expect(response.status()).toBe(201)
  const file = (await response.json() as { path: string }).path
  const snapshot = JSON.parse(fs.readFileSync(file, 'utf8')).browser
  expect(snapshot.xterm.reader.viewportY).toBeLessThan(snapshot.xterm.reader.baseY)
  expect(snapshot.dom.reader).toEqual(before)
  await expect(reader).toBeVisible()
  expect(await rows.allTextContents()).toEqual(before)
})
