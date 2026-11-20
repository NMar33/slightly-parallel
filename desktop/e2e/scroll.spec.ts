import fs from 'node:fs'
import path from 'node:path'
import { execFileSync } from 'node:child_process'
import type { ElectronApplication, Page } from '@playwright/test'
import { test, expect, ROOT, WINDOWS, printFile, ready, typeLine, lines, expectLine, echoCalc, expectClickTarget } from './fixtures'
import { tmuxSockets } from './sockets'
import { fmt, notches, offsetNow, runPlan, runTrusted, slowFinger, stats, touchpad, type Stats, type Wheel } from './scrollProbe'

/**
 * Scrolling the terminal (tk_407be124, tk_56f11eb5).
 *
 * Found by the operator: the text moved in jerks, a whole line at a time
 * ("I cannot scroll so that half a line shows"), and in tmux five lines a
 * step, two frames late. xterm.js moves its view by whole rows only; tmux's
 * copy mode moved five rows per wheel report and xterm sent one report per
 * event. Measured before the fix (notes/2611-18-terminal-scroll.md): a
 * touchpad left the text still on 22 of 48 frames, a tmux touchpad moved
 * 468% of the finger in jumps of 84 px, and a full-screen program in tmux
 * did not move at all.
 *
 * Each test prints 3000 numbered lines and sends the wheel in the page:
 * a touchpad (two events a frame, 2–8 px each), a slow finger (2 px a
 * frame), mouse notches (100 px, and 3 lines with deltaMode 1). A probe
 * reads every animation frame where the topmost visible numbered line
 * stands, in pixels (scrollProbe.ts). The expectations per case:
 *
 * - history (a shell; Claude Code writes its conversation there too): the
 *   text moves on every frame that had input, by that frame's input (no
 *   jump bigger than the frame's input plus 2 px), the total equals the
 *   input within a row, and half rows are seen. A notch glides: it moves on
 *   at least three frames, not one. In tmux the reader takes a few frames to
 *   open (a round trip and a capture): still frames count from its first move.
 * - setting off (`scroll=rows`): xterm's own whole rows, as before.
 * - a full-screen program on the alternate screen (vim, less, htop): it
 *   owns its view, so it moves by rows; the wheel's rows reach it one for
 *   one (in tmux it did not move at all before).
 *
 * Tolerances hold on CI's GPU-less runners: the touchpad's pixels are
 * applied in the wheel handler itself, so a slow frame changes nothing but
 * the frame time; a notch's glide is checked by its count of moving frames
 * and its end, not its speed. Frame times are asserted only on the hidden
 * GNOME display (the laptop's GPU): p95 under 34 ms (two frames at 60 Hz).
 * On CI they are printed.
 */

const N = 3000
const OUT = process.env.SP_SCROLL_OUT
/** SP_SCROLL_MODE=rows|smooth: run every test in that mode (to compare); default: smooth. */
const MODE = process.env.SP_SCROLL_MODE ?? ''
const LAPTOP = !!process.env.SP_E2E_WAYLAND && !process.env.CI
const NODE = process.execPath
const PAGER = path.join(__dirname, 'bin', 'altpager.mjs')

async function inMode(page: Page, mode: string) {
  if (!mode) return
  const u = new URL(page.url())
  u.searchParams.set('scroll', mode)
  await page.goto(u.toString())
  await ready(page)
}

function numbered(): string {
  const file = path.join(ROOT, 'work', 'numbered.txt')
  if (!fs.existsSync(file)) {
    fs.writeFileSync(file, Array.from({ length: N }, (_, i) => `L${String(i + 1).padStart(5, '0')} the quick brown fox jumps over the lazy dog ${i % 10}`).join('\n') + '\n')
  }
  return file
}
const LAST = `L${String(N).padStart(5, '0')}`

async function fill(page: Page) {
  await typeLine(page, printFile(numbered()))
  await expect.poll(async () => (await lines(page)).some((l) => l.startsWith(LAST)), { timeout: 30_000 }).toBe(true)
  await page.waitForTimeout(300)
}

async function pager(page: Page, mouse = false) {
  const q = (s: string) => `'${s.replace(/'/g, "''")}'`
  await typeLine(page, `${WINDOWS ? '& ' : ''}${q(NODE)} ${q(PAGER)} ${q(numbered())}${mouse ? ' --mouse' : ''}`)
  await expect.poll(async () => (await lines(page)).some((l) => l.startsWith(LAST)), { timeout: 30_000 }).toBe(true)
  await page.waitForTimeout(300)
}

