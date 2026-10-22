import { execFileSync } from 'node:child_process'
import fs from 'node:fs'
import os from 'node:os'
import path from 'node:path'
import { test as base, expect, type APIRequestContext, type Page } from '@playwright/test'

// The direct API calls here stand in for the operator's pages, so they carry
// the cookie the server hands a page of its own (server.OperatorCookie): one
// read marked as this site's, and the context keeps what it set.
const test = base.extend({
  request: async ({ request }, use) => {
    await request.get('/api/health', { headers: { 'Sec-Fetch-Site': 'same-origin' } })
    await use(request)
  },
})

/**
 * The core, clicked through the way a person uses it — the net under the
 * board and the task window after their split into many modules.
 *
 * Runs on the hermetic copy of the demo fixtures (playwright.config.ts), so
 * every test may write. Each test makes its own task with a unique title,
 * so the tests stay independent and can run in parallel on one board.
 */

const PROJECT = 'alpha-labs'

/** A title no other test (or earlier run on this server) can share. */
const unique = (what: string) => `${what} ${Date.now().toString(36)}${Math.random().toString(36).slice(2, 6)}`

const escape = (s: string) => s.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')

/**
 * A board column, found by its "+" (Add task to <label>): the outermost
 * element holding that button and no other column's — the column itself.
 * The columns carry no role or name of their own (see the report).
 */
function column(page: Page, label: string) {
  return page.locator('div')
    .filter({ has: page.getByRole('button', { name: `Add task to ${label}`, exact: true }) })
    .filter({ hasNot: page.getByRole('button', { name: new RegExp(`^Add task to (?!${escape(label)}$)`) }) })
    .first()
}

const card = (page: Page, title: string) =>
  page.getByRole('button', { name: `Edit task: ${title}`, exact: true })

async function openBoard(page: Page) {
  await page.goto(`/project/${PROJECT}#tasks`)
  await expect(page.getByRole('tab', { name: 'Tasks' })).toHaveAttribute('aria-selected', 'true')
  await expect(page.getByRole('button', { name: 'Add task to To do', exact: true })).toBeVisible()
}

/** The task as the server has it — the second check behind the page. */
async function taskByTitle(request: APIRequestContext, title: string) {
  const res = await request.get(`/api/tasks?project=${PROJECT}`)
  expect(res.ok()).toBeTruthy()
  const { tasks } = await res.json() as { tasks: Array<Record<string, string>> }
  return tasks.find((t) => t.title === title)
}

/** Add a task through a column's "+" and wait for its card. */
async function addTask(page: Page, title: string, to = 'To do') {
  await page.getByRole('button', { name: `Add task to ${to}`, exact: true }).click()
  const win = page.getByRole('dialog', { name: 'New task' })
  await expect(win).toBeVisible()
  await win.getByLabel('Title').fill(title)
  await win.getByRole('button', { name: 'Save', exact: true }).click()
  await expect(win).toBeHidden()
  await expect(column(page, to).getByRole('button', { name: `Edit task: ${title}`, exact: true })).toBeVisible()
}

async function openTask(page: Page, title: string) {
  await card(page, title).click()
  const win = page.getByRole('dialog', { name: 'Edit task' })
  await expect(win).toBeVisible()
  await expect(win.getByLabel('Title')).toHaveValue(title)
  return win
}

