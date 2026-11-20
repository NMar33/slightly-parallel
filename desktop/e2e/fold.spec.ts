import { execFileSync } from 'node:child_process'
import fs from 'node:fs'
import path from 'node:path'
import type { Page } from '@playwright/test'
import { test, expect, ROOT, PROJECT, URL_, WINDOWS, expectLine, fullSize, ready, sessions, typeLine } from './fixtures'

/**
 * A message collapsed to one line in the terminal's history (tk_a2bb64a1).
 *
 * A chat is recorded as the capture hook records one (msgmenu.spec.ts) and
 * the terminal prints it as Claude Code draws it, a reply of many rows with
 * one line longer than the terminal (two screen rows). The second reply is
 * pinned at the bottom; more output pushes the chat into the history. Then,
 * scrolled up:
 * - «Collapse to one line» on the first reply: one row «▸ A · N lines ·
 *   Read(…)», N its screen rows; the pin mark of the reply below stays on
 *   its text;
 * - a click on that row expands it: the rows are back;
 * - «Collapse all replies» with the first reply wholly above the view: the
 *   text on view does not move; the pinned reply's mark goes to its label;
 * - a reload keeps both; «Expand all» opens them; the live terminal at the
 *   bottom never shows a label.
 * tmux and plain (SP_E2E_KEEP=plain).
 */

const REPO = path.resolve(__dirname, '..', '..')
const PYTHON = path.join(REPO, 'backend', '.venv', 'bin', 'python')
const CAPTURE = path.join(REPO, 'scripts', 'hooks', 'capture-cli.py')
// A chat of its own each run (a repeated test would tie the same chat to the last test's terminal).
const RUN = Math.random().toString(36).slice(2, 7)
const AGENT = `cc-fold${RUN}`

function record(sid: string, phase: 'open' | 'complete', text: string) {
  execFileSync(PYTHON, [CAPTURE, '--phase', phase, '--project', PROJECT, '--data-root', path.join(ROOT, 'data'), '--agent', AGENT,
    '--text-stdin', ...(phase === 'open' ? ['--tool', 'claude-code', '--session', `e2e-fold-${RUN}`, '--cwd', path.join(ROOT, 'work', 'shell')] : [])],
  { input: text, env: { ...process.env, SP_TERMINAL: sid, SP_PORT: new URL(URL_).port }, stdio: ['pipe', 'ignore', 'inherit'] })
}

/** The rows of the xterm in front: the history reader when one is shown, else the live terminal. */
const FRONT = `(() => {
  const rs = [...document.querySelectorAll('.aqua-screen .sp-reader')].filter((e) => e.style.visibility !== 'hidden')
  const host = rs.length ? rs[rs.length - 1] : document.querySelector('.aqua-screen')
  return host.querySelector('.xterm-screen')
})()`

/** `top` is on the page; `y` from the top of the terminal's frame (the window's own layout may move the frame: a line at the bottom comes and goes). */
type Row = { i: number; text: string; top: number; y: number; h: number }

/** Every row of the xterm in front, with its place on the page. */
async function frontRows(page: Page): Promise<Row[]> {
  return page.evaluate((front) => {
    // eslint-disable-next-line no-eval
    const scr = (0, eval)(front) as HTMLElement | null
    if (!scr) return []
    const frame = scr.closest('.aqua-screen')!.getBoundingClientRect().top
    return [...scr.querySelectorAll('.xterm-rows > div')].map((d, i) => {
      const r = d.getBoundingClientRect()
      return { i, text: (d.textContent ?? '').replace(/ /g, ' ').trimEnd(), top: r.top, y: r.top - frame, h: r.height }
    })
  }, FRONT)
}

const rowOf = async (page: Page, want: string | RegExp) =>
  (await frontRows(page)).find((r) => (typeof want === 'string' ? r.text.includes(want) : want.test(r.text))) ?? null

/** The middle of the terminal, where the wheel goes. */
async function centre(page: Page) {
  const b = (await page.locator('.aqua-screen .xterm-screen').first().boundingBox())!
  return { x: b.x + b.width / 2, y: b.y + b.height / 2 }
}

