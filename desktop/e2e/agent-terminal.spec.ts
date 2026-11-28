import { execFileSync } from 'node:child_process'
import fs from 'node:fs'
import path from 'node:path'
import type { APIRequestContext, Page } from '@playwright/test'
import { expect, expectLine, openShell, PROJECT, ready, ROOT, sessionTab, sessions, test, typeLine, URL_, WINDOWS } from './fixtures'

const AGENT = 'cc-e2ec1623'
const launchMenu = "Go to agent's terminal"
const resumeMenu = "Open / resume agent's terminal"

function linkTabs(...ids: string[]) {
  const registry = path.join(ROOT, 'data', 'terminal', 'sessions.json')
  const data = JSON.parse(fs.readFileSync(registry, 'utf8')) as { sessions: { id: string; agent_id: string }[] }
  for (const session of data.sessions) if (ids.includes(session.id)) session.agent_id = AGENT
  fs.writeFileSync(registry + '.e2e', JSON.stringify(data))
  fs.renameSync(registry + '.e2e', registry)
}

async function waitForTabs(api: APIRequestContext, ...ids: string[]) {
  await expect.poll(async () => {
    const response = await api.get('/api/terminal/tabs')
    const { tabs } = await response.json() as { tabs: Record<string, { agent_id: string }> }
    return ids.every((id) => tabs[id]?.agent_id === AGENT)
  }).toBe(true)
}

async function printMention(page: Page, label = AGENT) {
  await typeLine(page, `echo ${label}`)
  await expectLine(page, label)
  const row = page.locator('.aqua-screen .xterm-rows > div').filter({ hasText: new RegExp(`^${label}\\s*$`) })
  await row.click({ position: { x: 24, y: 8 } })
  return page.getByRole('dialog', { name: 'Chat' })
}

const label = 'Fixture agent display name'

async function recordAgent(server: { api: APIRequestContext; dir: string }, sid: string) {
  const repo = path.resolve(__dirname, '..', '..')
  const python = path.join(repo, 'backend', '.venv', WINDOWS ? 'Scripts/python.exe' : 'bin/python')
  execFileSync(python, [path.join(repo, 'scripts', 'hooks', 'capture-cli.py'), '--phase', 'full',
    '--project', PROJECT, '--data-root', path.join(ROOT, 'data'), '--agent', AGENT, '--tool', 'claude-code',
    '--session', 'e2e-agent-terminal-mention', '--cwd', server.dir, '--text-stdin', '--agent-text', 'Fixture reply'],
  { input: 'Dashboard mention fixture', env: { ...process.env, SP_TERMINAL: sid, SP_PORT: new URL(URL_).port }, stdio: ['pipe', 'ignore', 'inherit'] })
  await expect.poll(async () => {
    const response = await server.api.post(`/api/agents/${AGENT}/rename`, { data: { name: label, actor: 'operator' } })
    return response.status()
  }).toBe(200)
}

test('an agent mention offers a jump and selects its live tab', async ({ win, shell, server }) => {
  const { page } = win
  const target = await openShell(server.api, 'agent-target')
  linkTabs(target.id)
  await waitForTabs(server.api, target.id)
  const menu = await printMention(page)
  await menu.getByRole('menuitem', { name: launchMenu, exact: true }).click()
  await expect(sessionTab(page, target.id)).toHaveAttribute('aria-selected', 'true')
  await expect(sessionTab(page, shell.id)).toHaveAttribute('aria-selected', 'false')
})

test('the chat’s display name in terminal output opens the same agent menu', async ({ win, server }) => {
  const { page } = win
  const target = await openShell(server.api, 'named-agent target')
  await recordAgent(server, target.id)
  await waitForTabs(server.api, target.id)
  await page.reload()
  const menu = await printMention(page, label)
  await menu.getByRole('menuitem', { name: launchMenu, exact: true }).click()
  await expect(sessionTab(page, target.id)).toHaveAttribute('aria-selected', 'true')
})

test('the agent menu wakes a sleeping tab under the same id', async ({ win, server }) => {
  const { page } = win
  const target = await openShell(server.api, 'sleeping-target')
  linkTabs(target.id)
  await waitForTabs(server.api, target.id)
  const asleep = await server.api.post(`/api/terminal/sessions/${target.id}/sleep`, { data: { actor: 'operator' } })
  expect(asleep.ok(), await asleep.text()).toBe(true)
  const menu = await printMention(page)
  await menu.getByRole('menuitem', { name: launchMenu, exact: true }).click()
  await page.getByRole('dialog', { name: 'Wake agent terminal' }).getByRole('button', { name: 'Wake terminal' }).click()
  await expect(sessionTab(page, target.id)).toHaveAttribute('aria-selected', 'true')
  await expect.poll(async () => (await sessions(server.api)).find((s) => s.id === target.id)?.asleep).toBe(false)
})