const results: Record<string, Record<string, Stats>> = {}
function keep(c: string, name: string, s: Stats) {
  console.log(`[${c}] ${name}: ${fmt(s)}`)
  ;(results[c] ??= {})[name] = s
}
test.afterAll(() => {
  if (OUT) {
    const prev = fs.existsSync(OUT) ? JSON.parse(fs.readFileSync(OUT, 'utf-8')) : {}
    fs.writeFileSync(OUT, JSON.stringify({ ...prev, ...results }, null, 1))
  }
})

/** The biggest input one frame of `plan` carries, px. */
const perFrame = (plan: Wheel[][], rowH: number) => Math.max(...plan.map((f) => Math.abs(f.reduce((a, e) => a + (e.mode === 1 ? e.dy * rowH : e.dy), 0))))

function frameBudget(s: Stats) {
  if (LAPTOP) expect(s.frameP95Ms, `frame p95 ${s.frameP95Ms.toFixed(1)} ms`).toBeLessThan(34)
}

/* ------------------------------------------------------------ history */

async function smoothHistory(page: Page, c: string, tmux: boolean) {
  const h0 = await runPlan(page, [[{ dy: -1 }]], 2).then((m) => m.rowH)
  const touch = touchpad(48)
  const s1 = stats(await runPlan(page, touch), 1, tmux)
  keep(c, 'touchpad', s1)
  // The first gesture in tmux opens the reader: still frames until it shows, then none.
  expect(s1.stalls, fmt(s1)).toBeLessThanOrEqual(1)
  // In tmux the input that piled up while the reader opened glides in: no jump bigger than that backlog.
  const most = perFrame(touch, h0)
  expect(s1.maxJump, fmt(s1)).toBeLessThanOrEqual(tmux ? Math.max(3 * h0, (s1.latency + 1) * most) : most + 2)
  expect(Math.abs(s1.moved - s1.asked), fmt(s1)).toBeLessThanOrEqual(h0 + 1)
  expect(s1.wholeRows, `moves of whole rows only: ${fmt(s1)}`).toBeLessThan(0.5)
  frameBudget(s1)

  const slow = slowFinger(60)
  const s2 = stats(await runPlan(page, slow))
  keep(c, 'slow finger', s2)
  expect(s2.stalls, fmt(s2)).toBeLessThanOrEqual(1)
  expect(s2.maxJump, fmt(s2)).toBeLessThanOrEqual(2 + 2)
  expect(Math.abs(s2.moved - s2.asked), fmt(s2)).toBeLessThanOrEqual(1)

  for (const [name, plan] of [['notch 100px', notches(5, 10, -100)], ['notch 3 lines', notches(5, 10, -3, 1)]] as const) {
    const s = stats(await runPlan(page, plan as Wheel[][]))
    keep(c, name, s)
    // A notch glides over several frames; all of it arrives.
    expect(s.movingFrames, `a notch jumped in one frame: ${fmt(s)}`).toBeGreaterThanOrEqual(3 * 5)
    expect(s.maxJump, fmt(s)).toBeLessThan(Math.abs(s.asked) / 5)
    expect(Math.abs(s.moved - s.asked), fmt(s)).toBeLessThanOrEqual(1)
    frameBudget(s)
  }

  // Chromium's own wheel input (CDP): printed, and nothing lost.
  const t1 = stats(await runTrusted(page, Array.from({ length: 60 }, (_, i) => -[2, 3, 5, 8, 4, 6][i % 6]), 8))
  keep(c, 'trusted touchpad', t1)
  expect(Math.abs(t1.moved - t1.asked), fmt(t1)).toBeLessThanOrEqual(h0 + 1)
  expect(t1.wholeRows, fmt(t1)).toBeLessThan(0.5)
  const t2 = stats(await runTrusted(page, [-100, -100, -100, -100], 160))
  keep(c, 'trusted notch', t2)
  expect(Math.abs(t2.moved - t2.asked), fmt(t2)).toBeLessThanOrEqual(1)
}

