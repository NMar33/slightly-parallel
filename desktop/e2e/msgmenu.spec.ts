import { execFileSync } from 'node:child_process'
import fs from 'node:fs'
import path from 'node:path'
import type { APIRequestContext, Page } from '@playwright/test'
import { test, expect, ROOT, PROJECT, URL_, WINDOWS, echoCalc, expectClickTarget, expectLine, expectTerminalAncestorsUnscrolled, fullSize, lines, printFile, ready, sessions, typeLine } from './fixtures'

/**
 * The message menu on the real terminal (tk_a9306fb1, variant b «list»).
 *
 * A chat is recorded the way the capture hook records one — its own CLI
 * (scripts/hooks/capture-cli.py) writes the turns into the sandbox's data
 * root, tied to the test's terminal by SP_TERMINAL, as a Claude Code
 * started in that terminal would be. The terminal then prints the same
 * conversation as Claude Code draws it ("❯ " the operator, "● " the agent,
 * "✻ " a status line, wrapped by hand). Then, in the window:
 * - a right click on a row of the agent's reply opens the list for that
 *   reply; Pin pins it, the pin is in the right sidebar's Pins and its mark
 *   on the reply's first row; tmux never draws its own pane menu;
 * - a click on the task id opens its menu and then its card;
 * - a click on the note id opens the note, Escape closes it;
 * - a right click on a row that is no message offers Copy only and says so.
 * It runs in tmux and plain terminals (SP_E2E_KEEP=plain).
 */

const REPO = path.resolve(__dirname, '..', '..')
const PYTHON = path.join(REPO, 'backend', '.venv', WINDOWS ? 'Scripts/python.exe' : 'bin/python')
const CAPTURE = path.join(REPO, 'scripts', 'hooks', 'capture-cli.py')
/** A chat of its own per run: the same server keeps the last run's turns and pins (--repeat-each, a retry). */
let AGENT = 'cc-e2emenu1'

/** One turn recorded by the capture hook's CLI, as a chat started in terminal `sid`. */
function record(sid: string, phase: 'open' | 'complete', text: string) {
  execFileSync(PYTHON, [CAPTURE, '--phase', phase, '--project', PROJECT, '--data-root', path.join(ROOT, 'data'), '--agent', AGENT,
    '--text-stdin', ...(phase === 'open' ? ['--tool', 'claude-code', '--session', `e2e-session-${AGENT}`, '--cwd', path.join(ROOT, 'work', 'shell')] : [])],
  { input: text, env: { ...process.env, SP_TERMINAL: sid, SP_PORT: new URL(URL_).port }, stdio: ['pipe', 'ignore', 'inherit'] })
}

async function madeTask(api: APIRequestContext): Promise<string> {
  const r = await api.post('/api/tasks', { data: {
    project: PROJECT, projects: PROJECT, agent_id: 'operator', actor: 'operator', created_date: '2611-18', created_time: '10:00',
    title: 'Message menu in the terminal', description: 'A right click on a message.', status: 'doing', priority: 'med', lane: 'unassigned',
  } })
  expect(r.ok(), await r.text()).toBeTruthy()
  return (await r.json()).metadata.id as string
}

async function madeNote(api: APIRequestContext): Promise<string> {
  // A note is an agent's write, through the MCP tool: the header it sends.
  const r = await api.post('/api/notes/write', {
    headers: { 'x-sp-via': 'mcp' },
    data: { agent_id: AGENT, project: PROJECT, kind: 'report', title: 'How a click finds its message', text: '# How a click finds its message\n\nBy its text, and by the turn above it.\n\n- [ ] read it in place' },
  })
  expect(r.ok(), await r.text()).toBeTruthy()
  return (await r.json()).id as string
}