test.describe('core flows', () => {
  test('a task added on the board shows up as a card, and on the server', async ({ page, request }) => {
    const title = unique('Flow add')
    await openBoard(page)
    await addTask(page, title)
    const row = await taskByTitle(request, title)
    expect(row?.status).toBe('todo')
  })

  test('storyboard: an agent version and a pasted one are listed, read, compared', async ({ page, request }) => {
    const title = unique('Flow doc')
    const made = await request.post('/api/docs', { data: { project: PROJECT, kind: 'post', title } })
    expect(made.ok()).toBeTruthy()
    const { doc } = await made.json() as { doc: { id: string } }
    // The call the MCP tool doc_version makes: the agent's identity, the via mark.
    const posted = await request.post(`/api/docs/${doc.id}/versions`, {
      headers: { 'X-SP-Via': 'mcp' },
      data: { agent_id: 'cc-flowwriter', body: '# Launch\n\nFirst draft from the agent.', note: 'first pass' },
    })
    expect(posted.status()).toBe(201)

    await openBoard(page)
    await page.getByRole('button', { name: /^Storyboard/ }).click()
    await page.getByRole('radiogroup', { name: 'Documents' }).getByRole('radio', { name: new RegExp(escape(title)) }).click()
    const versions = page.getByRole('region', { name: 'Versions' })
    await expect(versions.getByRole('button', { name: 'Open version 1' })).toContainText('first pass')

    await versions.getByRole('button', { name: '+ paste a version' }).click()
    await versions.getByLabel('Text').fill('# Launch\n\nSecond draft, pasted by hand.')
    await versions.getByLabel('Note').fill('pasted from a chat')
    await versions.getByRole('button', { name: 'save version' }).click()
    await expect(versions.getByRole('button', { name: 'Open version 2' })).toContainText('pasted from a chat')
    await expect(versions.getByRole('listitem').filter({ has: page.getByRole('button', { name: 'Open version 2' }) })).toContainText('you')
    await expect(versions.getByRole('link', { name: 'cc-flowwriter' })).toHaveAttribute('href', '/agent/cc-flowwriter')

    await versions.getByRole('button', { name: 'Open version 2' }).click()
    const win = page.getByRole('dialog', { name: 'Version 2' })
    await expect(win.getByText('Second draft, pasted by hand.')).toBeVisible()
    await win.getByRole('radio', { name: 'changes from v1' }).click()
    await expect(win.getByText('First draft from the agent.')).toHaveClass(/line-through/)

    const d = await request.get(`/api/docs/${doc.id}`).then((r) => r.json()) as { versions: Array<{ agent_id: string; note: string }> }
    expect(d.versions.map((v) => [v.agent_id, v.note])).toEqual([['operator', 'pasted from a chat'], ['cc-flowwriter', 'first pass']])
  })

  test('the task window edits title and priority, and the edit survives a reopen', async ({ page, request }) => {
    const title = unique('Flow edit')
    const renamed = `${title} renamed`
    await openBoard(page)
    await addTask(page, title)

    const win = await openTask(page, title)
    await expect(win.getByLabel('Priority')).toHaveValue('med')
    await win.getByLabel('Priority').selectOption('high')
    await win.getByLabel('Title').fill(renamed)
    await win.getByLabel('Title').press('Control+Enter')
    await expect(win).toBeHidden()

    await expect(card(page, renamed)).toBeVisible()
    await expect(card(page, title)).toHaveCount(0)

    // Reopen: the window reads what was saved, not what was typed.
    const again = await openTask(page, renamed)
    await expect(again.getByLabel('Priority')).toHaveValue('high')
    await again.getByRole('button', { name: 'Cancel', exact: true }).click()
    await expect(again).toBeHidden()

    // And after a reload, from the server.
    await page.reload()
    await expect(card(page, renamed)).toBeVisible()
    const row = await taskByTitle(request, renamed)
    expect(row?.priority).toBe('high')
  })

  test('a card moves by the status chips and by drag and drop', async ({ page, request }) => {
    const title = unique('Flow move')
    await openBoard(page)
    await addTask(page, title)

    // Chips: To do → Doing.
    const win = await openTask(page, title)
    await win.getByRole('button', { name: 'Doing', exact: true }).click()
    await win.getByRole('button', { name: 'Save', exact: true }).click()
    await expect(win).toBeHidden()
    await expect(column(page, 'Doing').getByRole('button', { name: `Edit task: ${title}`, exact: true })).toBeVisible()
    await expect(column(page, 'To do').getByRole('button', { name: `Edit task: ${title}`, exact: true })).toHaveCount(0)
    expect((await taskByTitle(request, title))?.status).toBe('doing')

    // Drag: Doing → To do, dropped on the column's header (the column zone
    // takes it; a card's top half would take it as a reorder instead).
    // Under parallel load a drag now and then comes to nothing (about 1 in
    // 20 at 4 workers, other tests writing to the same board: the drop
    // never lands, likely a redraw mid-drag); the drag is retried, the
    // move itself is asserted.
    await expect(async () => {
      await card(page, title).dragTo(page.getByRole('button', { name: 'Add task to To do', exact: true }))
      await expect(column(page, 'To do').getByRole('button', { name: `Edit task: ${title}`, exact: true })).toBeVisible({ timeout: 2_000 })
    }).toPass({ timeout: 12_000 })
    await expect(column(page, 'Doing').getByRole('button', { name: `Edit task: ${title}`, exact: true })).toHaveCount(0)
    await expect.poll(async () => (await taskByTitle(request, title))?.status).toBe('todo')
  })

  test('marked Done from the window, the card lands in the Done column', async ({ page, request }) => {
    const title = unique('Flow done')
    await openBoard(page)
    await addTask(page, title)

    const win = await openTask(page, title)
    await win.getByRole('button', { name: 'Done', exact: true }).click()
    await win.getByLabel('Title').press('Control+Enter')
    await expect(win).toBeHidden()

    await expect(column(page, 'Done').getByRole('button', { name: `Edit task: ${title}`, exact: true })).toBeVisible()
    await expect(column(page, 'To do').getByRole('button', { name: `Edit task: ${title}`, exact: true })).toHaveCount(0)
    expect((await taskByTitle(request, title))?.status).toBe('done')
  })

  test('chats: pick a chat, read its turns, focus opens with F and leaves with Escape', async ({ page }) => {
    await page.goto('/chats')
    const list = page.getByRole('list', { name: 'Chats' })
    await expect(list.getByRole('button').first()).toBeVisible()

    // A chat that is not the one open by default.
    const other = list.locator('button[aria-pressed="false"]').first()
    await expect(other).toBeVisible()
    // Held by its place in the list: the "not pressed" filter would move on once it is.
    const at = await other.evaluate((el) => [...el.parentElement!.parentElement!.querySelectorAll('button[aria-pressed]')].indexOf(el))
    const pick = list.locator('button[aria-pressed]').nth(at)
    await pick.click()
    await expect(pick).toHaveAttribute('aria-pressed', 'true')

    const reader = page.getByRole('log', { name: 'Chat turns' })
    await expect(reader.getByRole('article').first()).toBeVisible()


    // F reads the keyboard only when no field has it.
    await pick.focus()
    await page.keyboard.press('f')
    const focus = page.getByRole('dialog', { name: /^Focus:/ })
    await expect(focus).toBeVisible()
    await expect(page).toHaveURL(/focus=1/)
    await page.keyboard.press('Escape')
    await expect(focus).toBeHidden()
    await expect(page).not.toHaveURL(/focus=1/)
  })

  test('standups: focus opens from the title row, walks the days, and leaves with Escape', async ({ page }) => {
    await page.goto(`/standups#project=${PROJECT}`)
    await page.getByRole('button', { name: 'Focus', exact: true }).click()
    const focus = page.getByRole('dialog', { name: /^Focus:/ })
    await expect(focus).toBeVisible()
    await expect(page).toHaveURL(/focus=1/)
    const days = focus.getByRole('list', { name: 'Days with a standup' })
    await expect(days.getByRole('button').first()).toHaveAttribute('aria-current', 'true')
    await expect(focus.getByText(/^day 1 of \d+/)).toBeVisible()
    // ] opens the day before; the address keeps it.
    await page.keyboard.press(']')
    await expect(focus.getByText(/^day 2 of \d+/)).toBeVisible()
    await expect(days.getByRole('button').nth(1)).toHaveAttribute('aria-current', 'true')
    await expect(page).toHaveURL(/day=\d{4}-\d{2}/)
    await page.keyboard.press('Escape')
    await expect(focus).toBeHidden()
    await expect(page).not.toHaveURL(/focus=1/)
    // F opens it again.
    await page.keyboard.press('f')
    await expect(focus).toBeVisible()
  })

  test('rules: group by changes the chapters; Edit opens and Cancel closes', async ({ page }) => {
    await page.goto('/rules')
    const contents = page.getByRole('navigation', { name: 'Contents' })
    const groupBy = page.getByRole('radiogroup', { name: 'group by' })
    await expect(groupBy.getByRole('radio', { name: 'tag' })).toBeChecked()
    await expect(contents.getByRole('button', { name: /^No tag \d+$/ })).toBeVisible()

    await groupBy.getByRole('radio', { name: 'month' }).click()
    await expect(groupBy.getByRole('radio', { name: 'month' })).toBeChecked()
    await expect(contents.getByRole('button', { name: /^August 2026 \d+$/ })).toBeVisible()
    await expect(contents.getByRole('button', { name: /^No tag \d+$/ })).toHaveCount(0)

    const rule = page.getByRole('article').first()
    await rule.getByRole('button', { name: 'Edit', exact: true }).first().click()
    const field = rule.getByRole('textbox', { name: 'interpretation' })
    await expect(field).toBeVisible()
    await expect(rule.getByRole('button', { name: 'Save as v2' })).toBeDisabled()
    await rule.getByRole('button', { name: 'Cancel', exact: true }).click()
    await expect(field).toHaveCount(0)
  })

  test('terminal: a shell runs a command and "Copy the last output" copies it', async ({ page, context, request }) => {
    let tmux = true
    try { execFileSync('tmux', ['-V'], { stdio: 'ignore' }) } catch { tmux = false }
    test.skip(!tmux, 'tmux is not on this machine')
    // The terminal answers only its own pages; a server on any port (this
    // one is not 8123) must trust its own origin — it once refused it.
    const own = new URL(test.info().project.use.baseURL!).origin
    const probe = await request.get('/api/terminal/state', { headers: { origin: own } })
    expect(probe.status(), `the server refused its own origin ${own}`).toBe(200)
    await context.grantPermissions(['clipboard-read', 'clipboard-write'])

    // The launcher offers a shell only in a project with a registered
    // folder; the fixtures have none. Register a throwaway one for a demo
    // project, writing nothing into it but the registry row.
    const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'sp-e2e-shell-'))
    const reg = await request.post('/api/setup/integrate', {
      data: {
        project_code: PROJECT, project_dir: dir,
        write_agents: false, write_claude_bridge: false, write_claude_hooks: false,
        write_opencode_plugin: false, write_codex_hooks: false, write_mcp: false,
      },
    })
    expect(reg.ok(), await reg.text()).toBeTruthy()
    const on = await request.post('/api/settings', { data: { values: { 'terminal.enabled': true } } })
    expect(on.ok()).toBeTruthy()

    try {
      await page.goto('/terminal')
      const launch = page.getByRole('button', { name: new RegExp(`^${PROJECT}`) })
      await expect(launch).toBeVisible()
      await launch.click()

      // On /terminal the page itself is the terminal: the launch lands in
      // this page's deck, and the drawer stays shut (once it opened over
      // the page too, the same terminal twice).
      const drawer = page
      const tab = page.getByRole('tablist', { name: 'Terminals' }).getByRole('tab', { name: new RegExp(PROJECT) })
      await expect(tab).toBeVisible()
      await expect(page.getByRole('region', { name: 'Terminal', exact: true })).toHaveCount(0)

      // xterm reads keys from its hidden textarea once the socket is up;
      // wait for the shell's prompt before typing. (.xterm-* are the
      // library's own classes: the screen has no role to find it by.)
      const screen = drawer.locator('.xterm-rows')
      await expect(screen).toContainText('$', { timeout: 10_000 })
      await drawer.getByRole('textbox', { name: 'Terminal input' }).focus()
      await page.keyboard.type("printf 'flow-%s\\n' 1 2 3")
      await page.keyboard.press('Enter')
      await expect(screen).toContainText('flow-3')

      await drawer.locator('.xterm-screen').click({ button: 'right' })
      await drawer.getByRole('menuitem', { name: 'Copy the last output' }).click()
      await expect.poll(() => page.evaluate(() => navigator.clipboard.readText()))
        .toMatch(/flow-1\s*\n\s*flow-2\s*\n\s*flow-3/)

      await tab.getByRole('button', { name: new RegExp(`^Close ${PROJECT}`) }).click()
      await expect(page.getByRole('tab', { name: new RegExp(PROJECT) })).toHaveCount(0)
    } finally {
      // Leave no shell behind, whatever happened above.
      const list = await request.get('/api/terminal/sessions').then((r) => r.json()).catch(() => ({}))
      for (const s of (list.sessions ?? []) as Array<{ id: string; state: string }>) {
        if (s.state !== 'ended') await request.post(`/api/terminal/sessions/${s.id}/close`, { data: { actor: 'operator' } }).catch(() => {})
      }
      await request.post('/api/settings', { data: { values: { 'terminal.enabled': false } } }).catch(() => {})
      fs.rmSync(dir, { recursive: true, force: true })
    }
  })
})