test('history: the text follows the touchpad by pixels, a notch glides, nothing is lost', async ({ win, shell }) => {
  test.skip(MODE === 'rows', 'SP_SCROLL_MODE=rows measures the old way only (the next test)')
  const { page } = win
  await ready(page)
  await inMode(page, MODE)
  await fill(page)
  expect(await offsetNow(page)).not.toBeNull()
  await smoothHistory(page, `history ${shell.backend}`, shell.backend === 'tmux')
})

test('history, smooth scrolling off: xterm\'s whole rows, as before', async ({ win, shell }) => {
  test.skip(MODE === 'smooth', 'SP_SCROLL_MODE=smooth')
  const { page } = win
  await ready(page)
  await inMode(page, 'rows')
  await fill(page)
  const s = stats(await runPlan(page, touchpad(48)))
  keep(`history ${shell.backend} rows`, 'touchpad', s)
  // Whole rows, and in tmux five of them a step: the off switch really is off.
  expect(s.wholeRows, fmt(s)).toBe(1)
  expect(s.maxJump, fmt(s)).toBeGreaterThanOrEqual(s.rowH - 0.5)
})

test('an ordinary click keeps the wheel on the same route in whole-row mode', async ({ win, shell }) => {
  const { page } = win
  await ready(page)
  await inMode(page, 'rows')
  await fill(page)
  const screen = page.locator('.aqua-screen .xterm-screen')
  const box = (await screen.boundingBox())!
  const point = { x: box.x + box.width / 2, y: box.y + box.height / 2 }
  await expectClickTarget(screen, point)
  await page.mouse.click(point.x, point.y)
  const start = await offsetNow(page)
  expect(start).not.toBeNull()
  await page.mouse.wheel(0, -100)
  if (shell.backend === 'tmux') {
    const [socket] = tmuxSockets(process.env.SP_DESKTOP_E2E_TMUX!)
    await expect.poll(() => execFileSync('tmux', [
      '-S', socket, 'display-message', '-p', '-t', `mk-${shell.id}`, '#{pane_in_mode}',
    ], { encoding: 'utf8' }).trim(), { message: 'tmux still owns the wheel after clicking its terminal' }).toBe('1')
    // The first notch opens tmux's copy mode. The next one scrolls it.
    await page.mouse.wheel(0, -100)
  }
  await expect.poll(async () => (await offsetNow(page)) ?? start!).toBeLessThan(start!)
})

/* ---------------------------------------------- full-screen programs */

test('a full-screen program without the mouse (less, man) moves row for row under the wheel', async ({ win, shell }) => {
  const { page } = win
  await ready(page)
  await inMode(page, MODE)
  await pager(page)
  const c = `alt ${shell.backend}${MODE ? ' ' + MODE : ''}`
  const touch = touchpad(48)
  const s = stats(await runPlan(page, touch))
  keep(c, 'touchpad', s)
  // It owns its view: whole rows; and every row of the wheel reaches it (tmux: none did).
  expect(s.wholeRows, fmt(s)).toBe(1)
  expect(Math.abs(s.moved - s.asked), fmt(s)).toBeLessThanOrEqual(s.rowH + 1)
  const n = stats(await runPlan(page, notches(5, 10, -100)))
  keep(c, 'notch 100px', n)
  expect(Math.abs(n.moved - n.asked), fmt(n)).toBeLessThanOrEqual(5 * n.rowH)
  await page.keyboard.press('q')
  await ready(page)
})

test('a full-screen program that reads the mouse (vim mouse=a) gets the wheel as reports', async ({ win, shell }) => {
  const { page } = win
  await ready(page)
  await inMode(page, MODE)
  await pager(page, true)
  const c = `alt+mouse ${shell.backend}${MODE ? ' ' + MODE : ''}`
  const s = stats(await runPlan(page, touchpad(48)))
  keep(c, 'touchpad', s)
  expect(s.wholeRows, fmt(s)).toBe(1)
  // In tmux the page sends one report per row (xterm alone: one per event that crossed a row).
  if (shell.backend === 'tmux' && MODE !== 'rows') expect(Math.abs(s.moved - s.asked), fmt(s)).toBeLessThanOrEqual(s.rowH + 1)
  else expect(s.moved, fmt(s)).toBeLessThan(0)
  await page.keyboard.press('q')
  await ready(page)
})

/* --------------------------------------- selection, copy and the reader */

