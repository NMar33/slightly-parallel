import { test, expect, PROJECT, ready } from './fixtures'

test('neither tab-group control covers the color line when hovered', async ({ win, shell, server }, info) => {
  const { page } = win
  const name = `bap-${shell.id}`
  const response = await server.api.post('/api/terminal/groups', {
    data: { name, color: 5, project: PROJECT, tabs: [shell.id] },
  })
  expect(response.ok(), await response.text()).toBeTruthy()
  await page.reload()
  await ready(page)
  const group = page.getByRole('group', { name, exact: true })
  const fold = group.getByRole('button', { name, exact: true })
  const settings = group.getByRole('button', { name: `Tab group settings: ${name}` })
  const header = fold.locator('..')
  for (const expanded of [true, false]) {
    await expect(fold).toHaveAttribute('aria-expanded', String(expanded))
    for (const [control, label] of [[fold, 'label'], [settings, 'settings']] as const) {
      await control.hover()
      await header.screenshot({ path: info.outputPath(`${expanded}-${label}.png`) })
      await expect.poll(() => header.evaluate((element) => {
        const bottom = element.getBoundingClientRect().bottom - 1
        return [...element.querySelectorAll('button')].map((button) => {
          const { left, width } = button.getBoundingClientRect()
          return document.elementFromPoint(left + width / 2, bottom) === element
        })
      }), { message: 'the accent line below both buttons belongs to the header' }).toEqual([true, true])
    }
    if (expanded) await fold.click()
  }
})
