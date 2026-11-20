import fs from 'node:fs'
import path from 'node:path'
import { _electron } from '@playwright/test'
import { test, expect, ELECTRON, PROJECT, ROOT, echoCalc, expectLine, fullSize, launchArgs, launchEnv, openShell, ready, sessionTab, sessions, typeLine, WINDOWS } from './fixtures'

/**
 * The tab strip of tk_a9306fb1 in the real window: the tab is titled by the
 * program in the terminal (OSC 0/2), held Alt shows each tab's facts, the
 * "+" list opens with Ctrl+click and a key picks, the status strip draws
 * its dots; by default each tab draws six dots, the chat's last six hours
 * (tk_d2e11125). A plain "+" opens a plain shell (tk_e7649e7c); the top
 * level shows the projects without terminals (tk_2ac8748d).
 */

/** A moment as the server reads it: local, naive ISO. */
const localIso = (d: Date) => {
  const p = (n: number) => String(n).padStart(2, '0')
  return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())}T${p(d.getHours())}:${p(d.getMinutes())}:${p(d.getSeconds())}`
}

/** `pwd`'s line for a folder: as given or with its links resolved. */
const pwdLine = (dir: string) => {
  const esc = (x: string) => x.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')
  return new RegExp(`^(${[dir, fs.realpathSync(dir)].map(esc).join('|')})$`)
}

const strip = (page: import('@playwright/test').Page) => page.getByRole('tablist', { name: 'Chats' })

test.describe('tab strip', () => {
  test('a program that sets the terminal title (OSC 2) names the tab', async ({ win, shell }) => {
    test.skip(WINDOWS, 'sh printf')
    const { page } = win
    await ready(page)
    const tab = strip(page).getByRole('tab').first()
    await expect(tab).toHaveAttribute('aria-label', new RegExp(`^${shell.label} `))
    // The printed line never holds the title itself: the name is joined by printf.
    await typeLine(page, "printf '\\033]2;sp-osc-%s\\007' named")
    // plain: xterm hears it at once; tmux: the server reads tmux's pane_title (polled every 5 s)
    await expect(tab).toHaveAttribute('aria-label', /^sp-osc-named /, { timeout: 15_000 })
    await expect(tab.locator('[data-tab-title]')).toHaveText('sp-osc-named')
  })

  test('held Alt shows the facts on each tab; releasing it brings the titles back', async ({ win, shell }) => {
    const { page } = win
    await ready(page)
    const tab = sessionTab(strip(page), shell.id)
    const title = tab.locator('[data-tab-title]')
    await expect(title).not.toBeEmpty()
    const originalTitle = await title.innerText()
    await page.keyboard.down('Alt')
    await expect(page.locator('[data-alt="b"]')).toHaveCount(1)
    await expect(page.getByRole('button', { name: `Close the tab ${originalTitle}` })).toBeVisible()
    await page.keyboard.up('Alt')
    await expect(page.locator('[data-alt="b"]')).toHaveCount(0)
    await expect(title).toHaveText(originalTitle)
  })

  test('tab groups stay inside their project and restore collapsed around the active session', async ({ win, shell, server }) => {
    const { page } = win
    await ready(page)
    const second = await openShell(server.api, 'e2e-group-second')
    await page.reload()
    const tabs = strip(page)
    const first = sessionTab(tabs, shell.id)
    const next = sessionTab(tabs, second.id)
    await first.click({ button: 'right' })
    await page.getByRole('menuitem', { name: /New group from this tab/ }).click()
    await page.getByRole('textbox', { name: 'Group name' }).fill('Release')
    await page.getByRole('button', { name: 'Make the group' }).click()
    const group = tabs.getByRole('group', { name: 'Release' })
    await expect(group.getByRole('tab')).toHaveCount(1)
    await next.click({ button: 'right' })
    await page.getByRole('menuitem', { name: 'Add to tab group Release' }).click()
    await expect(group.getByRole('tab')).toHaveCount(2)
    await expect(page.getByRole('button', { name: /^\+\d/ })).toHaveCount(0)

    await next.click()
    const fold = group.getByRole('button', { name: 'Release', exact: true })
    await fold.click()
    await expect(fold).toHaveAttribute('aria-current', 'true')
    await expect(tabs.getByRole('tab')).toHaveCount(0)
    await page.reload()
    await expect(fold).toHaveAttribute('aria-expanded', 'false')
    await expect(fold).toHaveAttribute('aria-current', 'true')
    await fold.click()
    await expect(next).toHaveAttribute('aria-selected', 'true')

    await group.getByRole('button', { name: 'Tab group settings: Release' }).click()
    await page.getByRole('textbox', { name: 'Group name' }).fill('Launch')
    await page.getByRole('button', { name: 'Save', exact: true }).click()
    const renamed = tabs.getByRole('group', { name: 'Launch' })
    await expect(renamed.getByRole('tab')).toHaveCount(2)
    await renamed.getByRole('button', { name: 'Tab group settings: Launch' }).click()
    await page.getByRole('menuitem', { name: 'Ungroup tabs' }).click()
    await expect(renamed).toHaveCount(0)
    await expect(tabs.getByRole('tab')).toHaveCount(2)
    await expect(next).toHaveAttribute('aria-selected', 'true')
  })

  test('Shift groups a visible range without switching the current terminal or taking hidden tabs', async ({ win, shell, server }) => {
    const { page } = win
    const hidden = await openShell(server.api, 'e2e-hidden')
    const middle = await openShell(server.api, 'e2e-middle')
    const last = await openShell(server.api, 'e2e-last')
    const hiddenName = `Hidden ${shell.id}`
    const rangeName = `Visible range ${shell.id}`
    const makeHidden = await server.api.post('/api/terminal/groups', { data: {
      name: hiddenName, project: PROJECT, tabs: [hidden.id],
    } })
    expect(makeHidden.ok(), await makeHidden.text()).toBeTruthy()
    await page.reload()
    const tabs = strip(page)
    const byId = (id: string) => tabs.locator(`[data-tab="${id}"] [role="tab"]`)
    const hiddenGroup = tabs.getByRole('group', { name: hiddenName, exact: true })
    const foldHidden = hiddenGroup.getByRole('button', { name: hiddenName, exact: true })
    await foldHidden.click()
    await byId(shell.id).click()
    await byId(last.id).click({ modifiers: ['Shift'] })
    await expect(tabs.locator('[data-group-selected="true"]')).toHaveCount(3)
    for (const id of [shell.id, middle.id, last.id]) {
      await expect(byId(id)).toHaveAttribute('data-group-selected', 'true')
    }
    await expect(byId(shell.id)).toHaveAttribute('aria-selected', 'true')
    await expect(byId(last.id)).toHaveAttribute('aria-selected', 'false')
    await expect(byId(hidden.id)).toHaveCount(0)

    await byId(last.id).press('Shift+F10')
    const menu = page.getByRole('menu', { name: 'Selected tabs' })
    await expect(menu.getByText('Selected tabs: 3', { exact: true })).toBeVisible()
    await menu.getByRole('menuitem', { name: /Group selected tabs/ }).click()
    await menu.getByRole('textbox', { name: 'Group name' }).fill(rangeName)
    await menu.getByRole('button', { name: 'Make the group' }).click()
    const grouped = tabs.getByRole('group', { name: rangeName, exact: true })
    await expect(grouped.getByRole('tab')).toHaveCount(3)
    for (const id of [shell.id, middle.id, last.id]) {
      await expect(grouped.locator(`[data-tab="${id}"] [role="tab"]`)).toBeVisible()
    }
    await expect(byId(shell.id)).toHaveAttribute('aria-selected', 'true')
    await expect(tabs.locator('[data-group-selected]')).toHaveCount(0)
    await foldHidden.click()
    await expect(hiddenGroup.locator(`[data-tab="${hidden.id}"] [role="tab"]`)).toBeVisible()
  })

  test('Ctrl+click on "+" opens the list; a key picks; Esc closes; the strip draws dots', async ({ win, shell, server }) => {
    const { page } = win
    await ready(page)
    // the dotted strip is the tab state «dots» now; «ритм» is the default
    await page.getByRole('button', { name: 'Window settings' }).click()
    const settings = page.getByRole('complementary', { name: 'Window settings' })
    await settings.getByText('Status strip on the tabs', { exact: true }).click()
    await page.getByRole('radio', { name: 'dots' }).click()
    await expect(page.locator('[data-tab] [data-strip="c"] [data-part]')).toHaveCount(3)
    await page.getByRole('radio', { name: 'rhythm' }).click()
    await expect(page.locator('[data-tab] [data-strip="c"]')).toHaveCount(0)
    await settings.getByRole('button', { name: 'Close window settings' }).click()
    const plus = page.getByRole('button', { name: 'New terminal', exact: true })
    await plus.click({ modifiers: ['Control'] })
    const menu = page.getByRole('menu', { name: 'Open a new terminal' })
    await expect(menu).toBeVisible()
    await expect(menu.getByRole('menuitem', { name: /^New chat in its own worktree/ })).toBeDisabled()
    await page.keyboard.press('Escape')
    await expect(menu).toHaveCount(0)

    await page.getByRole('button', { name: 'Choose what to open' }).click()
    await expect(menu).toBeVisible()
    // 1: a plain terminal (the agents' rows would start a real Claude Code in the sandbox)
    await page.keyboard.press('1')
    await expect(menu).toHaveCount(0)
    await expect(strip(page).getByRole('tab')).toHaveCount(2)
    await expect(strip(page).getByRole('tab', { name: new RegExp(`^${PROJECT} `) })).toHaveAttribute('aria-selected', 'true')
    await expect.poll(async () => (await sessions(server.api)).filter((s) => s.id !== shell.id).length).toBe(1)
  })

  test('Alt+N, Alt+/ and Ctrl+Shift+T open the controls and leave a working shell', async ({ win, shell, server }) => {
    const { app, page } = win
    await app.evaluate(({ BrowserWindow }) => { BrowserWindow.getAllWindows()[0].setSize(640, 500) })
    await expect.poll(() => page.evaluate(() => innerWidth)).toBe(640)
    await ready(page)
    const input = page.getByRole('textbox', { name: 'Terminal input' })
    await input.focus()
    await page.keyboard.press('Alt+KeyN')
    const menu = page.getByRole('menu', { name: 'Open a new terminal' })
    await expect(menu.getByRole('menuitem', { name: /^Plain terminal/ })).toBeVisible()
    await page.keyboard.press('Escape')
    await expect(menu).toHaveCount(0)

    await page.keyboard.press('Alt+Slash')
    const keys = page.getByRole('dialog', { name: 'Keys' })
    await expect(keys).toBeVisible()
    await page.keyboard.press('Escape')
    await expect(keys).toHaveCount(0)
    await expect(input).toBeFocused()

    await page.keyboard.press('ControlOrMeta+Shift+KeyT')
    const fresh = strip(page).getByRole('tab', { name: new RegExp(`^${PROJECT} `) })
    await expect(fresh).toHaveAttribute('aria-selected', 'true')
    await expect.poll(async () => (await sessions(server.api)).filter((s) => s.id !== shell.id).length).toBe(1)
    await ready(page)
    await expect(input).toBeFocused()
    await page.keyboard.type(echoCalc('new-shell-', '6*7'))
    await page.keyboard.press('Enter')
    await expectLine(page, 'new-shell-42')
  })

  test('Alt+W jumps to the waiting tab and the keyboard reaches that terminal', async ({ win, shell, server }) => {
    const { page } = win
    const waiting = await openShell(server.api, 'waiting-e2e')
    await page.route('**/api/terminal/sessions', async (route) => {
      if (route.request().method() !== 'GET') return route.continue()
      const response = await route.fetch()
      const data = await response.json()
      await route.fulfill({ response, json: {
        ...data,
        sessions: data.sessions.map((session: { id: string; state: string }) => session.id === waiting.id ? { ...session, state: 'waiting' } : session),
      } })
    })
    await page.reload()
    const byId = (id: string) => strip(page).locator(`[data-tab="${id}"]`).getByRole('tab')
    await byId(shell.id).click()
    await expect(byId(shell.id)).toHaveAttribute('aria-selected', 'true')
    await ready(page)
    await page.keyboard.press('Alt+KeyW')
    await expect(byId(waiting.id)).toHaveAttribute('aria-selected', 'true')
    await ready(page)
    await expect(page.getByRole('textbox', { name: 'Terminal input' })).toBeFocused()
    await page.keyboard.type(echoCalc('waiting-shell-', '6*7'))
    await page.keyboard.press('Enter')
    await expectLine(page, 'waiting-shell-42')
  })

  test('six dots on each tab: the chat\'s last six hours; work fills them, a full context warms them (tk_d2e11125)', async ({ win, shell }) => {
    const { page } = win
    await ready(page)
    const row = page.locator(`[data-tab="${shell.id}"] [data-tabstate="rhythm"]`)
    const dots = row.locator('[data-dot]')
    await expect(dots).toHaveCount(6)
    const values = async () => (await dots.evaluateAll((els) => els.map((e) => Number(e.getAttribute('data-v')))))
    // A chat started in this terminal (the capture hook's link), quiet so far.
    const aid = `cc-e2e-rhythm-${shell.id.slice(0, 8)}`
    const folder = path.join(ROOT, 'data', 'projects', PROJECT, 'chats', aid)
    fs.mkdirSync(folder, { recursive: true })
    const now = localIso(new Date())
    fs.writeFileSync(path.join(folder, 'meta.json'), JSON.stringify({
      agent_id: aid, agent_name: 'rhythm e2e', project: PROJECT, created_date: '2611-18', last_active: now,
      message_count: 0, tool: 'claude-code', cwd: path.join(ROOT, 'work', 'shell'), session_ref: `ref-${aid}`, terminal: shell.id,
    }))
    fs.writeFileSync(path.join(folder, 'chat.md'), `# Chat log — ${aid}\n*Started ${now}. Verbatim captured turns.*\n\n---\n`)
    await expect(row).toHaveAttribute('title', /quiet/, { timeout: 20_000 })
    expect(Math.max(...await values())).toBe(0)
    await expect(row).toHaveAttribute('data-warm', '0.00')
    // Ten turns this hour: twenty messages, two thirds of a full dot.
    fs.writeFileSync(path.join(folder, 'turns.jsonl'), Array.from({ length: 10 }, (_, i) => JSON.stringify({ turn: i + 1, start: now, end: now, source: 'hook' })).join('\n') + '\n')
    await expect.poll(async () => Math.max(...await values()), { timeout: 20_000 }).toBe(0.67)
    await expect(row).toHaveAttribute('title', /20 messages/)
    // Claude Code's status line: 92% of the context in use. The row warms past amber toward red.
    const usage = path.join(ROOT, 'data', '.usage', 'sessions')
    fs.mkdirSync(usage, { recursive: true })
    fs.writeFileSync(path.join(usage, `claude-code-ref-${aid}.json`), JSON.stringify({ at: now, context: { used_pct: 92, size: 200000 } }))
    await expect(row).toHaveAttribute('data-warm', '1.70', { timeout: 20_000 })
    await expect(row).toHaveAttribute('title', /Context 92%/)
    expect(await row.locator('[data-dot="0"]').getAttribute('data-k')).toBe('1.00')
  })

  test('a chat that waits for the operator over 5 minutes warms its six dots from the right (tk_d2e11125)', async ({ win, shell }) => {
    test.skip(WINDOWS, 'sh sleep')
    const { page } = win
    await ready(page)
    // An agent in the terminal that answered and waits: a program in front, its chat's last stop after the last message.
    const aid = `cc-e2e-wait-${shell.id.slice(0, 8)}`
    const folder = path.join(ROOT, 'data', 'projects', PROJECT, 'chats', aid)
    fs.mkdirSync(folder, { recursive: true })
    const now = new Date()
    fs.writeFileSync(path.join(folder, 'meta.json'), JSON.stringify({
      agent_id: aid, agent_name: 'wait e2e', project: PROJECT, created_date: '2611-18', last_active: localIso(new Date(now.getTime() - 60_000)),
      last_stop: { at: localIso(now) }, message_count: 0, tool: 'claude-code', cwd: path.join(ROOT, 'work', 'shell'), session_ref: `ref-${aid}`, terminal: shell.id,
    }))
    fs.writeFileSync(path.join(folder, 'chat.md'), `# Chat log — ${aid}\n\n---\n`)
    await typeLine(page, 'sleep 900')
    const row = page.locator(`[data-tab="${shell.id}"] [data-tabstate="rhythm"]`)
    await expect(page.locator(`[data-tab="${shell.id}"] [role="tab"]`)).toHaveAttribute('aria-label', /your turn/, { timeout: 20_000 })
    // Waited under a minute: calm.
    await expect(row).toHaveAttribute('data-warm', '0.00')
    // The page's clock 15 minutes on (the server's stays): the wait is 15 minutes, past amber toward red.
    await page.clock.install({ time: Date.now() + 15 * 60_000 })
    await page.reload()
    await expect(row).toHaveAttribute('data-warm', /^1\.[4-6]\d$/, { timeout: 20_000 })
    expect(await row.locator('[data-dot="0"]').getAttribute('data-k')).toBe('1.00')
    await expect(row).toHaveAttribute('title', /Waits for your answer 1[456] min/)
  })

  test('a workspace opens on the tab last in front there, not its first (tk_f7a924a6)', async ({ win, shell, server }) => {
    const { page } = win
    const other = 'beta-e2e'
    const dir = path.join(server.dir, '..', other)
    fs.mkdirSync(dir, { recursive: true })
    const reg = await server.api.post('/api/setup/integrate', { data: {
      project_code: other, project_dir: dir, write_agents: false, write_claude_bridge: false, write_claude_hooks: false,
      write_opencode_plugin: false, write_codex_hooks: false, write_mcp: false,
    } })
    expect(reg.ok(), await reg.text()).toBeTruthy()
    const second = await openShell(server.api, 'e2e-second')
    const r = await server.api.post('/api/terminal/sessions', { data: { kind: 'shell', project: other, label: 'e2e-beta', role: 'shell' } })
    expect(r.ok(), await r.text()).toBeTruthy()
    await page.reload()
    const { session: beta } = await r.json() as { session: { id: string } }
    // into PROJECT through the folded workspaces if the window opened on the other one
    const tabs = strip(page)
    await expect(tabs.getByRole('tab').first()).toBeVisible()
    const go = async (code: string) => {
      await page.getByRole('button', { name: /^\+\d/ }).click()
      await page.getByRole('menuitem', { name: new RegExp(code) }).click()
    }
    const first = sessionTab(tabs, shell.id)
    const next = sessionTab(tabs, second.id)
    if (!(await first.count())) await go(PROJECT)
    await next.click()
    await expect(next).toHaveAttribute('aria-selected', 'true')
    await go(other)
    await expect(sessionTab(tabs, beta.id)).toHaveAttribute('aria-selected', 'true')
    await go(PROJECT)
    await expect(next).toHaveAttribute('aria-selected', 'true')
    await expect(first).toHaveAttribute('aria-selected', 'false')
  })

  test('the workspace picked in the sidebar stays active after quitting and reopening the window', async ({ win, shell, server }) => {
    const { app, page, userData } = win
    const other = 'restart-e2e'
    const dir = path.join(server.dir, '..', other)
    fs.mkdirSync(dir, { recursive: true })
    const reg = await server.api.post('/api/setup/integrate', { data: {
      project_code: other, project_dir: dir, write_agents: false, write_claude_bridge: false, write_claude_hooks: false,
      write_opencode_plugin: false, write_codex_hooks: false, write_mcp: false,
    } })
    expect(reg.ok(), await reg.text()).toBeTruthy()
    const r = await server.api.post('/api/terminal/sessions', { data: { kind: 'shell', project: other, label: 'e2e-restart-project', role: 'shell' } })
    expect(r.ok(), await r.text()).toBeTruthy()

    await page.reload()
    const tabs = strip(page)
    const { session: target } = await r.json() as { session: { id: string } }
    const current = sessionTab(tabs, shell.id)
    await page.getByRole('button', { name: 'Left sidebar', exact: true }).click()
    const workspaces = page.getByRole('navigation', { name: 'Workspaces' })
    await workspaces.getByRole('button', { name: new RegExp(`^${PROJECT} `) }).click()
    // Save an explicit tab selection in the first project, then switch by
    // project name alone. The older tab selection must not win at startup.
    await current.click()
    await workspaces.getByRole('button', { name: new RegExp(`^${other} `) }).click()
    await expect(sessionTab(tabs, target.id)).toHaveAttribute('aria-selected', 'true')

    await app.close()
    const reopened = await _electron.launch({ executablePath: ELECTRON, args: launchArgs(userData), env: launchEnv(), timeout: 30_000 })
    try {
      const restarted = await reopened.firstWindow()
      await expect(sessionTab(strip(restarted), target.id)).toHaveAttribute('aria-selected', 'true')
    } finally {
      await reopened.close()
    }
  })

  test('the selected far-right tab is visible in an overflowing strip after reload', async ({ win, server, shell }) => {
    const { app, page } = win
    await fullSize(app, page)
    for (let i = 1; i <= 7; i++) await openShell(server.api, `e2e wide terminal label for tab number ${i}`)
    // Use a shell for the test process, with the same row identity as a Codex chat.
    const r = await server.api.post('/api/terminal/sessions', { data: {
      kind: 'shell', project: PROJECT, role: 'chat', agent: 'codex-e2e-rightmost', label: 'e2e Codex chat at the far right',
    } })
    expect(r.ok(), await r.text()).toBeTruthy()
    const { session: last } = await r.json() as { session: { id: string } }
    await page.reload()
    const tabs = strip(page)
    await expect(tabs.getByRole('tab')).toHaveCount(9)
    await expect(tabs.getByRole('tab').last()).toHaveAttribute('aria-label', /^e2e Codex chat at the far right /)
    await expect.poll(() => tabs.evaluate((el) => el.scrollWidth > el.clientWidth), { message: 'the strip overflows horizontally' }).toBe(true)
    const first = tabs.getByRole('tab').first()
    await first.click()
    await expect(first).toHaveAttribute('aria-selected', 'true')
    const chat = tabs.locator(`[data-tab="${last.id}"]`).getByRole('tab')
    await expect.poll(() => chat.evaluate((button) => button.getBoundingClientRect().width <= button.closest('[role="tablist"]')!.clientWidth),
      { message: 'the strip is wide enough to show one whole tab' }).toBe(true)
    // Before these keys stayed local, boot could save its first view to the
    // server and later overwrite the operator's most recent selection with it.
    const stale = await server.api.post('/api/prefs', { data: { values: {
      'sp-aqua-active': shell.id, 'sp-aqua-ws-tabs': JSON.stringify({ [`p:${PROJECT}`]: shell.id }),
    } } })
    expect(stale.ok(), await stale.text()).toBeTruthy()
    try {
      await chat.click()
      await expect(chat).toHaveAttribute('aria-selected', 'true')

      await page.reload()
      await expect(chat).toHaveAttribute('aria-selected', 'true')
      await expect.poll(() => chat.evaluate((button) => {
        const tab = button.getBoundingClientRect()
        const view = button.closest('[role="tablist"]')!.getBoundingClientRect()
        const visible = Math.max(0, Math.min(tab.right, view.right) - Math.max(tab.left, view.left))
        return Math.round(100 * visible / tab.width)
      }), { message: 'the active tab fits horizontally inside the strip' }).toBeGreaterThanOrEqual(95)
    } finally {
      const cleared = await server.api.post('/api/prefs', { data: { values: { 'sp-aqua-active': null, 'sp-aqua-ws-tabs': null } } })
      expect(cleared.ok(), await cleared.text()).toBeTruthy()
    }
  })

  test('a plain "+" opens a shell in the project, no agent (tk_e7649e7c)', async ({ win, shell, server }) => {
    const { page } = win
    test.skip(WINDOWS, 'sh pwd')
    await ready(page)
    await page.getByRole('button', { name: 'New terminal', exact: true }).click()
    await expect(page.getByRole('menu', { name: 'Open a new terminal' })).toHaveCount(0)
    await expect(strip(page).getByRole('tab')).toHaveCount(2)
    await expect(strip(page).getByRole('tab', { name: new RegExp(`^${PROJECT} `) })).toHaveAttribute('aria-selected', 'true')
    await ready(page)
    const fresh = (await sessions(server.api)).filter((s) => s.id !== shell.id)
    expect(fresh).toHaveLength(1)
    const row = (await (await server.api.get('/api/terminal/sessions')).json()).sessions.find((s: { id: string }) => s.id === fresh[0]!.id) as { command: string; role: string }
    expect(row.command).toBe('')
    expect(row.role).toBe('shell')
    await typeLine(page, 'pwd')
    await expectLine(page, pwdLine(server.dir))
  })
})