const clip = (app: ElectronApplication) => app.evaluate(({ clipboard }) => clipboard.readText())

/** Drag over two rows at the middle of the view, copy with Ctrl+Shift+C: what lands on the clipboard. */
async function dragCopy(page: Page, app: ElectronApplication): Promise<{ under: string; got: string }> {
  await app.evaluate(({ clipboard }) => clipboard.writeText('nothing yet'))
  const box = (await page.locator('.aqua-screen').boundingBox())!
  const x = box.x + 40, y = box.y + box.height / 2
  const under = await page.evaluate(([px, py]) => (document.elementFromPoint(px, py)?.closest('.xterm-rows > div')?.textContent ?? '').trim(), [x, y])
  await page.mouse.move(x - 30, y)
  await page.mouse.down()
  await page.mouse.move(x + 200, y + 18, { steps: 5 })
  await page.mouse.up()
  await page.keyboard.press(process.platform === 'darwin' ? 'Meta+C' : 'Control+Shift+C')
  await expect.poll(() => clip(app)).not.toBe('nothing yet')
  return { under, got: await clip(app) }
}

test('selection and copy work on a view stopped between two rows; typing goes back to the shell', async ({ win, shell }) => {
  test.skip(MODE === 'rows', 'the smooth view only')
  const { page, app } = win
  await ready(page)
  await fill(page)
  // Up by 20.5 rows: the view stops half a row into one.
  const h = await runPlan(page, [[{ dy: 0.0001 }]], 2).then((m) => m.rowH)
  // At the bottom the view stands on a whole row: the probe's offset there is the zero.
  const zero = await offsetNow(page)
  await runPlan(page, [[{ dy: -Math.round(20.5 * h) }], [], [], []], 30)
  if (shell.backend === 'tmux') await expect(page.locator('.sp-reader')).toHaveCount(1)
  const off = await offsetNow(page)
  expect(off, 'the view stands between two rows').not.toBeNull()
  const rows = (zero! - off!) / h
  expect(Math.abs(rows - Math.round(rows)), `half a row shows: ${rows.toFixed(2)} rows up`).toBeGreaterThan(0.2)

  // The row under the pointer is the one selected (the shift is in xterm's mouse maths).
  const { under, got } = await dragCopy(page, app)
  expect(under).toMatch(/^L\d{5}/)
  // (The drag starts a column or two in: compare the line's number.)
  expect(got.split('\n')[0].match(/\d{5}/)?.[0], `clipboard: ${JSON.stringify(got.slice(0, 120))}`).toBe(under.slice(1, 6))

  // A command typed now reaches the shell once; the view is back at the bottom.
  await page.keyboard.type(echoCalc('typed-', '20+1'))
  await page.keyboard.press('Enter')
  await expectLine(page, 'typed-21')
  await expect(page.locator('.sp-reader')).toHaveCount(0)
  expect((await lines(page)).filter((l) => l.trim() === 'typed-21')).toHaveLength(1)
})

test('tmux: the reader closes at the bottom and with Esc, and find searches the whole history', async ({ win, shell }) => {
  test.skip(shell.backend !== 'tmux', 'the reader is for tmux terminals (plain ones keep their history in the page)')
  test.skip(MODE === 'rows', 'the smooth view only')
  const { page } = win
  await ready(page)
  await fill(page)
  const reader = page.locator('.sp-reader')
  await runPlan(page, touchpad(20), 20)
  await expect(reader).toHaveCount(1)
  // The "↓ newest" pill is up while reading.
  await expect(page.getByRole('button', { name: /newest/ })).toBeVisible()
  // Down past the bottom: the live terminal is back.
  await runPlan(page, touchpad(80, 1), 10)
  await runPlan(page, [[{ dy: 40 }]], 10)
  await expect(reader).toHaveCount(0)

  await runPlan(page, touchpad(10), 20)
  await expect(reader).toHaveCount(1)
  await page.locator('.sp-reader textarea').focus()
  await page.keyboard.press('Escape')
  await expect(reader).toHaveCount(0)

  // Find in a tmux terminal: the live screen holds 34 rows, the reader all of them.
  await page.getByRole('textbox', { name: 'Terminal input' }).focus()
  await page.keyboard.press('Control+Shift+F')
  await expect(reader).toHaveCount(1)
  await page.getByRole('textbox', { name: 'Find in the terminal' }).fill('L00042 the quick')
  await expect.poll(async () => page.locator('.sp-reader .xterm-rows > div').evaluateAll((els) => els.some((e) => (e.textContent ?? '').startsWith('L00042')))).toBe(true)
})

