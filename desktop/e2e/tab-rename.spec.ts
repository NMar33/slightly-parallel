import { test, expect, ready } from './fixtures'

test('double-click renames a tab, Escape cancels a second edit and the name survives reload', async ({ win, shell }) => {
  const { page } = win
  await ready(page)
  const tab = page.getByRole('tablist', { name: 'Chats' }).locator(`[data-tab="${shell.id}"]`)
  await tab.getByRole('tab').dblclick()
  const name = tab.getByRole('textbox', { name: 'Name' })
  await expect(name).toBeFocused()
  await name.fill('Release shell')
  await name.press('Enter')
  await expect(tab.getByRole('tab')).toHaveAccessibleName(/^Release shell ·/)
  await tab.getByRole('tab').dblclick()
  await name.fill('Cancelled edit')
  await name.press('Escape')
  await expect(tab.getByRole('tab')).toHaveAccessibleName(/^Release shell ·/)
  await page.reload()
  await expect(tab.getByRole('tab')).toHaveAccessibleName(/^Release shell ·/)
})
