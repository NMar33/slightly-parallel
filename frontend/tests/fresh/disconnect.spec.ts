import { test, expect } from '@playwright/test'

/** Setup's Disconnect: stop observing a project and undo what Setup wrote in its folder. */

const CODE = process.env.FRESH_CODE ?? 'notes'

test('disconnect the project on the Setup page', async ({ page }) => {
  await page.goto('/setup')
  await page.getByRole('button', { name: `Disconnect ${CODE}` }).click()
  const dialog = page.getByRole('dialog')
  await expect(dialog).toBeVisible()
  const confirm = dialog.getByPlaceholder(/to confirm/)
  if (await confirm.count()) await confirm.fill(CODE)
  await dialog.getByRole('button', { name: /disconnect/i }).click()
  await expect.poll(async () => {
    const d = await (await page.request.get('/api/setup/info')).json()
    return d.integrations.some((i: { project: string }) => i.project === CODE)
  }).toBe(false)
  await expect(page.getByRole('button', { name: `Disconnect ${CODE}` })).toHaveCount(0)
})
