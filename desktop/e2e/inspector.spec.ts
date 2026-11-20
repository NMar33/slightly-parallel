import fs from 'node:fs'
import path from 'node:path'

import { expect, PROJECT, ready, ROOT, test } from './fixtures'

test('a project shell can organize a task and reuse it in its Markdown draft', async ({ win, server }) => {
  const { page, app } = win
  const title = 'Check the project inspector'
  const body = 'Записать результат проверки.'
  const create = await server.api.post('/api/tasks', { data: {
    project: PROJECT, title, description: body, status: 'todo', actor: 'operator',
  } })
  expect(create.ok(), await create.text()).toBeTruthy()
  const id = (await create.json()).metadata.id as string
  const lane = 'Terminal QA'
  const laneTask = await server.api.post('/api/tasks', { data: {
    project: PROJECT, title: 'Check a different card', status: 'done', assignee: lane, lane, actor: 'operator',
  } })
  expect(laneTask.ok(), await laneTask.text()).toBeTruthy()

  await ready(page)
  await page.getByRole('button', { name: 'Right sidebar', exact: true }).click()
  const inspector = page.getByRole('complementary', { name: 'Right sidebar' })
  await inspector.getByRole('tab', { name: 'Tasks' }).click()
  await inspector.getByRole('checkbox', { name: 'Only done' }).check()
  await expect(inspector.getByRole('button', { name: /Check a different card/ })).toBeVisible()
  await expect(inspector.getByRole('button', { name: new RegExp(title) })).toHaveCount(0)
  await inspector.getByRole('checkbox', { name: 'Only done' }).uncheck()
  await inspector.getByRole('button', { name: new RegExp(title) }).click()
  await expect(inspector.getByText(body, { exact: true })).toBeVisible()
  await inspector.getByLabel('Column', { exact: true }).selectOption('doing')
  await expect(inspector.getByLabel('Column', { exact: true })).toHaveValue('doing')
  await inspector.getByLabel('Lane', { exact: true }).selectOption(lane)
  await expect.poll(async () => {
    const row = (await (await server.api.get(`/api/tasks/${id}`)).json()).metadata
    return { status: row.status, lane: row.lane, assignee: row.assignee }
  }).toEqual({ status: 'doing', lane, assignee: lane })

  const draft = inspector.getByRole('textbox', { name: 'Project draft' })
  await inspector.getByRole('tab', { name: 'Draft' }).click()
  const prefix = '## Мои заметки\n\nНичего не потерять.'
  await draft.fill(prefix)
  await inspector.getByRole('tab', { name: 'Tasks' }).click()
  await inspector.getByRole('button', { name: new RegExp(title) }).click()
  await inspector.getByRole('button', { name: 'Add to draft' }).click()
  await expect(draft).toHaveValue(new RegExp(`^## Мои заметки[\\s\\S]*${id}[\\s\\S]*${body}`))
  const original = await draft.inputValue()

  const target = path.join(ROOT, 'work', 'inspector-draft.md')
  await app.evaluate(({ dialog }, filePath) => {
    dialog.showSaveDialog = async () => ({ canceled: false, filePath })
  }, target)
  await inspector.getByRole('button', { name: 'Save as Markdown' }).click()
  await expect.poll(() => fs.existsSync(target) ? fs.readFileSync(target, 'utf8') : '').toBe(original)
  await expect(draft).toHaveValue(original)

  const oldTaskDraft = JSON.stringify({ title: 'A separate board draft', body: 'Keep this too' })
  await page.evaluate(([project, value]) => localStorage.setItem(`sp-task-draft:${project}`, value), [PROJECT, oldTaskDraft])
  await draft.evaluate((el, end) => (el as HTMLTextAreaElement).setSelectionRange(0, end), prefix.length)
  await inspector.getByRole('button', { name: 'Create task', exact: true }).click()
  const form = page.getByRole('dialog', { name: 'New task' })
  await expect(form.getByLabel('Title')).toHaveValue('Мои заметки')
  await expect(form.locator('#task-desc')).toHaveValue('Ничего не потерять.')
  await form.getByRole('button', { name: 'Cancel', exact: true }).click()
  await expect(form).toHaveCount(0)
  await expect(draft).toHaveValue(original)
  expect(await page.evaluate((project) => localStorage.getItem(`sp-task-draft:${project}`), PROJECT)).toBe(oldTaskDraft)

  await inspector.getByRole('button', { name: 'Clear draft' }).click()
  await expect(draft).toHaveValue('')
  await inspector.getByRole('button', { name: 'Undo clear' }).click()
  await expect(draft).toHaveValue(original)

  await page.reload()
  await page.getByRole('button', { name: 'Right sidebar', exact: true }).click()
  await inspector.getByRole('tab', { name: 'Draft' }).click()
  await expect(draft).toHaveValue(original)
})
