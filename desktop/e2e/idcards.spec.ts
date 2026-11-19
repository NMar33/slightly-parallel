import { execFileSync } from 'node:child_process'
import fs from 'node:fs'
import path from 'node:path'
import type { APIRequestContext, Page } from '@playwright/test'
import { test, expect, ROOT, PROJECT, URL_, WINDOWS, expectLine, fullSize, ready, sessions, typeLine } from './fixtures'

/**
 * Records named in the terminal open their card in place (tk_b3edbd84).
 *
 * The sandbox holds a decision (the fixtures' dc_cc266f82), a Publish card
 * and a core made here as the operator, a chat recorded the way the capture
 * hook records one (tied to the test's terminal), and a commit in the
 * project's folder, made a git repository for this test. The terminal
 * prints a line naming each, and a hash that is no commit of the project.
 * A click on each id opens its card (decision, Publish card, core, chat,
 * commit — its changes shown); the fake hash is asked about once and never
 * becomes a link. It runs in tmux and plain terminals (SP_E2E_KEEP=plain).
 */

const REPO = path.resolve(__dirname, '..', '..')
const PYTHON = path.join(REPO, 'backend', '.venv', 'bin', 'python')
const CAPTURE = path.join(REPO, 'scripts', 'hooks', 'capture-cli.py')
const AGENT = 'cc-e2eca4d5'
const DECISION = 'dc_cc266f82'
const FAKE = 'd3adbee1'

function record(sid: string, phase: 'open' | 'complete', text: string) {
  execFileSync(PYTHON, [CAPTURE, '--phase', phase, '--project', PROJECT, '--data-root', path.join(ROOT, 'data'), '--agent', AGENT,
    '--text-stdin', ...(phase === 'open' ? ['--tool', 'claude-code', '--session', 'e2e-cards-session-1', '--cwd', path.join(ROOT, 'work', 'shell')] : [])],
  { input: text, env: { ...process.env, SP_TERMINAL: sid, SP_PORT: new URL(URL_).port }, stdio: ['pipe', 'ignore', 'inherit'] })
}

/** git in the sandbox's project folder, with none of the developer's config (signing, hooks). */
function git(dir: string, ...args: string[]): string {
  return execFileSync('git', ['-c', 'commit.gpgsign=false', '-c', 'init.defaultBranch=master', ...args], {
    cwd: dir, encoding: 'utf-8',
    env: { ...process.env, GIT_CONFIG_GLOBAL: '/dev/null', GIT_CONFIG_NOSYSTEM: '1', GIT_AUTHOR_NAME: 'e2e', GIT_AUTHOR_EMAIL: 'e2e@example.invalid', GIT_COMMITTER_NAME: 'e2e', GIT_COMMITTER_EMAIL: 'e2e@example.invalid' },
  }).trim()
}

/** The shortest prefix of 8 or more that has a letter and a digit (a hash the terminal takes). */
function printable(sha: string): string {
  for (let n = 8; n <= 40; n++) { const s = sha.slice(0, n); if (/[a-f]/.test(s) && /[0-9]/.test(s)) return s }
  return sha
}

async function post(api: APIRequestContext, url: string, data: Record<string, unknown>): Promise<Record<string, unknown>> {
  const r = await api.post(url, { data })
  expect(r.ok(), await r.text()).toBeTruthy()
  return await r.json() as Record<string, unknown>
}

