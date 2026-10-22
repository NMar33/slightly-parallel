import { test, expect } from '@playwright/test'

/** The dev start (`./run.sh`): the pages come from Vite and the data through its proxy. */

const CODE = process.env.FRESH_CODE ?? 'calc'

test('the overview and a project load through the hot-reload UI', async ({ page }) => {
  test.setTimeout(120_000) // the first load compiles the app
  const thrown: string[] = []
  page.on('pageerror', (e) => thrown.push(String(e)))
  await page.goto('/')
  await expect(page.getByRole('link', { name: 'Kanban' }).first()).toBeVisible({ timeout: 90_000 })
  await expect(page.getByText(CODE).first()).toBeVisible()
  await page.goto(`/project/${CODE}`)
  await expect(page.getByRole('heading', { name: CODE }).first()).toBeVisible({ timeout: 30_000 })
  await page.goto('/setup')
  await expect(page.getByText('Integrate your projects')).toBeVisible({ timeout: 30_000 })
  expect(thrown).toEqual([])
})
