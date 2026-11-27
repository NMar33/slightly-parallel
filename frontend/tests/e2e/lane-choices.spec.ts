import fs from 'node:fs'
import path from 'node:path'
import { expect, test } from '@playwright/test'

const project = 'alpha-labs'
const boardLane = 'Film review'
const agentLane = 'Sound recording'
const agentCard = 'Check the microphone gain'
const wanted = 'Film reviwe'
const operatorCard = 'Review the cut on the board'

test('resolves an operator lane on its card and promotes an agent lane from the group', async ({ page, request }) => {
  const root = process.env.SP_E2E_DATA_ROOT
  test.skip(!root, 'A local fixture is needed to capture an operator message')
  const agent = 'cc-e2elanes01'
  const dir = path.join(root!, 'projects', project, 'chats', agent)
  fs.mkdirSync(dir, { recursive: true })
  fs.writeFileSync(path.join(dir, 'meta.json'), JSON.stringify({
    agent_id: agent, project, tool: 'claude-code', capture: 'hooks', message_count: 1,
  }))
  const at = new Date().toISOString().slice(0, 19)
  const chat = path.join(dir, 'chat.md')
  fs.writeFileSync(chat, `# Chat log — ${agent}\n\n## Turn 1 · ${at}\n**User**: #task check the audio\n**Agent**: Checking.\n`)
  await request.get('/api/health', { headers: { 'Sec-Fetch-Site': 'same-origin' } })
  const board = await request.post('/api/tasks/lanes', { data: { project, lane: boardLane, op: 'add' } })
  expect(board.ok()).toBeTruthy()
  const create = (title: string, lane?: string) => request.post('/api/tasks', {
    headers: { 'X-SP-Via': 'mcp' },
    data: { project, agent_id: agent, title, lane, tags: 'ag_idea' },
  })
  const filed = await create(agentCard, agentLane)
  expect(await filed.json()).toMatchObject({ metadata: { lane_kind: 'agent' } })
  fs.appendFileSync(chat, `\n## Turn 2 · ${at}\n**User**: #now-todo {${wanted}} ${operatorCard}\n`)
  const created = await create(operatorCard)
  expect(await created.json()).toMatchObject({ metadata: { status: 'todo', lane: 'Now' } })

  await page.goto(`/project/${project}#tasks`)
  await page.getByText('swim lanes', { exact: true }).click()
  const group = page.getByRole('button', { name: /^Agents/ })
  const agentTask = page.getByRole('button', { name: `Edit task: ${agentCard}`, exact: true })
  await expect(group).toHaveAttribute('aria-expanded', 'false')
  await expect(agentTask).not.toBeVisible()
  await group.click()
  await page.getByRole('button', { name: 'Unfold the From agents column', exact: true }).click()
  await expect(agentTask).toBeVisible()
  await page.getByRole('button', { name: 'To board', exact: true }).click()
  await expect(group).not.toBeVisible()
  await expect(agentTask).toBeVisible()

  const operatorTask = page.getByRole('button', { name: `Edit task: ${operatorCard}`, exact: true })
  await operatorTask.getByRole('button', { name: 'Choose lane' }).click()
  await operatorTask.getByRole('button', { name: boardLane, exact: true }).click()
  await expect(operatorTask.getByRole('button', { name: 'Choose lane' })).not.toBeVisible()
  const { tasks } = await (await request.get(`/api/tasks?project=${project}`)).json()
  expect(tasks.find((task: { title: string }) => task.title === operatorCard)).toMatchObject({ lane: boardLane })
})

test('a combined board keeps the same lane name scoped to each project', async ({ page, request }) => {
  const root = process.env.SP_E2E_DATA_ROOT
  test.skip(!root, 'A local fixture is needed to capture an operator message')
  const other = 'beta-corp'
  const agent = 'cc-e2elanes02'
  const dir = path.join(root!, 'projects', other, 'chats', agent)
  fs.mkdirSync(dir, { recursive: true })
  fs.writeFileSync(path.join(dir, 'meta.json'), JSON.stringify({
    agent_id: agent, project: other, tool: 'claude-code', capture: 'hooks', message_count: 1,
  }))
  const at = new Date().toISOString().slice(0, 19)
  fs.writeFileSync(path.join(dir, 'chat.md'),
    `# Chat log — ${agent}\n\n## Turn 1 · ${at}\n**User**: File the audio notes.\n**Agent**: Checking.\n`)
  await request.get('/api/health', { headers: { 'Sec-Fetch-Site': 'same-origin' } })
  const left = await request.post('/api/tasks', {
    data: { project, lane: 'Audio', assignee: 'Audio', title: 'Alpha audio review', status: 'todo' },
  })
  expect(left.status()).toBe(201)
  const right = await request.post('/api/tasks', {
    headers: { 'X-SP-Via': 'mcp' },
    data: { project: other, agent_id: agent, lane: 'audio', title: 'Beta audio review', tags: 'ag_idea' },
  })
  expect(await right.json()).toMatchObject({ metadata: { lane_kind: 'agent' } })
  const board = await request.post('/api/boards', { data: { name: 'Combined audio', projects: [project, other] } })
  expect(board.status()).toBe(201)
  const { id } = await board.json()
  await page.goto(`/kanban?board=${id}`)
  await page.getByText('swim lanes', { exact: true }).click()
  const mainCard = page.getByRole('button', { name: 'Edit task: Alpha audio review', exact: true })
  const agentCard = page.getByRole('button', { name: 'Edit task: Beta audio review', exact: true })
  const group = page.getByRole('button', { name: /^Agents/ })
  await expect(mainCard).toBeVisible()
  await expect(group).toHaveAttribute('aria-expanded', 'false')
  await group.click()
  await page.getByRole('button', { name: 'Unfold the From agents column', exact: true }).click()
  await expect(mainCard).toBeVisible()
  await expect(agentCard).toBeVisible()
})
