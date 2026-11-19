import { expect, test } from '@playwright/test'

test('Notes keeps separate comments on a checklist item and on the whole note', async ({ page, request }) => {
  await request.get('/api/health', { headers: { 'Sec-Fetch-Site': 'same-origin' } })
  const agent = { project: 'alpha-labs', agent_id: 'cc-e2e-note-comments', kind: 'report' }
  const write = (body: Record<string, unknown>) => request.post('/api/notes/write', {
    headers: { 'X-SP-Via': 'mcp' },
    data: { ...agent, ...body },
  })
  const created = await write({ text: '# Comment review\n\n## Checklist\n\n- [ ] Keep this item' })
  expect(created.ok(), await created.text()).toBeTruthy()
  const { id } = await created.json() as { id: string }

  await page.goto(`/notes?note=${id}`)
  const note = page.getByRole('article', { name: 'Comment review', exact: true })
  const rowComment = note.getByRole('button', { name: 'Comment on: Keep this item', exact: true })
  const noteComment = note.getByRole('button', { name: 'Comment on the note', exact: true })
  const tick = note.getByRole('checkbox', { name: 'Keep this item' })
  const input = note.getByRole('textbox', { name: 'Comment', exact: true })
  const send = note.getByRole('button', { name: 'Send comment', exact: true })

  await rowComment.click()
  await input.fill('Keep the desktop layout.\nCheck the mobile layout separately.')
  await send.click()
  await expect(page.getByText('Keep the desktop layout.', { exact: false })).toBeVisible()
  await expect(tick).not.toBeChecked()
  await rowComment.click()

  await noteComment.click()
  await input.fill('These comments apply to this review.')
  await send.click()
  await expect(page.getByText('These comments apply to this review.')).toBeVisible()

  await page.reload()
  await expect(tick).not.toBeChecked()
  const saved = await request.get(`/api/notes/${id}/agent`)
  expect(saved.ok()).toBeTruthy()
  const detail = await saved.json()
  expect(detail.comments).toMatchObject([
    { text: 'Keep the desktop layout.\nCheck the mobile layout separately.', section: 'Checklist', label: 'Keep this item', version: 1 },
    { text: 'These comments apply to this review.', item: null, version: 1 },
  ])
  await rowComment.click()
  await expect(page.getByText('Keep the desktop layout.', { exact: false })).toBeVisible()

  const rewritten = await write({ id, base: 1, text: '# Comment review\n\n## Checklist\n\n- [ ] Check a different item' })
  expect(rewritten.ok(), await rewritten.text()).toBeTruthy()
  await page.reload()
  await expect(note.getByRole('checkbox', { name: 'Check a different item' })).toBeVisible()
  await noteComment.click()
  await expect(page.getByText('Keep the desktop layout.', { exact: false })).toBeVisible()
  await expect(page.getByText('Keep this item', { exact: false })).toBeVisible()
  await expect(page.getByText('These comments apply to this review.')).toBeVisible()
})