/** The middle of `text` on the screen (xterm's DOM rows), in page pixels. */
async function pointOf(page: Page, text: string): Promise<{ x: number; y: number }> {
  let got: { x: number; y: number } | null = null
  await expect.poll(async () => {
    got = await page.evaluate((want) => {
      for (const row of document.querySelectorAll('.aqua-screen .xterm-rows > div')) {
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
    }, text)
    return got !== null
  }, { message: `"${text}" on the screen` }).toBe(true)
  return got!
}

test.describe('record cards', () => {
  test('a decision, a Publish card, a core, a chat and a commit open their cards; a hash that is no commit is no link', async ({ win, shell, server }) => {
    test.skip(WINDOWS, 'the capture CLI and the printed lines are written for a Unix shell')
    const { page } = win
    await ready(page)
    const asked: string[] = []
    page.on('request', (r) => { if (r.url().includes('/api/git/commit')) asked.push(new URL(r.url()).searchParams.get('sha') ?? '') })

    // The records.
    record(shell.id, 'open', 'make the ids in the terminal open their cards')
    record(shell.id, 'complete', 'Done: decisions, cards, cores, chats and commits open in place.')
    const card = ((await post(server.api, '/api/publishing/cards', { project: PROJECT, text: 'Records open in place in the terminal', actor: 'operator' })).card as { id: string }).id
    const core = ((await post(server.api, '/api/cores', { project: PROJECT, name: 'Terminal window', type: 'interface', reason: 'Where the operator works', actor: 'operator' })).core as { id: string }).id
    const repoDir = server.dir
    const madeRepo = !fs.existsSync(path.join(repoDir, '.git'))
    if (madeRepo) git(repoDir, 'init', '-q')
    try {
      fs.writeFileSync(path.join(repoDir, 'cards.txt'), 'one\ntwo\n')
      git(repoDir, 'add', 'cards.txt')
      git(repoDir, 'commit', '-q', '-m', 'Records open in place\n\nTask: tk_b3edbd84')
      const sha = git(repoDir, 'rev-parse', 'HEAD')
      const short = printable(sha)
      await expect.poll(async () => (await sessions(server.api)).find((s) => s.id === shell.id && (s as { agent_id?: string }).agent_id === AGENT),
        { timeout: 15_000, message: 'the terminal tied to the recorded chat' }).toBeTruthy()

      // The lines that name them.
      const file = path.join(server.dir, '..', 'cards-lines.txt')
      fs.writeFileSync(file, [
        `decision ${DECISION} and card ${card}`,
        `core ${core} by chat ${AGENT}`,
        `[master ${short}] Records open in place`,
        `not a commit: ${FAKE} here`,
        'cards printed',
        '',
      ].join('\n'))
      await typeLine(page, `cat '${file}'`)
      await expectLine(page, 'cards printed')

      const openCard = async (text: string, name: string | RegExp) => {
        const p = await pointOf(page, text)
        const dialog = page.getByRole('dialog', { name })
        // A link is known once xterm asked for the row's links (on hover); a hash after the server answered.
        await expect.poll(async () => {
          await page.mouse.move(p.x, p.y - 30)
          await page.mouse.move(p.x, p.y)
          await page.mouse.click(p.x, p.y)
          return dialog.isVisible()
        }, { timeout: 15_000, intervals: [300, 600, 1000], message: `the card of ${text}` }).toBe(true)
        return dialog
      }

      // 1. The decision.
      const d = await openCard(DECISION, `Decision ${DECISION}`)
      await expect(d.getByText('Chose FastAPI over Flask')).toBeVisible()
      await expect(d.getByText('async support + auto OpenAPI + type hints')).toBeVisible()
      await expect(d.getByRole('button', { name: 'Open on the Decisions page' })).toBeVisible()
      await page.keyboard.press('Escape')
      await expect(d).toHaveCount(0)

      // 2. The Publish card.
      const c = await openCard(card, `Publish card ${card}`)
      await expect(c.getByText('Records open in place in the terminal')).toBeVisible()
      await page.keyboard.press('Escape')
      await expect(c).toHaveCount(0)

      // 3. The core.
      const k = await openCard(core, `Core ${core}`)
      await expect(k.getByText('Terminal window')).toBeVisible()
      await expect(k.getByText('Where the operator works')).toBeVisible()
      await expect(k.getByRole('button', { name: 'Add a note' })).toBeVisible()
      await page.keyboard.press('Escape')
      await expect(k).toHaveCount(0)

      // 4. The chat: its terminal is this one.
      const a = await openCard(AGENT, `Chat ${AGENT}`)
      await expect(a.getByRole('button', { name: 'Go to its tab' })).toBeVisible()
      await expect(a.getByRole('button', { name: 'Open the chat in Slightly Parallel' })).toBeVisible()
      await page.keyboard.press('Escape')
      await expect(a).toHaveCount(0)

      // 5. The commit, and its changes.
      const m = await openCard(short, /^Commit /)
      await expect(m.getByText('Records open in place', { exact: true })).toBeVisible()
      await expect(m.getByRole('button', { name: 'tk_b3edbd84' })).toBeVisible()
      await expect(m.getByTestId('commit-files')).toContainText('cards.txt')
      await m.getByRole('button', { name: 'Show the changes' }).click()
      await expect(m.getByRole('region', { name: 'Changes' })).toContainText('+two')
      await page.keyboard.press('Escape')
      await expect(m).toHaveCount(0)

      // 6. The fake hash: asked about, never a link — a click opens nothing.
      const f = await pointOf(page, FAKE)
      await page.mouse.move(f.x, f.y - 30)
      await page.mouse.move(f.x, f.y)
      await expect.poll(() => asked.includes(FAKE), { message: 'the fake hash asked about' }).toBe(true)
      await page.mouse.click(f.x, f.y)
      await page.waitForTimeout(800)
      await expect(page.locator('.mm-pop')).toHaveCount(0)
      expect(asked.filter((s) => s === FAKE)).toHaveLength(1)

      // The keyboard is the terminal's again.
      await typeLine(page, 'echo cards-$((40+2))-done')
      await expectLine(page, 'cards-42-done')
    } finally {
      if (madeRepo) fs.rmSync(path.join(repoDir, '.git'), { recursive: true, force: true })
      fs.rmSync(path.join(repoDir, 'cards.txt'), { force: true })
    }
  })

  test('a right click on a link copies it as printed: a web address, a task id', async ({ win }) => {
    test.skip(WINDOWS, 'the printed lines are written for a Unix shell')
    const { app, page } = win
    await ready(page)
    await fullSize(app, page)
    // A CI hostname can be long enough to wrap the prompt before the command.
    await typeLine(page, "PS1='$ '")
    await expectLine(page, '$')
    const url = 'https://example.com/docs/a?b=1'
    await typeLine(page, `printf '%s\\n' 'open ${url}. now' 'task tk_b3edbd84 here' 'links printed'`)
    await expectLine(page, 'links printed')
    const clipboard = () => app.evaluate(({ clipboard }) => clipboard.readText())

    const u = await pointOf(page, 'example.com/docs')
    await page.mouse.click(u.x, u.y, { button: 'right' })
    const menu = page.getByRole('menu', { name: 'Link' })
    // The row is the typed `$ printf …` line: a command too (tk_29b870f1), its items after the link's.
    await expect(menu.getByRole('menuitem')).toHaveText(['Copy the link', 'Open', 'Copy the command', 'Copy for Claude Code', 'Paste into the terminal', 'Terminal menu…'])
    await menu.getByRole('menuitem', { name: 'Copy the link' }).click()
    await expect.poll(clipboard).toBe(url)
    await expect(menu).toHaveCount(0)

    const t = await pointOf(page, 'tk_b3edbd84')
    await page.mouse.click(t.x, t.y, { button: 'right' })
    await expect(menu.getByRole('menuitem')).toHaveText(['Copy the link', 'Copy the page address', 'Open', 'Copy the command', 'Copy for Claude Code', 'Paste into the terminal', 'Terminal menu…'])
    await menu.getByRole('menuitem', { name: 'Copy the link' }).click()
    await expect.poll(clipboard).toBe('tk_b3edbd84')
    // tmux drew no pane menu of its own under ours.
    expect(await page.locator('.aqua-screen .xterm-rows').innerText()).not.toMatch(/Horizontal Split|Swap Up/)

    // The keyboard is the terminal's again.
    await typeLine(page, 'echo links-$((40+2))-done')
    await expectLine(page, 'links-42-done')
  })
})
