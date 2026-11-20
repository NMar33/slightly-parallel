import { execFileSync } from 'node:child_process'
import fs from 'node:fs'
import path from 'node:path'
import type { ElectronApplication, Page } from '@playwright/test'
import { test, expect, ROOT, PROJECT, URL_, WINDOWS, expectLine, fullSize, lines, ready, sessions, typeLine } from './fixtures'

/**
 * Commands in an agent's reply, copied from the terminal (tk_29b870f1).
 *
 * A chat is recorded through the capture hook's CLI, tied to the test's
 * terminal (as in msgmenu.spec.ts); its reply is markdown with a fenced
 * command (`! echo …`, the operator's case), an inline `git status`, a
 * two-line block and a file name. The terminal then prints the reply as
 * Claude Code draws it: no fences, no backticks. In the window:
 * - over the command's row a copy icon shows; a click copies the command
 *   (read with Electron's clipboard) without its `! `;
 * - a right click on it: «Copy the command» (no `! `), «Copy for Claude
 *   Code» (with `! `), «Paste into the terminal»: the command on the prompt
 *   exactly once, not run (its output is not printed) until Enter;
 * - the two-line block copies whole; it is not pasted into a shell that
 *   would run its lines at once (sh asks for no bracketed paste);
 * - the inline command copies; the file name's row offers no command.
 * It runs in tmux and plain terminals (SP_E2E_KEEP=plain).
 */

const REPO = path.resolve(__dirname, '..', '..')
const PYTHON = path.join(REPO, 'backend', '.venv', 'bin', 'python')
const CAPTURE = path.join(REPO, 'scripts', 'hooks', 'capture-cli.py')
const AGENT = 'cc-e2ecmd01'

function record(sid: string, phase: 'open' | 'complete', text: string) {
  execFileSync(PYTHON, [CAPTURE, '--phase', phase, '--project', PROJECT, '--data-root', path.join(ROOT, 'data'), '--agent', AGENT,
    '--text-stdin', ...(phase === 'open' ? ['--tool', 'claude-code', '--session', 'e2e-session-cmd', '--cwd', path.join(ROOT, 'work', 'shell')] : [])],
  { input: text, env: { ...process.env, SP_TERMINAL: sid, SP_PORT: new URL(URL_).port }, stdio: ['pipe', 'ignore', 'inherit'] })
}

