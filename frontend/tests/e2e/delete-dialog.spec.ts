import fs from 'node:fs'
import path from 'node:path'
import { test as base, expect } from '@playwright/test'

// The direct API calls stand in for the operator's pages, so they carry the
// cookie the server hands a page of its own (server.OperatorCookie).
const test = base.extend({
  request: async ({ request }, use) => {
    await request.get('/api/health', { headers: { 'Sec-Fetch-Site': 'same-origin' } })
    await use(request)
  },
})

/**
 * A project delete that a member's chat holds back (tk_d1d25a4d step 2,
 * note nt_9de63b9e §5), in the sandbox copy of the demo data: a chat of
 * pdr-framework-dev joins alpha-labs; the delete dialog lists it with a
 * «Move to alpha-labs» button; the delete is refused; the move goes through;
 * then the delete does. It deletes a demo project, so it runs last, alone
 * (playwright.config.ts, project "delete").
 */
const PROJECT = 'pdr-framework-dev'
const AGENT = 'mira-sztern-capture-doc-2608-08'
const TO = 'alpha-labs'

test('delete-dialog: a held project offers the move, then deletes', async ({ page, request }) => {
  const root = process.env.SP_E2E_DATA_ROOT
  test.skip(!root, 'runs on the server this config starts (SP_E2E_DATA_ROOT)')
  // The move refuses a chat written in the last minute; the copy's files are
  // as new as the run. Ten minutes back.
  const folder = path.join(root!, 'projects', PROJECT, 'chats', AGENT)
  const old = new Date(Date.now() - 600_000)
  for (const f of fs.readdirSync(folder)) fs.utimesSync(path.join(folder, f), old, old)

  const join = await request.post(`/api/agents/${AGENT}/membership`, { data: { op: 'join', project: TO } })
  expect(join.status(), await join.text()).toBe(200)

  await page.goto('/setup')
  const row = page.getByRole('listitem').filter({ hasText: PROJECT }).filter({ has: page.getByRole('button', { name: /Delete data/ }) })
  await row.getByRole('button', { name: /Delete data/ }).click()
  const dialog = page.getByRole('dialog')
  const held = dialog.getByTestId('held-chats')
  await expect(held).toContainText(AGENT)

  // 1. The delete is refused while the chat is held, and names it.
  await dialog.getByLabel('Type the project code to confirm').fill(PROJECT)
  await dialog.getByRole('button', { name: 'Delete data', exact: true }).click()
  await expect(page.getByText(/holds chats of agents that are members elsewhere/).first()).toBeVisible()
  expect((await (await request.get('/api/setup/info')).json()).data_projects.some((p: { code: string }) => p.code === PROJECT)).toBe(true)

  // 2–3. «Move to alpha-labs» moves the chat.
  await held.getByRole('button', { name: `Move to ${TO}` }).click()
  await expect(page.getByText(`Moved the chat of ${AGENT} to ${TO}.`)).toBeVisible()
  await expect(held).toHaveCount(0)
  const after = await (await request.get(`/api/agents/${AGENT}/membership`)).json()
  expect(after.members).toEqual([TO])

  // 4. The delete goes through.
  await dialog.getByRole('button', { name: 'Delete data', exact: true }).click()
  await expect(page.getByText(new RegExp(`Moved \\d+ entr(y|ies) for ${PROJECT}`))).toBeVisible()
  const info = await (await request.get('/api/setup/info')).json()
  expect(info.data_projects.some((p: { code: string }) => p.code === PROJECT)).toBe(false)
  const chats = await (await request.get(`/api/sessions?project=${TO}`)).json()
  expect(chats.sessions.some((s: { agent_id: string; project: string }) => s.agent_id === AGENT && s.project === TO)).toBe(true)
})