test('an agent without a terminal has a resume action, while other cards do not', async ({ win, server }) => {
  const { page } = win
  await recordAgent(server, '')
  const menu = await printMention(page)
  await expect(menu.getByRole('menuitem', { name: resumeMenu, exact: true })).toBeVisible()
  let asked: unknown
  let resumed = ''
  await page.route('**/api/terminal/sessions', async (route) => {
    if (route.request().method() !== 'POST') return route.continue()
    asked = route.request().postDataJSON()
    const opened = await openShell(server.api, 'resumed agent fixture')
    resumed = opened.id
    linkTabs(resumed)
    const session = (await sessions(server.api)).find((s) => s.id === resumed)
    await route.fulfill({ status: 201, json: { session } })
  })
  await menu.getByRole('menuitem', { name: resumeMenu, exact: true }).click()
  const confirm = page.getByRole('dialog', { name: 'Resume agent terminal' })
  await expect(confirm).toContainText(AGENT)
  const preview = await (await server.api.get(`/api/terminal/resume/${AGENT}`)).json()
  await expect(confirm).toContainText(preview.cwd)
  expect(asked).toBeUndefined()
  await confirm.getByRole('button', { name: 'Resume terminal' }).click()
  await expect.poll(() => asked).toMatchObject({
    kind: 'resume', agent: AGENT, expected_cwd: preview.cwd, resume_revision: preview.resume_revision,
  })
  await expect.poll(() => resumed).toMatch(/^t/)
  await expect(sessionTab(page, resumed)).toHaveAttribute('aria-selected', 'true')
  await ready(page)

  await typeLine(page, 'echo dc_cc266f82')
  await expectLine(page, 'dc_cc266f82')
  await page.locator('.aqua-screen .xterm-rows > div').filter({ hasText: /^dc_cc266f82\s*$/ })
    .click({ position: { x: 24, y: 8 } })
  const decision = page.getByRole('dialog', { name: 'Decision' })
  await expect(decision).toBeVisible()
  await expect(decision.getByRole('menuitem', { name: /agent.s terminal/ })).toHaveCount(0)
})

test('several terminals are offered with the newest first and a choice selects the requested tab', async ({ win, server }) => {
  const { page } = win
  const older = await openShell(server.api, 'older agent terminal')
  const newer = await openShell(server.api, 'newer agent terminal')
  linkTabs(older.id, newer.id)
  await waitForTabs(server.api, older.id, newer.id)
  // Set the activity times so an asynchronous shell prompt cannot reorder the fixtures.
  const clock = Date.now() / 1000
  const activity = new Map([[older.id, clock + 1], [newer.id, clock + 2]])
  const listed = await server.api.get('/api/terminal/sessions')
  const data = await listed.json() as { sessions: { id: string; last_output: number }[] }
  for (const row of data.sessions) {
    const time = activity.get(row.id)
    if (time !== undefined) row.last_output = time
  }
  await page.route('**/api/terminal/sessions', (route) => route.request().method() === 'GET'
    ? route.fulfill({ json: data }) : route.continue())
  await page.reload()
  const menu = await printMention(page)
  await menu.getByRole('menuitem', { name: launchMenu, exact: true }).click()
  const choices = menu.getByRole('menu', { name: launchMenu })
  await expect(choices.getByRole('menuitem')).toHaveText(['newer agent terminal', 'older agent terminal'])
  await choices.getByRole('menuitem', { name: 'older agent terminal' }).click()
  await expect(sessionTab(page, older.id)).toHaveAttribute('aria-selected', 'true')
})