/** The middle of `text` on the screen (the last row that holds it), in page pixels. */
async function pointOf(page: Page, text: string, last = false): Promise<{ x: number; y: number }> {
  let got: { x: number; y: number } | null = null
  await expect.poll(async () => {
    got = await page.evaluate(([want, fromEnd]) => {
      const rows = [...document.querySelectorAll('.aqua-screen .xterm-rows > div')]
      if (fromEnd) rows.reverse()
      for (const row of rows) {
        const all = (row.textContent ?? '').replace(/ /g, ' ')
        const at = all.indexOf(want)
        if (at < 0) continue
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
    }, [text, last] as const)
    return got !== null
  }, { message: `"${text}" on the screen` }).toBe(true)
  return got!
}

const clipboard = (app: ElectronApplication) => app.evaluate(({ clipboard }) => clipboard.readText())

/** A row with the prompt written as `$ `: macOS's sh (bash) prints `host:dir user$ `, Linux's `$ `. */
const prompted = (l: string) => l.trim().replace(/^[^$]*\$ /, '$ ')

const CMD = 'echo cmd-$((40+2))-ran'
const REPLY = [
  'Поставь так:',
  '',
  '```',
  `! ${CMD}`,
  '```',
  '',
  'Потом `git status` и:',
  '',
  '```bash',
  'cd /tmp',
  'echo two-$((1+1))',
  '```',
  '',
  'Файл `README.md` не трогай.',
].join('\n')

test.describe('commands in a reply', () => {
  test.skip(WINDOWS, 'the printed conversation and commands require a Unix shell')

  test('the copy icon, the right-click items, a paste that arrives once and does not run; a file name is no command', async ({ win, shell, server }) => {
    const { app, page } = win
    await ready(page)
    // The reply is drawn for a terminal taller than headless's 420×240 window.
    await fullSize(app, page)

    record(shell.id, 'open', 'как поднять лимит')
    record(shell.id, 'complete', REPLY)
    await expect.poll(async () => (await sessions(server.api)).find((s) => s.id === shell.id && (s as { agent_id?: string }).agent_id === AGENT), { timeout: 15_000, message: 'the terminal tied to the recorded chat' }).toBeTruthy()

    // The reply as Claude Code draws it.
    const file = path.join(server.dir, 'cmd-chat.txt')
    fs.writeFileSync(file, [
      '❯ как поднять лимит',
      '',
      '● Поставь так:',
      '',
      `    ! ${CMD}`,
      '',
      '  Потом git status и:',
      '',
      '    cd /tmp',
      '    echo two-$((1+1))',
      '',
      '  Файл README.md не трогай.',
      '',
      '✻ Worked for 3s',
      '',
    ].join('\n'))
    await typeLine(page, `cat '${file}'`)
    await expectLine(page, '✻ Worked for 3s')

    // The window learns the terminal's chat on its next read of the terminals: until then a right click is the screen's.
    let p = await pointOf(page, CMD)
    // (Its turn's number: 1, or more when the test runs again on the same server.)
    const menu = page.getByRole('menu', { name: /^Agent's reply · \d+$/ })
    await expect.poll(async () => {
      await page.mouse.click(p.x, p.y, { button: 'right' })
      if (await menu.waitFor({ state: 'visible', timeout: 2000 }).then(() => true, () => false)) return true
      await page.keyboard.press('Escape')
      return false
    }, { timeout: 20_000, intervals: [500], message: 'the list for the reply' }).toBe(true)
    // The command's items first, above the message's.
    await expect(menu.getByRole('menuitem').first()).toHaveText('Copy the command')
    await expect(menu.getByRole('menuitem').nth(1)).toHaveText('Copy for Claude Code')
    await expect(menu.getByRole('menuitem').nth(2)).toHaveText('Paste into the terminal')
    await expect(menu.getByRole('menuitem', { name: 'Pin' })).toBeVisible()
    // tmux drew no pane menu of its own under ours.
    expect((await lines(page)).join('\n')).not.toMatch(/Horizontal Split|Swap Up|Kill/)
    await app.evaluate(({ clipboard }) => clipboard.writeText('nothing yet'))
    await menu.getByRole('menuitem', { name: 'Copy the command' }).click()
    await expect.poll(() => clipboard(app)).toBe(CMD)

    // The window's bottom line ("copied") may move the screen: where the command is now.
    p = await pointOf(page, CMD)
    await page.mouse.click(p.x, p.y, { button: 'right' })
    await menu.getByRole('menuitem', { name: 'Copy for Claude Code' }).click()
    await expect.poll(() => clipboard(app)).toBe(`! ${CMD}`)

    // 1. The icon: shown over the command's row, at its right end; a click copies.
    // (From elsewhere: a move to where the pointer already is sends no mousemove.)
    const away = await pointOf(page, 'Поставь так')
    await page.mouse.move(away.x, away.y)
    await expect(page.locator('.aqua-screen .mm-cmd')).toHaveCount(0)
    p = await pointOf(page, CMD)
    await page.mouse.move(p.x, p.y, { steps: 2 })
    const icon = page.locator('.aqua-screen .mm-cmd')
    await expect(icon).toBeVisible()
    const row = await page.evaluate(([y]) => {
      const r = [...document.querySelectorAll('.aqua-screen .xterm-rows > div')].find((d) => { const b = d.getBoundingClientRect(); return y >= b.top && y < b.bottom })
      return r ? r.getBoundingClientRect() : null
    }, [p.y] as const)
    const ib = (await icon.boundingBox())!
    expect(ib.y + ib.height / 2, 'the icon on the command\'s row').toBeGreaterThan(row!.top)
    expect(ib.y + ib.height / 2).toBeLessThan(row!.bottom)
    await app.evaluate(({ clipboard }) => clipboard.writeText('nothing yet'))
    await icon.click()
    await expect.poll(() => clipboard(app)).toBe(CMD)
    await expect(icon).toContainText('Copied')
    await expect(page.getByRole('status').filter({ hasText: 'Command copied' })).toBeVisible()
    // Away from the command: no icon.
    await page.mouse.move(away.x, away.y)
    await expect(icon).toHaveCount(0)

    // 2. The two-line block: copied whole; not offered for pasting into sh (its lines would run at once).
    const b = await pointOf(page, 'echo two-')
    await page.mouse.click(b.x, b.y, { button: 'right' })
    await expect(menu.getByRole('menuitem', { name: 'Copy for Claude Code' })).toHaveCount(0)
    await expect(menu.getByRole('menuitem', { name: 'Paste into the terminal' })).toBeDisabled()
    await menu.getByRole('menuitem', { name: 'Copy the command' }).click()
    await expect.poll(() => clipboard(app)).toBe('cd /tmp\necho two-$((1+1))')

    // 3. The inline command; the file name's row has none.
    const g = await pointOf(page, 'git status')
    await page.mouse.click(g.x, g.y, { button: 'right' })
    await menu.getByRole('menuitem', { name: 'Copy the command' }).click()
    await expect.poll(() => clipboard(app)).toBe('git status')
    const f = await pointOf(page, 'README.md')
    await page.mouse.click(f.x, f.y, { button: 'right' })
    await expect(menu.getByRole('menuitem', { name: 'Pin' })).toBeVisible()
    await expect(menu.getByRole('menuitem', { name: 'Copy the command' })).toHaveCount(0)
    await page.keyboard.press('Escape')

    // 4. Paste into the terminal: on the prompt once, not run; Enter runs it once.
    p = await pointOf(page, CMD)
    await page.mouse.click(p.x, p.y, { button: 'right' })
    await menu.getByRole('menuitem', { name: 'Paste into the terminal' }).click()
    await expect(page.getByRole('status').filter({ hasText: 'Pasted into the terminal: Enter runs it' })).toBeVisible()
    await expect.poll(async () => prompted((await lines(page)).filter((l) => l.trim()).at(-1) ?? ''), { message: 'the prompt holds the command' }).toMatch(/^\$ echo cmd-\$\(\(40\+2\)\)-ran$/)
    // Given time to run, it has not: no output.
    await page.waitForTimeout(1200)
    expect((await lines(page)).filter((l) => l.trim() === 'cmd-42-ran')).toHaveLength(0)
    expect((await lines(page)).filter((l) => l.includes(CMD)).map(prompted)).toEqual([`! ${CMD}`, `$ ${CMD}`])
    await page.keyboard.press('Enter')
    await expectLine(page, 'cmd-42-ran')
    expect((await lines(page)).filter((l) => l.trim() === 'cmd-42-ran')).toHaveLength(1)
  })

  test('a shell: a `$ ` row is a command, its icon copies it; a right click offers the command\'s items', async ({ win }) => {
    const { app, page } = win
    await ready(page)
    await typeLine(page, `printf '%s\\n' '$ ls -la /tmp' 'not a command here'`)
    await expectLine(page, 'not a command here')
    const p = await pointOf(page, 'ls -la /tmp', true)
    await page.mouse.move(p.x, p.y)
    const icon = page.locator('.aqua-screen .mm-cmd')
    await expect(icon).toBeVisible()
    await icon.click()
    await expect.poll(() => clipboard(app)).toBe('ls -la /tmp')
    const o = await pointOf(page, 'not a command here', true)
    await page.mouse.move(o.x, o.y)
    await expect(icon).toHaveCount(0)
    await page.mouse.click(p.x, p.y, { button: 'right' })
    const menu = page.getByRole('menu', { name: 'Command' })
    await expect(menu.getByRole('menuitem')).toHaveText(['Copy the command', 'Copy for Claude Code', 'Paste into the terminal', 'Terminal menu…'])
    await menu.getByRole('menuitem', { name: 'Copy for Claude Code' }).click()
    await expect.poll(() => clipboard(app)).toBe('! ls -la /tmp')
    // The keyboard is the terminal's again.
    await typeLine(page, 'echo cmds-$((40+2))-done')
    await expectLine(page, 'cmds-42-done')
  })
})