/** The middle of `text` on the screen (xterm's DOM rows), in page pixels. */
async function pointOf(page: Page, text: string): Promise<{ x: number; y: number }> {
  let got: { x: number; y: number } | null = null
  await expect.poll(async () => {
    got = await page.evaluate((want) => {
      for (const row of document.querySelectorAll('.aqua-screen .xterm-rows > div')) {
        const all = (row.textContent ?? '').replace(/ /g, ' ')
        const at = all.indexOf(want)
        if (at < 0) continue
        // The text nodes of the row, to put a range exactly on the words.
        const walk = document.createTreeWalker(row, NodeFilter.SHOW_TEXT)
        let seen = 0
        const range = document.createRange()
        let started = false
        for (let n = walk.nextNode(); n; n = walk.nextNode()) {
          const len = n.textContent!.length
          if (!started && at < seen + len) { range.setStart(n, at - seen); started = true }
          if (started && at + want.length <= seen + len) { range.setEnd(n, at + want.length - seen); break }
          seen += len
        }
        const r = range.getBoundingClientRect()
        return { x: r.left + r.width / 2, y: r.top + r.height / 2 }
      }
      return null
    }, text)
    return got !== null
  }, { message: `"${text}" on the screen` }).toBe(true)
  return got!
}

test.describe('message menu', () => {
  test.beforeEach(() => { AGENT = `cc-e2em${Math.random().toString(16).slice(2, 6)}` })
  test('the inspector previews long replies in Messages and Pins and lets them expand', async ({ win, shell, server }) => {
    const { app, page } = win
    const ending = 'End of the full inspector reply.'
    const reply = [
      ...Array.from({ length: 12 }, (_, n) => `Paragraph ${n + 1} stays readable in a narrow inspector, including all the text on this line.`),
      'long-unbroken-token-'.repeat(50),
      ending,
    ].join('\n')
    record(shell.id, 'open', 'Check the inspector readability')
    record(shell.id, 'complete', reply)
    await expect.poll(async () => (await sessions(server.api)).find((s) => s.id === shell.id && (s as { agent_id?: string }).agent_id === AGENT)).toBeTruthy()
    // The terminal binding can be visible before the chat index serves the reply.
    await expect.poll(async () => {
      const listed = await server.api.get(`/api/sessions?agent_id=${AGENT}`)
      expect(listed.ok()).toBe(true)
      const { sessions: chats } = await listed.json() as { sessions: { id: string }[] }
      if (!chats.length) return false
      const ids = chats.map((chat) => chat.id).join(',')
      const response = await server.api.get(`/api/sessions/turns?ids=${encodeURIComponent(ids)}`)
      expect(response.ok()).toBe(true)
      const { turns } = await response.json() as { turns: Record<string, { agent: string }[]> }
      return Object.values(turns).flat().some((turn) => turn.agent.endsWith(ending))
    }, { timeout: 15_000, message: 'the complete reply is available in the chat index' }).toBe(true)
    await page.reload()
    await fullSize(app, page)
    await ready(page)
    await page.keyboard.press('Alt+BracketRight')
    const side = page.getByRole('complementary', { name: 'Right sidebar' })
    const fullText = side.getByText(ending, { exact: false }).first()
    const fits = () => fullText.evaluate((el) => el.scrollHeight <= el.clientHeight + 1 && el.scrollWidth <= el.clientWidth + 1)
    const verifyPreview = async () => {
      const expand = side.getByRole('button', { name: 'Expand message' }).first()
      await expect(expand).toHaveAttribute('aria-expanded', 'false')
      await expect.poll(fits).toBe(false)
      await expand.click()
      await expect.poll(fits).toBe(true)
      const collapse = side.getByRole('button', { name: 'Collapse message' }).first()
      await expect(collapse).toHaveAttribute('aria-expanded', 'true')
      await collapse.click()
      await expect.poll(fits).toBe(false)
    }
    await expect(fullText).toBeVisible()
    await verifyPreview()
    await side.getByRole('button', { name: 'Pin this reply, to come back to it' }).click()
    await side.getByRole('tab', { name: 'Pins' }).click()
    await expect(fullText).toBeVisible()
    await verifyPreview()
  })
  for (const size of ['usual', 'narrow'] as const) test(`a right click on a reply in a ${size} window: Pin, task and note ids; Copy only on a line that is no message`, async ({ win, shell, server }) => {
    const { app, page } = win
    await ready(page)
    if (size === 'narrow') {
      await app.evaluate(({ BrowserWindow }) => { BrowserWindow.getAllWindows()[0].setSize(640, 270) })
      await expect.poll(() => page.evaluate(() => innerWidth)).toBe(640)
      await expect.poll(() => page.evaluate(() => innerHeight)).toBe(270)
    } else {
      await fullSize(app, page)
    }

    // The chat: a task and a note the reply names, and the turn the hook records.
    const task = await madeTask(server.api)
    const question = 'make the login test pass on macOS: the host name is long and the line wraps'
    record(shell.id, 'open', question)
    const note = await madeNote(server.api)
    const reply = `The test counted rows in the joined text, and the long host name wrapped the command onto a second row. It now waits for the whole line. Card ${task}, note ${note}.`
    record(shell.id, 'complete', reply)
    await expect.poll(async () => (await sessions(server.api)).find((s) => s.id === shell.id && (s as { agent_id?: string }).agent_id === AGENT), { timeout: 15_000, message: 'the terminal tied to the recorded chat' }).toBeTruthy()
    await expect.poll(async () => ((await (await server.api.get(`/api/sessions?agent_id=${AGENT}`)).json()).sessions ?? []).length, { timeout: 15_000, message: 'the chat in the record' }).toBeGreaterThan(0)

    // The conversation as Claude Code draws it, printed into the terminal.
    const file = path.join(server.dir, 'chat.txt')
    fs.writeFileSync(file, [
      '❯ make the login test pass on macOS: the host name is long and',
      '  the line wraps',
      '',
      '● Read(desktop/e2e/terminals.spec.ts)',
      '  ⎿  Read 134 lines',
      '',
      '● The test counted rows in the joined text, and the long host',
      '  name wrapped the command onto a second row. It now waits for',
      `  the whole line. Card ${task}, note ${note}.`,
      '',
      '✻ Worked for 42s',
      'plain shell output, no chat here',
      '',
    ].join('\n'))
    await typeLine(page, printFile(file))
    await expectLine(page, 'plain shell output, no chat here')

    // 1. The reply: its list, then Pin.
    const p = await pointOf(page, 'name wrapped the command onto a second row')
    const menu = page.getByRole('menu', { name: 'Agent\'s reply · 1' })
    // The window learns the terminal's chat on its next read of the terminals (every 2 s):
    // until then the right click is the screen's own menu.
    await expect.poll(async () => {
      await expectClickTarget(page.locator('.aqua-screen'), p)
      await page.mouse.click(p.x, p.y, { button: 'right' })
      if (await menu.waitFor({ state: 'visible', timeout: 2000 }).then(() => true, () => false)) return true
      await page.keyboard.press('Escape')
      return false
    }, { timeout: 20_000, intervals: [500], message: 'the list for the reply' }).toBe(true)
    await expectTerminalAncestorsUnscrolled(page)
    if (size === 'narrow') {
      await expect.poll(() => menu.evaluate((element) => {
        const { top, bottom, left, right } = element.getBoundingClientRect()
        return top >= 0 && left >= 0 && bottom <= innerHeight && right <= innerWidth
      })).toBe(true)
      const box = (await menu.boundingBox())!
      await page.mouse.move(box.x + box.width / 2, box.y + box.height / 2)
      await page.mouse.wheel(0, 600)
      await expect.poll(() => menu.evaluate((element) => element.scrollTop)).toBeGreaterThan(0)
      await expect(menu.getByRole('menuitem', { name: 'Terminal menu…' })).toBeInViewport()
      await page.mouse.wheel(0, -600)
      await expect.poll(() => menu.evaluate((element) => element.scrollTop)).toBe(0)
    }
    for (const name of ['Pin', 'Hand over later', 'Branch into a new window', 'Make a task', 'Copy', 'Terminal menu…']) await expect(menu.getByRole('menuitem', { name })).toBeVisible()
    await expect(menu.getByRole('menuitemradio', { name: 'Carry after compaction: word for word' })).toBeVisible()
    // tmux drew no pane menu of its own under ours.
    expect((await lines(page)).join('\n')).not.toMatch(/Horizontal Split|Swap Up|Kill/)
    await menu.getByRole('menuitem', { name: 'Pin' }).click()
    await expect(page.getByRole('status').filter({ hasText: 'Message pinned' })).toBeVisible()
    await expect.poll(async () => ((await (await server.api.get(`/api/pins?agent_id=${AGENT}`)).json()).items ?? []).map((m: { target: string }) => m.target)).toEqual([`${AGENT}#1/reply`])
    if (size === 'narrow') {
      await app.evaluate(({ BrowserWindow }) => { BrowserWindow.getAllWindows()[0].setSize(640, 500) })
      await expect.poll(() => page.evaluate(() => innerHeight)).toBe(500)
    }
    // The mark on the reply's first row, and the pin in the right sidebar.
    await expect(page.locator('.mm-marks', { hasText: 'pinned' })).toHaveAttribute('data-target', `${AGENT}#1/reply`, { timeout: 10_000 })
    await page.keyboard.press('Alt+BracketRight')
    const side = page.getByRole('complementary', { name: 'Right sidebar' })
    await side.getByRole('tab', { name: 'Pins' }).click()
    await expect(side.getByText('pinned · 1↩')).toBeVisible()
    await expect(side.getByText(/^The test counted rows in the joined text/).first()).toBeVisible()
    await page.keyboard.press('Alt+BracketRight')
    await expect(side).toHaveCount(0)

    // 2. The task id: its menu, then its card.
    const t = await pointOf(page, task)
    await expectClickTarget(page.locator('.aqua-screen'), t)
    await page.mouse.click(t.x, t.y)
    const tmenu = page.getByRole('menu', { name: task })
    await expect(tmenu.getByText('Message menu in the terminal')).toBeVisible()
    await expect(tmenu.getByRole('menuitemradio', { name: 'doing' })).toHaveAttribute('aria-checked', 'true')
    await tmenu.getByRole('menuitem', { name: 'Open the task' }).click()
    const card = page.getByRole('dialog', { name: `Task ${task}` })
    await expect(card.getByText('A right click on a message.')).toBeVisible()
    await page.keyboard.press('Escape')
    await expect(card).toHaveCount(0)

    // 3. The note id: read and comment in place; Escape closes it.
    const n = await pointOf(page, note)
    await expectClickTarget(page.locator('.aqua-screen'), n)
    await page.mouse.click(n.x, n.y)
    const nd = page.getByRole('dialog', { name: `Note ${note}` })
    await expect(nd.getByRole('heading', { name: 'How a click finds its message' }).first()).toBeVisible()
    await nd.getByRole('button', { name: 'Comment on: read it in place' }).click()
    await nd.getByRole('textbox', { name: 'Comment' }).pressSequentially('Keep this linked to the current chat.')
    await nd.getByRole('button', { name: 'Send comment' }).click()
    await expect(nd.getByRole('paragraph').filter({ hasText: 'Keep this linked to the current chat.' })).toBeVisible()
    await expect(nd.getByRole('checkbox', { name: 'read it in place' })).not.toBeChecked()
    await page.keyboard.press('Escape')
    await expect(nd).toHaveCount(0)

    // 4. A line that is no message: Copy only, and it says so.
    const o = await pointOf(page, 'plain shell output, no chat here')
    await expectClickTarget(page.locator('.aqua-screen'), o)
    await page.mouse.click(o.x, o.y, { button: 'right' })
    const none = page.getByRole('menu', { name: 'Message not found in the chat record' })
    await expect(none).toBeVisible()
    await expect(none.getByRole('menuitem')).toHaveText(['Copy', 'Terminal menu…'])
    await page.keyboard.press('Escape')
    await expect(none).toHaveCount(0)

    await expect(page.getByRole('textbox', { name: 'Terminal input' })).toBeFocused()
    await page.keyboard.type(echoCalc('menu-', '40+2', '-done'))
    await page.keyboard.press('Enter')
    await expectLine(page, 'menu-42-done')
  })
})