test.describe('every workspace (tk_2ac8748d)', () => {
  test('a project without terminals has a tile; its «New terminal» opens a shell in its folder', async ({ win, shell: _shell, server }) => {
    test.skip(WINDOWS, 'sh pwd')
    const { page } = win
    const quiet = 'gamma-e2e'
    const dir = path.join(server.dir, '..', quiet)
    fs.mkdirSync(dir, { recursive: true })
    const reg = await server.api.post('/api/setup/integrate', { data: {
      project_code: quiet, project_dir: dir, write_agents: false, write_claude_bridge: false, write_claude_hooks: false,
      write_opencode_plugin: false, write_codex_hooks: false, write_mcp: false,
    } })
    expect(reg.ok(), await reg.text()).toBeTruthy()
    await page.reload()
    await ready(page)
    await page.keyboard.press('ControlOrMeta+Shift+ArrowUp')
    await page.keyboard.press('ControlOrMeta+Shift+ArrowUp')
    await expect(page.locator('[data-level="all"]')).toHaveCount(1)
    const tile = page.getByRole('region', { name: quiet, exact: true })
    await expect(tile).toBeVisible()
    await expect(tile).toContainText('no terminals')
    await expect(page.getByRole('region', { name: 'New workspace' })).toBeVisible()
    await tile.getByRole('button', { name: 'New terminal' }).click()
    await expect(page.locator('[data-level="chat"]')).toHaveCount(1)
    await expect(strip(page).getByRole('tab', { name: new RegExp(`^${quiet} `) })).toHaveAttribute('aria-selected', 'true')
    await ready(page)
    await typeLine(page, 'pwd')
    await expectLine(page, pwdLine(dir))
  })
})