test('an agent menu in the dashboard returns to the terminal and focuses its tab', async ({ win, server }) => {
  const { app, page } = win
  const target = await openShell(server.api, 'dashboard target')
  linkTabs(target.id)
  await waitForTabs(server.api, target.id)
  await recordAgent(server, target.id)
  await page.getByRole('button', { name: 'Dashboard', exact: true }).click()
  const dashboard = app.context().pages().find((p) => p !== page && p.url().startsWith(URL_))!
  await dashboard.getByRole('link', { name: 'Agents', exact: true }).click()
  await dashboard.evaluate(() => Reflect.set(window, '__agentDashboardDocument', true))
  await dashboard.locator(`[data-agent-terminal="${AGENT}"]`).first().click()
  await dashboard.getByRole('menuitem', { name: launchMenu, exact: true }).click({ noWaitAfter: true })
  await expect(page.getByRole('button', { name: 'Dashboard', exact: true })).toBeVisible()
  await expect(sessionTab(page, target.id)).toHaveAttribute('aria-selected', 'true')
  expect(await dashboard.evaluate(() => ({
    pathname: location.pathname, sameDocument: Reflect.get(window, '__agentDashboardDocument'),
  }))).toEqual({ pathname: '/agent', sameDocument: true })
})

test('Electron refuses malformed agent and tab ids before notifying the terminal', async ({ win }) => {
  const { app, page } = win
  await page.evaluate(() => {
    const received: unknown[] = []
    Reflect.set(window, '__agentTerminalTest', received)
    Reflect.get(window, 'spWindow')?.observeAgentTerminal?.((target: unknown) => received.push(target))
  })
  const supported = await page.evaluate(() => typeof Reflect.get(window, 'spWindow')?.openAgentTerminal)
  expect(supported).toBe('function')
  await page.evaluate((id) => {
    const bridge = Reflect.get(window, 'spWindow')
    bridge.openAgentTerminal(id + '\n')
    bridge.openAgentTerminal(id, '../elsewhere')
    bridge.openAgentTerminal('https://example.invalid/')
  }, AGENT)
  await app.evaluate(() => true)
  expect(await page.evaluate(() => Reflect.get(window, '__agentTerminalTest'))).toEqual([])
})

test('a dashboard request cannot wake a tab without a terminal confirmation click', async ({ win, server }) => {
  const { app, page } = win
  const target = await openShell(server.api, 'sleeping dashboard target')
  linkTabs(target.id)
  const asleep = await server.api.post(`/api/terminal/sessions/${target.id}/sleep`, { data: { actor: 'operator' } })
  expect(asleep.ok(), await asleep.text()).toBe(true)
  await page.getByRole('button', { name: 'Dashboard', exact: true }).click()
  const dashboard = app.context().pages().find((p) => p !== page && p.url().startsWith(URL_))!
  const wakeRequests: string[] = []
  page.on('request', (request) => {
    if (request.method() === 'POST' && request.url().endsWith(`/${target.id}/wake`)) wakeRequests.push(request.url())
  })
  await dashboard.evaluate(({ agent, id }) => {
    window.location.assign(`/_sp/terminal-agent/${agent}/${id}`)
  }, { agent: AGENT, id: target.id })
  const confirm = page.getByRole('dialog', { name: 'Wake agent terminal' })
  await expect(confirm).toBeVisible()
  await expect(confirm).toContainText(AGENT)
  await expect(confirm).toContainText(target.id)
  await expect(confirm).toContainText('sleeping dashboard target')
  await expect(confirm).toContainText((await asleep.json()).session.wake_cwd)
  await confirm.getByRole('button', { name: 'Wake terminal' }).evaluate((button: HTMLButtonElement) => button.click())
  expect(wakeRequests).toEqual([])
  await confirm.getByRole('button', { name: 'Wake terminal' }).click()
  await expect(sessionTab(page, target.id)).toHaveAttribute('aria-selected', 'true')
  expect(wakeRequests).toHaveLength(1)
})

for (const record of ['unknown', 'unresumable'] as const) {
  test(`an ${record} chat without a tab does not offer resume`, async ({ win }) => {
    const { page } = win
    const agent = record === 'unknown' ? 'cc-e2ecfc00' : 'cursor-e2ec1624'
    const details = page.waitForResponse((response) =>
      new URL(response.url()).pathname === `/api/agent/${agent}`)
    if (record === 'unresumable') {
      await page.route(`**/api/agent/${agent}`, (route) => route.fulfill({
        json: { agent: { agent_id: agent, agent_name: 'Unresumable fixture', tool: 'cursor', session_ref: 'fixture' } },
      }))
    }
    const card = await printMention(page, agent)
    expect((await details).status()).toBe(record === 'unknown' ? 404 : 200)
    await expect(card).toContainText(record === 'unknown' ? 'No such chat' : 'Unresumable fixture')
    await expect(card.getByRole('menuitem', { name: resumeMenu, exact: true })).toHaveCount(0)
  })
}