/** Esc in the reader: the live terminal is in front again. */
async function closeReader(page: Page) {
  await page.locator('.sp-reader textarea').last().focus()
  await page.keyboard.press('Escape')
  await expect(page.locator('.sp-reader')).toHaveCount(0)
}

test('tmux: the first frame after the first wheel event already moves, the terminal rested or busy (tk_0d123cd5)', async ({ win, shell }) => {
  test.skip(shell.backend !== 'tmux', 'the reader is for tmux terminals')
  test.skip(MODE === 'rows', 'the smooth view only')
  const { page } = win
  // Every capture of the run. The pointer starts off the terminal: on a display with a real
  // pointer (X11 under Xvfb) it may rest where the terminal opens, and the rest begins then.
  const captures: string[] = []
  page.on('request', (r) => { if (r.url().includes('/capture')) captures.push(r.postData() ?? '') })
  await page.mouse.move(2, 2)
  await ready(page)
  await fill(page)
  const h0 = await runPlan(page, [], 2).then((m) => m.rowH)
  const touch = touchpad(24)
  const first = async (what: string) => {
    const s = stats(await runPlan(page, touch, 20))
    keep('first gesture in tmux', what, s)
    // Before: 4–5 still frames (70–85 ms) while the page fetched the history and built the reader.
    expect(s.latency, `the first frame after the first wheel event moves (${what}): ${fmt(s)}`).toBe(1)
    expect(s.stalls, fmt(s)).toBeLessThanOrEqual(1)
    // The reader takes over where the screen was led to: no jump bigger than a frame's input and a row.
    expect(s.maxJump, fmt(s)).toBeLessThanOrEqual(perFrame(touch, h0) + h0)
    expect(Math.abs(s.moved - s.asked), fmt(s)).toBeLessThanOrEqual(h0 + 1)
    await expect(page.locator('.sp-reader')).toHaveCount(1)
    await closeReader(page)
  }
  // At rest, the pointer over the terminal: the history is taken ahead, no round trip when the gesture starts.
  const box = (await page.locator('.aqua-screen').boundingBox())!
  // (One taken while the window opened under the pointer counts against the next by AHEAD_EVERY_MS, 5 s.)
  const before = captures.length
  await page.mouse.move(box.x + box.width / 2, box.y + box.height / 2)
  await expect.poll(() => captures.length, { timeout: 7_000, message: 'the history taken ahead under the pointer' }).toBeGreaterThan(before)
  await page.waitForTimeout(1500)
  // Taken once for this rest, the first 2000 rows; nothing more while it rests.
  expect(captures.slice(before).map((c) => JSON.parse(c).rows)).toEqual([2000])
  await first('rested')
  // Output every 100 ms (an agent at work): nothing taken ahead, the screen is led while the reader loads.
  // (Typed: what the pane shows is asked again a second later, the pointer still over it.)
  await typeLine(page, '(while :; do printf .; sleep 0.1; done) &')
  await page.waitForTimeout(1600)
  await first('busy')
  await typeLine(page, 'kill $!')
})