/** Scroll until `text` is on view at a row between lo and hi. */
async function scrollTo(page: Page, text: string, lo: number, hi: number) {
  const c = await centre(page)
  await page.mouse.move(c.x, c.y)
  await expect.poll(async () => {
    const rows = await frontRows(page)
    const h = rows[0]?.h || 17
    const r = rows.find((x) => x.text.includes(text))
    // Not on view: further up (the text is above, the view starts at the bottom).
    const off = !r ? -6 : r.i < lo ? -(lo - r.i) : r.i > hi ? r.i - hi : 0
    if (off === 0) return true
    // Pixel deltas under a notch: the view moves at once (no glide to wait for).
    for (let k = 0; k < Math.abs(off); k++) await page.mouse.wheel(0, Math.sign(off) * h)
    await page.waitForTimeout(150)
    return false
  }, { timeout: 30_000, intervals: [50], message: `"${text}" at rows ${lo}–${hi}` }).toBe(true)
}

/** The menu of the message at `text` (a right click there), retried until the window knows the terminal's chat. */
async function menuAt(page: Page, text: string | RegExp, name?: string | RegExp) {
  const menu = name ? page.getByRole('menu', { name }) : page.locator('.mm-pop[role=menu]')
  await expect.poll(async () => {
    const r = await rowOf(page, text)
    if (!r) return false
    const scr = (await page.locator('.aqua-screen .xterm-screen').first().boundingBox())!
    await page.mouse.click(scr.x + 60, r.top + r.h / 2, { button: 'right' })
    if (await menu.waitFor({ state: 'visible', timeout: 2000 }).then(() => true, () => false)) {
      // Reading the message: the items come once it is found.
      await expect(menu).not.toHaveAttribute('data-found', 'reading')
      return true
    }
    await page.keyboard.press('Escape')
    return false
  }, { timeout: 20_000, intervals: [500], message: `the menu at ${text}` }).toBe(true)
  return menu
}

/** The pin mark's top against the top of the row with `text`. */
async function markOn(page: Page, text: string | RegExp) {
  await expect.poll(async () => {
    const r = await rowOf(page, text)
    const m = await page.evaluate((front) => {
      // eslint-disable-next-line no-eval
      const scr = (0, eval)(front) as HTMLElement | null
      const el = scr?.querySelector('.mm-marks')
      return el ? el.getBoundingClientRect().top : null
    }, FRONT)
    return r && m != null ? Math.abs(m - r.top) : 999
  }, { timeout: 10_000, message: `the pin mark on the row of ${text}` }).toBeLessThan(2)
}

const LABEL = /^▸ A · (\d+) lines · /

