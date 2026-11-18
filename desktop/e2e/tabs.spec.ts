import fs from 'node:fs'
import path from 'node:path'
import { test, expect, PROJECT, ROOT, expectLine, openShell, ready, sessions, typeLine, WINDOWS } from './fixtures'

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
    const tab = strip(page).getByRole('tab').first()
    await expect(tab.locator('[data-tab-title]')).toHaveText(shell.label)
    await page.keyboard.down('Alt')
    await expect(page.locator('[data-alt="b"]')).toHaveCount(1)
    await expect(page.getByRole('button', { name: `Close the tab ${shell.label}` })).toBeVisible()
    await page.keyboard.up('Alt')
    await expect(page.locator('[data-alt="b"]')).toHaveCount(0)
    await expect(tab.locator('[data-tab-title]')).toHaveText(shell.label)
  })

  test('Ctrl+click on "+" opens the list; a key picks; Esc closes; the strip draws dots', async ({ win, shell, server }) => {
    const { page } = win
    await ready(page)
    // the dotted strip is the tab state «dots» now; «ритм» is the default
    await page.getByRole('button', { name: 'Status strip on the tabs' }).click()
    await page.getByRole('radio', { name: 'dots' }).click()
    await expect(page.locator('[data-tab] [data-strip="c"] [data-part]')).toHaveCount(3)
    await page.getByRole('radio', { name: 'rhythm' }).click()
    await expect(page.locator('[data-tab] [data-strip="c"]')).toHaveCount(0)
    await page.keyboard.press('Escape')
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
    // into PROJECT through the folded workspaces if the window opened on the other one
    const tabs = strip(page)
    await expect(tabs.getByRole('tab').first()).toBeVisible()
    const go = async (code: string) => {
      await page.getByRole('button', { name: /^\+\d/ }).click()
      await page.getByRole('menuitem', { name: new RegExp(code) }).click()
    }
    if (!(await tabs.getByRole('tab', { name: new RegExp(`^${shell.label} `) }).count())) await go(PROJECT)
    await tabs.getByRole('tab', { name: new RegExp(`^${second.label} `) }).click()
    await expect(tabs.getByRole('tab', { name: new RegExp(`^${second.label} `) })).toHaveAttribute('aria-selected', 'true')
    await go(other)
    await expect(tabs.getByRole('tab', { name: /^e2e-beta / })).toHaveAttribute('aria-selected', 'true')
    await go(PROJECT)
    await expect(tabs.getByRole('tab', { name: new RegExp(`^${second.label} `) })).toHaveAttribute('aria-selected', 'true')
    await expect(tabs.getByRole('tab', { name: new RegExp(`^${shell.label} `) })).toHaveAttribute('aria-selected', 'false')
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