test('the first wheel frame moves while terminal output is streaming', async ({ win, shell, server }) => {
  const { page } = win
  await page.mouse.move(2, 2)
  await ready(page)
  await fill(page)

  const stream = fs.mkdtempSync(path.join(server.dir, 'stream-'))
  const start = path.join(stream, 'start')
  const stop = path.join(stream, 'stop')
  const script = path.join(stream, 'stream.cjs')
  fs.writeFileSync(script, `
    const fs = require('node:fs')
    let count = 0
    process.stdout.write('stream ready\\r\\n')
    const timer = setInterval(() => {
      if (fs.existsSync(${JSON.stringify(stop)})) clearInterval(timer)
      else if (fs.existsSync(${JSON.stringify(start)})) process.stdout.write('\\rstreaming ' + ++count)
    }, 15)
  `)

  const paneReady = shell.backend === 'tmux'
    ? page.waitForResponse((r) => r.url().endsWith(`/sessions/${shell.id}/pos`) && r.ok())
    : undefined
  const quote = (s: string) => `'${s.replace(/'/g, WINDOWS ? "''" : "'\\''")}'`
  await typeLine(page, `${WINDOWS ? '& ' : ''}${quote(NODE)} ${quote(script)}`)
  await expectLine(page, 'stream ready')
  await paneReady

  // Hold history until after the measurement. The first visible movement
  // has to come from the live screen, even with a slow history response.
  let releaseHistory!: () => void
  const historyReady = new Promise<void>((resolve) => { releaseHistory = resolve })
  if (shell.backend === 'tmux') {
    await page.route(`**/sessions/${shell.id}/capture`, async (route) => {
      await historyReady
      await route.continue()
    })
  }
  try {
    fs.writeFileSync(start, '')
    await expectLine(page, /streaming [1-9]\d*/)
    const measured = await runPlan(page, slowFinger(1), 2)
    const { off: before } = measured.samples[0]!
    const { off: after } = measured.samples[1]!
    expect(before, 'a numbered row was visible before the wheel event').not.toBeNull()
    expect(after, 'a numbered row was visible on the next frame').not.toBeNull()
    expect(before! - after!, 'visible text moves on the first frame while output continues').toBeGreaterThan(0.5)
  } finally {
    fs.writeFileSync(stop, '')
    releaseHistory()
  }
})

test('tmux: a reader closed in the frame it scrolled in throws nothing (tk_988aeb37)', async ({ win, shell }) => {
  test.skip(shell.backend !== 'tmux', 'the reader is for tmux terminals')
  test.skip(MODE === 'rows', 'the smooth view only')
  const { page } = win
  const errors: string[] = []
  page.on('pageerror', (e) => errors.push(e.message))
  await ready(page)
  await fill(page)
  const reader = page.locator('.sp-reader')
  for (let i = 0; i < 8; i++) {
    await runPlan(page, touchpad(6), 4)
    await expect(reader).toHaveCount(1)
    // «↓ newest» comes a render after the reader: at once when the history was taken ahead (the pointer at rest over the terminal).
    await expect(page.locator('.aqua-screen button[title="Back to the newest line"]')).toHaveCount(1)
    // A wheel step on the reader, and in the same task «↓ newest» closes it: xterm's frame for that step comes after.
    await page.evaluate(() => {
      const r = [...document.querySelectorAll<HTMLElement>('.sp-reader')].pop()!
      const sc = r.querySelector('.xterm-screen')!
      const b = sc.getBoundingClientRect()
      sc.dispatchEvent(new WheelEvent('wheel', { deltaY: -24, clientX: b.left + 20, clientY: b.top + 20, bubbles: true, cancelable: true, composed: true, view: window }))
      ;[...document.querySelectorAll<HTMLButtonElement>('.aqua-screen button')].find((x) => x.title === 'Back to the newest line')!.click()
    })
    await expect(reader).toHaveCount(0)
    await page.waitForTimeout(100)
  }
  // Also the swap to the longer history (3000 rows > the first 2000), mid-glide, then closed at once.
  await runPlan(page, notches(3, 2, -100), 2)
  await page.waitForTimeout(400)
  await closeReader(page)
  await page.waitForTimeout(200)
  expect(errors, 'page errors').toEqual([])
})

test('plain: smooth scrolling keeps search and the newest pill', async ({ win, shell }) => {
  test.skip(shell.backend !== 'plain', 'plain terminals (the tmux one is the test above)')
  test.skip(MODE === 'rows', 'the smooth view only')
  const { page } = win
  await ready(page)
  await fill(page)
  await runPlan(page, touchpad(30), 20)
  await expect(page.getByRole('button', { name: /newest/ })).toBeVisible()
  await page.getByRole('textbox', { name: 'Terminal input' }).focus()
  await page.keyboard.press('Control+Shift+F')
  await page.getByRole('textbox', { name: 'Find in the terminal' }).fill('L00042 the quick')
  await expect.poll(async () => (await lines(page)).some((l) => l.startsWith('L00042'))).toBe(true)
  // A wheel after the search jump starts from where search left the view.
  const before = await offsetNow(page)
  await runPlan(page, slowFinger(10), 5)
  const after = await offsetNow(page)
  expect(Math.abs((after! - before!) - -20)).toBeLessThanOrEqual(1)
})
