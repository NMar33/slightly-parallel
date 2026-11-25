import { test as base, expect } from '@playwright/test'

// The direct API calls stand in for the operator's pages (their cookie).
const test = base.extend({
  request: async ({ request }, use) => {
    await request.get('/api/health', { headers: { 'Sec-Fetch-Site': 'same-origin' } })
    await use(request)
  },
})

/**
 * A task moved between projects keeps its id, and the card's history says
 * «moved from A to B» (tk_d1d25a4d step 3, note nt_258a7ed7 §8). The task is
 * the test's own and goes back where it came from, so no other flow sees it
 * on the second board.
 */
const FROM = 'pdr-framework-dev'
const TO = 'beta-corp'

test('a moved task keeps its id and its history says where it came from', async ({ page, request }) => {
  const made = await request.post('/api/tasks', {
    data: { project: FROM, title: 'A task that moves between projects', status: 'todo', actor: 'operator' },
  })
  expect(made.ok(), await made.text()).toBeTruthy()
  const id = ((await made.json()) as { metadata: { id: string } }).metadata.id
  const moved = await request.post(`/api/tasks/${id}/move`, { data: { to: TO, actor: 'operator' } })
  expect(moved.ok(), await moved.text()).toBeTruthy()
  expect(((await moved.json()) as { where: string }).where).toBe(`${id} → ${TO}`)

  await page.goto(`/project/${TO}#tasks`)
  await page.getByRole('button', { name: 'Edit task: A task that moves between projects', exact: true }).click()
  const win = page.getByRole('dialog', { name: 'Edit task' })
  await expect(win).toBeVisible()
  const history = win.locator('details').filter({ hasText: 'History' }).last()
  await history.locator('summary').click()
  await expect(history.getByText(`from ${FROM} to ${TO}, by the operator`)).toBeVisible()
  await expect(history.getByText('moved', { exact: true })).toBeVisible()

  const back = await request.post(`/api/tasks/${id}/move`, { data: { to: FROM, actor: 'operator' } })
  expect(back.ok(), await back.text()).toBeTruthy()
})