test.describe('collapsing a message', () => {
  test('collapse a reply in the history: one row, its count; expand by a click; collapse above the view without a jump; the pin stays on its text; a reload keeps it', async ({ win, shell, server }) => {
    test.skip(WINDOWS, 'the capture CLI and the printed conversation are written for a Unix shell')
    const { app, page } = win
    await ready(page)
    await fullSize(app, page)

    const q1 = 'make the history view collapse a long reply to a single line'
    const r1 = 'The reader now writes each collapsed message as one label row, and the map keeps marks on their text.'
    const q2 = 'and the pin on the next reply'
    const r2 = 'The pin mark follows the reply it was put on, collapsed or not.'
    record(shell.id, 'open', q1)
    record(shell.id, 'complete', r1)
    record(shell.id, 'open', q2)
    record(shell.id, 'complete', r2)
    await expect.poll(async () => (await sessions(server.api)).find((s) => s.id === shell.id && (s as { agent_id?: string }).agent_id === AGENT), { timeout: 15_000, message: 'the terminal tied to the recorded chat' }).toBeTruthy()

    const cols = Number(await page.locator('.aqua-screen [data-cols]').first().getAttribute('data-cols'))
    expect(cols).toBeGreaterThan(60)
    // The first reply: 28 lines, one of them longer than the terminal (two rows on the screen).
    const reply1 = [
      '● Read(frontend/src/features/terminal/reader.ts)',
      '  ⎿  Read 98 lines',
      '',
      '● The reader now writes each collapsed message as one label',
      '  row, and the map keeps marks on their text.',
      ...Array.from({ length: 18 }, (_, i) => `  r1-row-${String(i + 1).padStart(2, '0')} what changed in the reader`),
      '  ' + 'w'.repeat(cols + 4),
      '  r1-after-the-long-line',
      '',
      '✻ Worked for 12s',
    ]
    const n1 = reply1.length + 1
    const file = path.join(server.dir, 'fold-chat.txt')
    fs.writeFileSync(file, [
      ...Array.from({ length: 30 }, (_, i) => `before-${i + 1}`),
      `❯ ${q1}`,
      '',
      ...reply1,
      '',
      `❯ ${q2}`,
      '',
      '● The pin mark follows the reply it was put on, collapsed or',
      '  not.',
      '',
      '✻ Worked for 3s',
      'shell output after the chat',
      '',
    ].join('\n'))
    await typeLine(page, `cat '${file}'`)
    await expectLine(page, 'shell output after the chat')

    // The second reply pinned, at the bottom.
    const pin = await menuAt(page, 'The pin mark follows the reply', 'Agent\'s reply · 2')
    await pin.getByRole('menuitem', { name: 'Pin' }).click()
    await expect(page.getByRole('status').filter({ hasText: 'Message pinned' })).toBeVisible()
    // More output: the chat goes up into the history.
    await typeLine(page, 'for i in $(seq 1 60); do echo after-$i; done')
    await expectLine(page, 'after-60')

    // 1. Scrolled up, the first reply's tail and the pinned reply on view: collapse the first.
    await scrollTo(page, 'r1-row-12', 1, 3)
    await markOn(page, 'The pin mark follows the reply')
    const m1 = await menuAt(page, 'r1-row-14', 'Agent\'s reply · 1')
    await m1.getByRole('menuitem', { name: 'Collapse to one line' }).click()
    await expect(page.getByRole('status').filter({ hasText: 'Collapsed to one line' })).toBeVisible()
    await expect(page.locator('.sp-reader')).toHaveCount(1)
    const label = await rowOf(page, LABEL)
    expect(label, 'the one row of the collapsed reply').not.toBeNull()
    expect(Number(LABEL.exec(label!.text)![1]), 'its screen rows, the long line two').toBe(n1)
    expect(label!.text).toContain('Read(frontend/src/features/terminal/reader.ts)')
    expect(await rowOf(page, 'r1-row-14')).toBeNull()
    // The rows after it follow it at once, and the pin mark is on its text still.
    const labelRow = label!.i
    expect((await rowOf(page, q2))!.i).toBe(labelRow + 2)
    await markOn(page, 'The pin mark follows the reply')

    // 2. A click on the row expands it.
    // (Where the row is read again at the click: the line at the bottom of the window comes and goes, and moves the frame.)
    await expect.poll(async () => {
      const at = await rowOf(page, LABEL)
      if (at) {
        const scr = (await page.locator('.aqua-screen .xterm-screen').first().boundingBox())!
        await page.mouse.click(scr.x + 40, at.top + at.h / 2)
      }
      return !!(await rowOf(page, 'r1-after-the-long-line'))
    }, { intervals: [300], message: 'the reply\'s rows back' }).toBe(true)
    expect(await rowOf(page, LABEL)).toBeNull()
    await markOn(page, 'The pin mark follows the reply')

    // 3. The first reply wholly above the view: «Collapse all replies» leaves the text on view where it was.
    await scrollTo(page, q2, 1, 2)
    const before = (await rowOf(page, q2))!
    const all = await menuAt(page, 'The pin mark follows the reply', 'Agent\'s reply · 2')
    await all.getByRole('menuitem', { name: 'Collapse all replies' }).click()
    await expect(page.getByRole('status').filter({ hasText: /replies collapsed/ })).toBeVisible()
    await expect.poll(async () => (await frontRows(page)).filter((r) => LABEL.test(r.text)).length, { message: 'the pinned reply collapsed on view' }).toBeGreaterThan(0)
    const after = (await rowOf(page, q2))!
    expect(Math.abs(after.y - before.y), 'the operator\'s message on view did not move').toBeLessThan(1)
    // The pinned reply's mark: on its label now.
    await markOn(page, /^▸ A · 4 lines · The pin mark follows/)

    // 4. A reload keeps both.
    await page.reload()
    await ready(page)
    await scrollTo(page, 'before-30', 3, 6)
    await expect.poll(async () => (await frontRows(page)).filter((r) => LABEL.test(r.text)).map((r) => Number(LABEL.exec(r.text)![1])),
      { timeout: 10_000, message: 'both replies collapsed after the reload' }).toEqual([n1, 4])

    // 5. «Expand all» opens them; the live terminal never had a label.
    const ex = await menuAt(page, LABEL, 'Agent\'s reply · 1')
    await ex.getByRole('menuitem', { name: 'Expand all' }).click()
    await expect.poll(async () => (await frontRows(page)).filter((r) => LABEL.test(r.text)).length).toBe(0)
    await expect.poll(async () => !!(await rowOf(page, 'r1-row-01'))).toBe(true)
    await page.locator('.sp-reader textarea').last().focus()
    await page.keyboard.press('Escape')
    await expect(page.locator('.sp-reader')).toHaveCount(0)
    expect((await frontRows(page)).some((r) => r.text.startsWith('▸ '))).toBe(false)
    await typeLine(page, 'echo fold-$((40+2))-done')
    await expectLine(page, 'fold-42-done')
  })
})
